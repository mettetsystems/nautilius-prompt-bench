from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from prompt_piper_api.config import Settings
from prompt_piper_api.domain.inference import (
    ExternalInferenceAuditEvent,
    ExternalInferenceAuditOutcome,
    SendToInferenceResult,
)
from prompt_piper_api.domain.user_settings import ApiEndpointConfig
from prompt_piper_api.llm.base import ChatMessage, LLMClient
from prompt_piper_api.llm.enums import ModelProvider
from prompt_piper_api.llm.factory import (
    ExternalOpenAICompatibleClient,
    create_external_client,
    create_local_client,
)
from prompt_piper_api.llm.settings import ModelSettings, profile_defaults
from prompt_piper_api.services.artifact_service import ArtifactService
from prompt_piper_api.services.audit_log_service import AuditLogService
from prompt_piper_api.services.exceptions import InferenceCallError
from prompt_piper_api.services.logging_config import redact_secrets
from prompt_piper_api.services.session_record import SessionRecord
from prompt_piper_api.services.state_transitions import ACTION_SEND_TO_INFERENCE, require_state
from prompt_piper_api.services.user_settings_service import UserSettingsService, get_user_settings_service


class ExternalInferenceBlockedError(Exception):
    """Raised when an external inference call is blocked by privacy guardrails."""

    def __init__(self, message: str, *, reason: str) -> None:
        self.reason = reason
        super().__init__(message)


ExternalClientFactory = Callable[[Settings], LLMClient]
InferenceClientFactory = Callable[[Settings], LLMClient]


class ExternalInferenceService:
    """Send approved optimized prompts to external providers with local audit logging."""

    INFERENCE_RESPONSE_FILENAME = "inference_response.txt"
    OPTIMIZED_ARTIFACT_FILENAME = "optimized_prompt.txt"

    def __init__(
        self,
        settings: Settings,
        audit: AuditLogService,
        artifacts_path: Path,
        *,
        external_client_factory: ExternalClientFactory | None = None,
        local_client_factory: InferenceClientFactory | None = None,
        user_settings: UserSettingsService | None = None,
    ) -> None:
        self._settings = settings
        self._audit = audit
        self._artifacts_path = artifacts_path
        self._external_client_factory = external_client_factory or create_external_client
        self._local_client_factory = local_client_factory or create_local_client
        self._user_settings = user_settings or get_user_settings_service()

    def send_to_inference(
        self,
        record: SessionRecord,
        *,
        explicit_approval: bool,
        api_endpoint_id: str | None = None,
    ) -> SendToInferenceResult:
        session = record.session
        current = record.current_draft
        prompt_id = session.prompt_id
        version = current.version if current is not None else None

        def audit_and_block(reason: str, message: str) -> NoReturn:
            self._write_audit(
                session_id=str(session.id),
                prompt_id=prompt_id,
                version=version,
                outcome=ExternalInferenceAuditOutcome.BLOCKED,
                block_reason=reason,
                explicit_approval=explicit_approval,
            )
            raise ExternalInferenceBlockedError(message, reason=reason)

        if not self._settings.require_approval_before_external_call:
            audit_and_block(
                "approval_policy_violation",
                "External inference requires explicit user approval in v1.",
            )

        if not explicit_approval:
            audit_and_block(
                "explicit_approval_required",
                "External inference requires explicit_approval=true in the request body.",
            )

        if (
            not self._settings.external_inference_enabled
            and not self._user_settings.is_llm_enabled(self._settings)
            and not self._has_configured_endpoint()
        ):
            audit_and_block(
                "inference_unavailable",
                "No external model API is configured. Add an endpoint in Settings or enable the local LLM.",
            )

        if (
            prompt_id is None
            or current is None
            or not current.is_canonical
            or not current.is_frozen
        ):
            audit_and_block(
                "prompt_not_finalized",
                "Only finalized canonical prompts may be sent to external inference.",
            )

        if record.optimization_result is None or not record.optimization_result.approved:
            audit_and_block(
                "prompt_not_optimized",
                "Only approved optimized prompts may be sent to external inference.",
            )

        require_state(
            session.state,
            ACTION_SEND_TO_INFERENCE,
            "Send to model is only allowed after optimization approval.",
        )

        client, provider, model = self._resolve_inference_client(
            audit_and_block,
            api_endpoint_id=api_endpoint_id,
        )
        artifact_dir = ArtifactService.resolve_latest_artifact_dir(
            self._artifacts_path,
            prompt_id,
        )
        if artifact_dir is None or current is None:
            audit_and_block(
                "artifacts_missing",
                "Approved artifact export is required before sending to the model.",
            )
        optimized_path = artifact_dir / self.OPTIMIZED_ARTIFACT_FILENAME
        artifact_location = str(optimized_path)
        inference_response_path = str(artifact_dir / self.INFERENCE_RESPONSE_FILENAME)

        try:
            prompt_body = record.optimization_result.optimized_body
            chat_response = client.chat([ChatMessage(role="user", content=prompt_body)])

            response_path = Path(inference_response_path)
            response_path.parent.mkdir(parents=True, exist_ok=True)
            response_path.write_text(chat_response.content, encoding="utf-8")

            timestamp = datetime.now(tz=UTC)
            result = SendToInferenceResult(
                provider=provider,
                model=chat_response.model or model,
                prompt_id=prompt_id,
                version=current.version,
                timestamp=timestamp,
                artifact_location=artifact_location,
                inference_response_artifact_path=inference_response_path,
                response_text=chat_response.content,
            )
            self._write_audit(
                session_id=str(session.id),
                prompt_id=prompt_id,
                version=current.version,
                outcome=ExternalInferenceAuditOutcome.SUCCESS,
                explicit_approval=True,
                provider=result.provider,
                model=result.model,
                artifact_location=artifact_location,
                inference_response_artifact_path=inference_response_path,
            )
            return result
        except ExternalInferenceBlockedError:
            raise
        except Exception as exc:
            self._write_audit(
                session_id=str(session.id),
                prompt_id=prompt_id,
                version=version,
                outcome=ExternalInferenceAuditOutcome.ERROR,
                explicit_approval=explicit_approval,
                provider=provider,
                model=model,
                artifact_location=artifact_location,
                error_message=redact_secrets(str(exc)),
            )
            raise InferenceCallError(
                "Model API call failed.",
                reason="provider_error",
            ) from exc

    def _has_configured_endpoint(self) -> bool:
        return any(
            endpoint.configured for endpoint in self._user_settings.load().normalized_endpoints()
        )

    def _resolve_inference_client(
        self,
        audit_and_block: Callable[[str, str], NoReturn],
        *,
        api_endpoint_id: str | None,
    ) -> tuple[LLMClient, str, str]:
        prefs = self._user_settings.load()
        selected_id = api_endpoint_id or prefs.default_api_endpoint_id
        endpoint = prefs.endpoint_by_id(selected_id)
        if endpoint is not None and endpoint.configured:
            return (
                self._client_from_endpoint(endpoint),
                ModelProvider.EXTERNAL_OPENAI_COMPATIBLE.value,
                endpoint.chat_model,
            )

        if self._settings.external_inference_enabled:
            return (
                self._external_client_factory(self._settings),
                ModelProvider.EXTERNAL_OPENAI_COMPATIBLE.value,
                self._settings.prompt_piper_external_chat_model,
            )

        client = self._local_client_factory(self._settings)
        try:
            health = client.health_check()
        except Exception:
            health = None
        if health is None or not health.ok:
            audit_and_block(
                "local_model_unavailable",
                "Local model API is not reachable. Start the LLM server or enable external inference.",
            )
        return (
            client,
            ModelProvider.LOCAL_OPENAI_COMPATIBLE.value,
            self._settings.prompt_piper_local_chat_model,
        )

    def _client_from_endpoint(self, endpoint: ApiEndpointConfig) -> LLMClient:
        temperature, max_tokens = profile_defaults(self._settings.prompt_piper_model_profile)
        chat_settings = ModelSettings(
            provider=ModelProvider.EXTERNAL_OPENAI_COMPATIBLE,
            base_url=endpoint.base_url,
            model_name=endpoint.chat_model,
            api_key=endpoint.api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            enabled=True,
            profile=self._settings.prompt_piper_model_profile,
        )
        return ExternalOpenAICompatibleClient(
            chat_settings,
            embed_model_name=self._settings.prompt_piper_external_embed_model,
            timeout=self._settings.prompt_piper_llm_timeout_seconds,
        )

    def _write_audit(
        self,
        *,
        session_id: str,
        prompt_id: str | None,
        version: int | None,
        outcome: ExternalInferenceAuditOutcome,
        explicit_approval: bool,
        block_reason: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        artifact_location: str | None = None,
        inference_response_artifact_path: str | None = None,
        error_message: str | None = None,
    ) -> None:
        self._audit.log_external_inference_attempt(
            ExternalInferenceAuditEvent(
                session_id=session_id,
                prompt_id=prompt_id,
                version=version,
                outcome=outcome,
                block_reason=block_reason,
                provider=provider,
                model=model,
                explicit_approval=explicit_approval,
                artifact_location=artifact_location,
                inference_response_artifact_path=inference_response_artifact_path,
                error_message=error_message,
            )
        )

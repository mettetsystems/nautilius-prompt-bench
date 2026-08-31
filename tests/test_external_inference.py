import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.config import Settings
from prompt_piper_api.domain.inference import ExternalInferenceAuditOutcome
from prompt_piper_api.llm.enums import ModelProvider
from prompt_piper_api.llm.mock import MockLLMClient
from prompt_piper_api.llm.settings import ModelSettings
from prompt_piper_api.main import app
from prompt_piper_api.services.artifact_factory import create_artifact_export_service
from prompt_piper_api.services.audit_log_service import AuditLogService
from prompt_piper_api.services.external_inference_service import (
    ExternalInferenceBlockedError,
    ExternalInferenceService,
)
from prompt_piper_api.services.git_registry_service import GitRegistryService
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_session_to_edit


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "registry"


@pytest.fixture
def artifacts_path(tmp_path: Path) -> Path:
    path = tmp_path / "exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit"


@pytest.fixture
def enabled_settings(
    registry_path: Path,
    artifacts_path: Path,
    audit_path: Path,
) -> Settings:
    return Settings(
        registry_path=registry_path,
        artifacts_path=artifacts_path,
        audit_log_path=audit_path,
        prompt_piper_export_root=artifacts_path.parent,
        prompt_piper_host_export_root=artifacts_path.parent,
        prompt_piper_registry_root=registry_path,
        prompt_piper_artifact_root=artifacts_path,
        prompt_piper_external_enabled=True,
        prompt_piper_external_base_url="https://api.openai.com/v1",
        prompt_piper_external_chat_model="gpt-4o-mini",
        prompt_piper_external_api_key="test-key",
    )


@pytest.fixture
def mock_external_client() -> MockLLMClient:
    return MockLLMClient(
        settings=ModelSettings(
            provider=ModelProvider.EXTERNAL_OPENAI_COMPATIBLE,
            base_url="https://api.openai.com/v1",
            model_name="gpt-4o-mini",
            api_key="test-key",
        ),
        chat_responder=lambda _messages: "external-model-output",
    )


@pytest.fixture
def service(
    enabled_settings: Settings,
    registry_path: Path,
    artifacts_path: Path,
    audit_path: Path,
    mock_external_client: MockLLMClient,
) -> SessionService:
    return SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=None,
        optimizer=TokenOptimizationEngine(),
        artifact_export=create_artifact_export_service(enabled_settings),
        external_inference=ExternalInferenceService(
            enabled_settings,
            AuditLogService(audit_path),
            artifacts_path,
            external_client_factory=lambda _settings: mock_external_client,
        ),
    )


def _sample_body() -> str:
    return "\n".join(
        [
            "Technical Context",
            "-----------------",
            "Environment: Python with FastAPI and Pydantic",
            "",
            "Core Task and Scope",
            "-------------------",
            "Objective: Add FastAPI endpoint for weekly engineering status summaries.",
            "",
            "Architectural Rules and Constraints",
            "-----------------------------------",
            "Keep the response within 300 words.",
            "",
            "Inputs, Outputs, and Contracts",
            "------------------------------",
            "Output contract: JSON with blockers, owners, and next steps.",
        ]
    )


def _enter_approval_state(service: SessionService, *, body: str | None = None) -> UUID:
    created = service.create_session(
        initial_request="Summarize weekly engineering status for leadership review.",
    )
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Engineering managers", "Bulleted summary with risks"],
    )
    record = service.get_session(session_id)
    record.session.requirement_card.objective = (
        "Summarize weekly engineering status for leadership review."
    )
    record.session.requirement_card.unresolved_fields = []
    if body is not None:
        record.drafts[-1].body = body
    service.finalize(session_id, acknowledge_first_shot_risk=True)
    service.optimize(session_id)
    service.approve_optimization(session_id)
    service.generate_artifacts(session_id)
    return session_id


def test_external_inference_disabled_by_default() -> None:
    settings = Settings()
    assert settings.external_inference_enabled is False
    assert settings.require_approval_before_external_call is True


def test_require_approval_cannot_be_disabled() -> None:
    with pytest.raises(ValueError, match="cannot be disabled"):
        Settings(require_approval_before_external_call=False)


def test_unfinalized_prompt_cannot_be_sent(
    service: SessionService,
    audit_path: Path,
) -> None:
    created = service.create_session(initial_request="Draft a weekly status update prompt")
    session_id = created.record.session.id

    with pytest.raises(ExternalInferenceBlockedError, match="finalized"):
        service.send_to_inference(session_id, explicit_approval=True)

    events = AuditLogService(audit_path).read_external_inference_events()
    assert len(events) == 1
    assert events[0].outcome is ExternalInferenceAuditOutcome.BLOCKED
    assert events[0].block_reason == "prompt_not_finalized"


def test_unoptimized_prompt_cannot_be_sent(
    service: SessionService,
    audit_path: Path,
) -> None:
    created = service.create_session(
        initial_request="Summarize weekly engineering status for leadership review.",
    )
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Engineering managers", "Bulleted summary with risks"],
    )
    record = service.get_session(session_id)
    record.session.requirement_card.unresolved_fields = []
    service.finalize(session_id, acknowledge_first_shot_risk=True)

    with pytest.raises(ExternalInferenceBlockedError, match="optimized"):
        service.send_to_inference(session_id, explicit_approval=True)

    events = AuditLogService(audit_path).read_external_inference_events()
    assert events[-1].block_reason == "prompt_not_optimized"


def test_explicit_approval_required(
    service: SessionService,
    audit_path: Path,
) -> None:
    session_id = _enter_approval_state(service, body=_sample_body())

    with pytest.raises(ExternalInferenceBlockedError, match="explicit_approval"):
        service.send_to_inference(session_id, explicit_approval=False)

    events = AuditLogService(audit_path).read_external_inference_events()
    assert events[-1].block_reason == "explicit_approval_required"
    assert events[-1].explicit_approval is False


def test_inference_unavailable_when_no_model_configured(
    registry_path: Path,
    artifacts_path: Path,
    audit_path: Path,
) -> None:
    disabled_settings = Settings(
        registry_path=registry_path,
        artifacts_path=artifacts_path,
        audit_log_path=audit_path,
        prompt_piper_export_root=artifacts_path.parent,
        prompt_piper_host_export_root=artifacts_path.parent,
        prompt_piper_registry_root=registry_path,
        prompt_piper_artifact_root=artifacts_path,
        prompt_piper_external_enabled=False,
        prompt_piper_llm_enabled=False,
    )
    svc = SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=None,
        optimizer=TokenOptimizationEngine(),
        artifact_export=create_artifact_export_service(disabled_settings),
        external_inference=ExternalInferenceService(
            disabled_settings,
            AuditLogService(audit_path),
            artifacts_path,
        ),
    )
    session_id = _enter_approval_state(svc, body=_sample_body())

    with pytest.raises(ExternalInferenceBlockedError, match="No external model API"):
        svc.send_to_inference(session_id, explicit_approval=True)

    events = AuditLogService(audit_path).read_external_inference_events()
    assert events[-1].block_reason == "inference_unavailable"


def test_local_model_used_when_external_disabled(
    registry_path: Path,
    artifacts_path: Path,
    audit_path: Path,
    mock_external_client: MockLLMClient,
) -> None:
    local_client = MockLLMClient(
        chat_responder=lambda _messages: "local-model-output",
    )
    settings = Settings(
        registry_path=registry_path,
        artifacts_path=artifacts_path,
        audit_log_path=audit_path,
        prompt_piper_export_root=artifacts_path.parent,
        prompt_piper_host_export_root=artifacts_path.parent,
        prompt_piper_registry_root=registry_path,
        prompt_piper_artifact_root=artifacts_path,
        prompt_piper_external_enabled=False,
        prompt_piper_llm_enabled=True,
    )
    svc = SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=None,
        optimizer=TokenOptimizationEngine(),
        artifact_export=create_artifact_export_service(settings),
        external_inference=ExternalInferenceService(
            settings,
            AuditLogService(audit_path),
            artifacts_path,
            external_client_factory=lambda _settings: mock_external_client,
            local_client_factory=lambda _settings: local_client,
        ),
    )
    session_id = _enter_approval_state(svc, body=_sample_body())
    result = svc.send_to_inference(session_id, explicit_approval=True)

    assert result.provider == ModelProvider.LOCAL_OPENAI_COMPATIBLE.value
    assert result.response_text == "local-model-output"
    assert len(local_client.chat_calls) == 1


def test_successful_send_writes_audit_and_response_artifact(
    service: SessionService,
    artifacts_path: Path,
    audit_path: Path,
    mock_external_client: MockLLMClient,
) -> None:
    session_id = _enter_approval_state(service, body=_sample_body())
    record = service.get_session(session_id)
    prompt_id = record.session.prompt_id
    assert prompt_id

    result = service.send_to_inference(session_id, explicit_approval=True)

    assert result.provider == ModelProvider.EXTERNAL_OPENAI_COMPATIBLE.value
    assert result.model == "gpt-4o-mini"
    assert result.prompt_id == prompt_id
    assert result.inference_response_artifact_path.endswith("inference_response.txt")
    assert Path(result.inference_response_artifact_path).read_text(encoding="utf-8") == (
        "external-model-output"
    )
    assert len(mock_external_client.chat_calls) == 1
    assert mock_external_client.chat_calls[0][0].role == "user"

    events = AuditLogService(audit_path).read_external_inference_events()
    assert events[-1].outcome is ExternalInferenceAuditOutcome.SUCCESS
    assert events[-1].inference_response_artifact_path == result.inference_response_artifact_path


def test_api_route_send_to_inference(
    enabled_settings: Settings,
    registry_path: Path,
    artifacts_path: Path,
    audit_path: Path,
    mock_external_client: MockLLMClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompt_piper_api.config import get_settings
    from prompt_piper_api.routes import sessions as sessions_routes

    monkeypatch.setenv("REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("ARTIFACTS_PATH", str(artifacts_path))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setenv("PROMPT_PIPER_EXTERNAL_ENABLED", "true")
    monkeypatch.setenv("PROMPT_PIPER_EXTERNAL_API_KEY", "test-key")
    get_settings.cache_clear()
    sessions_routes._session_service = None

    svc = SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=None,
        optimizer=TokenOptimizationEngine(),
        artifact_export=create_artifact_export_service(enabled_settings),
        external_inference=ExternalInferenceService(
            enabled_settings,
            AuditLogService(audit_path),
            artifacts_path,
            external_client_factory=lambda _settings: mock_external_client,
        ),
    )
    sessions_routes._session_service = svc

    session_id = _enter_approval_state(svc, body=_sample_body())
    client = TestClient(app)

    blocked = client.post(
        f"/sessions/{session_id}/send-to-inference",
        json={"explicit_approval": False},
    )
    assert blocked.status_code == 403
    assert blocked.json()["reason"] == "explicit_approval_required"

    response = client.post(
        f"/sessions/{session_id}/send-to-inference",
        json={"explicit_approval": True},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["prompt_id"]
    assert body["provider"] == ModelProvider.EXTERNAL_OPENAI_COMPATIBLE.value
    assert body["artifact_location"]
    assert body["inference_response_artifact_path"]
    assert body["response_text"] == "external-model-output"
    assert body["timestamp"]

    audit_file = audit_path / "external_inference.jsonl"
    log_lines = audit_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(log_lines) >= 2
    last_event = json.loads(log_lines[-1])
    assert last_event["outcome"] == "success"

    get_settings.cache_clear()
    sessions_routes._session_service = None


def test_inference_settings_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/settings/inference")
    assert response.status_code == 200
    body = response.json()
    assert body["external_inference_enabled"] is False
    assert body["require_approval_before_external_call"] is True
    assert body["send_to_inference_available"] is True
    assert body["uses_local_model"] is True
    assert body["local_model_endpoint"]
    assert body["embedding_model"]

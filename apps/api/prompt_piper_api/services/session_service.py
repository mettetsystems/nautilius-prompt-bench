from uuid import UUID

from pydantic import BaseModel

from prompt_piper_api.domain.artifacts import ArtifactGenerationResult
from prompt_piper_api.domain.audit import AuditEvent, AuditEventKind, AuditOutcome
from prompt_piper_api.domain.draft import PromptDraft
from prompt_piper_api.domain.edit_intent import EditIntent
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.domain.inference import SendToInferenceResult
from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.domain.session import PromptSession
from prompt_piper_api.domain.similarity import SimilarityCheckResult, SimilarityMatch
from prompt_piper_api.llm.base import LLMClient
from prompt_piper_api.services.artifact_export_service import ArtifactExportService
from prompt_piper_api.services.ask_the_locals_service import (
    AskTheLocalsInsight,
    AskTheLocalsService,
)
from prompt_piper_api.services.audit_log_service import AuditLogService
from prompt_piper_api.services.clarification_option_guides import QuickReplyGuide
from prompt_piper_api.services.clarification_prompts import ClarificationVersionText
from prompt_piper_api.services.clarification_question_ranker import (
    ClarificationQuestion,
    ClarificationQuestionRanker,
    clarification_field_priority,
    prune_deferred_unresolved,
)
from prompt_piper_api.services.clarification_suggestion_service import (
    ClarificationSuggestions,
    ClarificationSuggestionService,
)
from prompt_piper_api.services.draft_generator import DraftGenerator
from prompt_piper_api.services.draft_patch_service import DraftPatchService
from prompt_piper_api.services.exceptions import (
    FirstShotRiskError,
    SessionNotFoundError,
    StateTransitionError,
)
from prompt_piper_api.services.external_inference_service import (
    ExternalInferenceBlockedError,
    ExternalInferenceService,
)
from prompt_piper_api.services.first_shot_readiness import (
    FirstShotReadiness,
    assess_first_shot_readiness,
)
from prompt_piper_api.services.git_registry_service import (
    GitRegistryService,
    RegistryWriteResult,
    build_prompt_id,
)
from prompt_piper_api.services.logging_config import get_logger
from prompt_piper_api.services.optimization import TokenOptimizationEngine
from prompt_piper_api.services.pre_inference_metrics_service import PreInferenceMetricsService
from prompt_piper_api.services.precision_suggestion_service import PrecisionSuggestionService
from prompt_piper_api.services.quality_gate_service import QualityGateService
from prompt_piper_api.services.requirement_card_extractor import RequirementCardExtractor
from prompt_piper_api.services.semantic_precision import (
    SemanticPrecisionEvaluator,
)
from prompt_piper_api.services.session_record import SessionRecord
from prompt_piper_api.services.session_store import InMemorySessionStore, SessionStore
from prompt_piper_api.services.similarity_check_service import SimilarityCheckService
from prompt_piper_api.services.state_transitions import (
    ACTION_ANSWER,
    ACTION_APPROVE_OPTIMIZATION,
    ACTION_COMPLETE_CLARIFICATION,
    ACTION_CREATE_FROM_TEMPLATE,
    ACTION_EDIT,
    ACTION_FINALIZE,
    ACTION_GENERATE_ARTIFACTS,
    ACTION_OPTIMIZE,
    ACTION_PRECISION_APPLY,
    ACTION_PRECISION_SUGGEST,
    ACTION_REOPEN_EDIT,
    ACTION_RERUN_OPTIMIZE,
    ACTION_RERUN_SIMILARITY,
    require_session_open,
    require_state,
)
from prompt_piper_api.services.user_settings_service import (
    UserSettingsService,
    get_user_settings_service,
)

logger = get_logger(__name__)


class SessionActionResult(BaseModel):
    record: SessionRecord
    clarification_question: str | None = None
    clarification_field: str | None = None
    clarification_question_number: int | None = None
    clarification_total_questions: int | None = None
    clarification_quick_replies: list[str] | None = None
    clarification_quick_reply_guides: list[QuickReplyGuide] | None = None
    clarification_versions: list[ClarificationVersionText] | None = None
    clarification_can_finish: bool | None = None
    draft: PromptDraft | None = None
    revised_draft: PromptDraft | None = None
    semantic_diff: str | None = None
    change_summary: str | None = None
    edit_intent: EditIntent | None = None
    updated_requirement_card: RequirementCard | None = None
    prompt_id: str | None = None
    registry_warning: str | None = None
    registry_metadata: RegistryWriteResult | None = None
    similarity_warning: str | None = None
    similarity_matches: list[SimilarityMatch] = []
    similarity_result: SimilarityCheckResult | None = None
    optimization_result: OptimizationResult | None = None
    pre_inference_metrics: PreInferenceMetrics | None = None
    quality_gate_passed: bool | None = None
    quality_gate_warnings: list[str] = []
    artifact_result: ArtifactGenerationResult | None = None
    artifact_warning: str | None = None
    inference_result: SendToInferenceResult | None = None
    first_shot_readiness: FirstShotReadiness | None = None


def _clarification_payload(
    question: ClarificationQuestion | None,
    *,
    can_finish: bool | None = None,
) -> dict[str, object | None]:
    if question is None:
        return {
            "clarification_question": None,
            "clarification_field": None,
            "clarification_question_number": None,
            "clarification_total_questions": None,
            "clarification_quick_replies": None,
            "clarification_quick_reply_guides": None,
            "clarification_versions": None,
            "clarification_can_finish": can_finish,
        }
    return {
        "clarification_question": question.question,
        "clarification_field": question.field_name,
        "clarification_question_number": question.question_number,
        "clarification_total_questions": question.total_questions,
        "clarification_quick_replies": question.quick_reply_options,
        "clarification_quick_reply_guides": question.quick_reply_guides,
        "clarification_versions": question.versions,
        "clarification_can_finish": can_finish,
    }


class SessionService:
    """Orchestrates the Nautilius Prompting Workbench session state machine."""


    def __init__(
        self,
        llm: LLMClient | None = None,
        registry: GitRegistryService | None = None,
        similarity: SimilarityCheckService | None = None,
        optimizer: TokenOptimizationEngine | None = None,
        artifact_export: ArtifactExportService | None = None,
        external_inference: ExternalInferenceService | None = None,
        audit: AuditLogService | None = None,
        store: SessionStore | None = None,
        user_settings: UserSettingsService | None = None,
    ) -> None:
        self._store = store if store is not None else InMemorySessionStore()
        self._cache: dict[UUID, SessionRecord] = {}
        self._llm = llm
        self._user_settings = user_settings or get_user_settings_service()
        self._extractor = RequirementCardExtractor(llm)
        self._ranker = ClarificationQuestionRanker(None)
        self._suggestion_service = ClarificationSuggestionService(llm)
        self._draft_generator = DraftGenerator(llm)
        self._patch_service = DraftPatchService(llm)
        self._registry = registry
        self._similarity = similarity
        self._optimizer = optimizer or TokenOptimizationEngine()
        self._quality_gate = QualityGateService()
        self._precision = SemanticPrecisionEvaluator()
        self._precision_suggestions = PrecisionSuggestionService(llm)
        self._artifact_export = artifact_export
        self._external_inference = external_inference
        self._audit = audit

    def create_session(
        self, *, initial_request: str, title: str | None = None
    ) -> SessionActionResult:
        session = PromptSession(state=SessionState.INTAKE)
        session.requirement_card = self._extractor.extract(initial_request)
        if title:
            session.title = title
        elif session.requirement_card.objective:
            session.title = session.requirement_card.objective[:80]

        record = SessionRecord(session=session, initial_request=initial_request.strip())
        question = self._begin_clarification(record)
        self._save(record)
        return SessionActionResult(
            record=record,
            **_clarification_payload(
                question,
                can_finish=self._can_complete_clarification_early(record),
            ),
        )

    def create_session_from_template(
        self,
        source_session_id: UUID,
        *,
        title: str | None = None,
    ) -> SessionActionResult:
        source = self.get_session(source_session_id)
        source_session = source.session

        require_state(
            source_session.state,
            ACTION_CREATE_FROM_TEMPLATE,
            "Only completed sessions can be used as templates.",
        )

        template_body = self._template_draft_body(source)
        if not template_body.strip():
            raise StateTransitionError(
                "Template session has no draft text to copy.",
                current_state=source_session.state.value,
                action=ACTION_CREATE_FROM_TEMPLATE,
            )

        session = PromptSession(state=SessionState.EDIT)
        session.requirement_card = source.session.requirement_card.model_copy(deep=True)
        session.template_source_session_id = source_session_id
        session.title = title or f"{source_session.title} (from template)"

        record = SessionRecord(
            session=session,
            initial_request=source.initial_request,
        )
        draft = PromptDraft(
            session_id=session.id,
            version=1,
            body=template_body,
            change_summary=(
                f"Initial draft copied from completed session {source_session_id}."
            ),
        )
        record.add_draft(draft)
        self._begin_edit_unresolved_queue(record)
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=draft,
            **_clarification_payload(record.pending_clarification),
        )

    def get_session(self, session_id: UUID) -> SessionRecord:
        cached = self._cache.get(session_id)
        if cached is not None:
            prune_deferred_unresolved(cached.session.requirement_card)
            return cached
        record = self._store.get(session_id)
        if record is None:
            raise SessionNotFoundError(str(session_id))
        prune_deferred_unresolved(record.session.requirement_card)
        self._cache[session_id] = record
        return record

    def delete_session(self, session_id: UUID) -> None:
        self.get_session(session_id)
        self._cache.pop(session_id, None)
        self._store.delete(session_id)

    def _save(self, record: SessionRecord) -> None:
        self._cache[record.session.id] = record
        self._store.save(record)

    def suggest_clarification(self, session_id: UUID, current_answer: str = "", model: str = "lightweight", field_name: str | None = None) -> ClarificationSuggestions:
        record = self.get_session(session_id)
        session = record.session
        pending = record.pending_clarification

        require_state(
            session.state,
            ACTION_ANSWER,
            "Clarification suggestions are only available while clarifying or resolving unresolved fields in edit.",
        )
        if pending is None:
            raise StateTransitionError(
                "No clarification question is pending for this session.",
                current_state=session.state.value,
                action=ACTION_ANSWER,
            )

        if field_name is not None and field_name != pending.field_name:
            raise ValueError("Question changed; regenerate suggestions for the current question.")
        from prompt_piper_api.llm.factory import create_clarification_client
        suggestion_service = self._suggestion_service
        if model == "large":
            from prompt_piper_api.config import get_settings
            suggestion_service = ClarificationSuggestionService(
                create_clarification_client(),
                use_user_prompt="deepseek-r1" in get_settings().prompt_piper_clarification_model.casefold(),
            )
        result = suggestion_service.suggest(
            current_answer=current_answer,
            initial_request=record.initial_request,
            card=session.requirement_card,
            field_name=pending.field_name,
            last_answer=record.last_clarification_answer,
            asked_fields=record.asked_clarification_fields,
        )
        result.model_source = model
        if model == "large" and not result.model_available:
            result.message = "Dedicated clarification model unavailable. Configure it with make setup or check its endpoint and timeout. Your manual answer is unchanged."
        record.clarification_suggestions.append(result.model_dump())
        self._save(record)
        return result

    def ask_the_locals(self, session_id: UUID) -> AskTheLocalsInsight:
        record = self.get_session(session_id)
        session = record.session
        pending = record.pending_clarification

        require_state(
            session.state,
            ACTION_ANSWER,
            "Ask The Locals is only available while clarifying or resolving unresolved fields in edit.",
        )
        if pending is None:
            raise StateTransitionError(
                "No clarification question is pending for this session.",
                current_state=session.state.value,
                action=ACTION_ANSWER,
            )

        from prompt_piper_api.llm.factory import create_ask_the_locals_client

        client, model_source = create_ask_the_locals_client()
        return AskTheLocalsService(client).ask(
            initial_request=record.initial_request,
            card=session.requirement_card,
            field_name=pending.field_name,
            last_answer=record.last_clarification_answer,
            asked_fields=record.asked_clarification_fields,
            model_source=model_source,
        )

    def answer_clarification(self, session_id: UUID, answer: str) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session
        pending = record.pending_clarification

        require_state(
            session.state,
            ACTION_ANSWER,
            "Clarification answers are only accepted while clarifying or resolving unresolved fields in edit.",
        )
        if pending is None:
            raise StateTransitionError(
                "No clarification question is pending for this session.",
                current_state=session.state.value,
                action=ACTION_ANSWER,
            )

        if session.state is SessionState.EDIT:
            return self._answer_edit_unresolved(record, pending, answer)

        self._extractor.apply_answer(session.requirement_card, pending.field_name, answer)
        record.pending_clarification = None
        record.last_clarification_answer = answer.strip()
        record.clarification_turn += 1
        session.touch()

        if self._should_finish_clarification(record):
            draft = self._create_initial_draft(record)
            self._save(record)
            return SessionActionResult(
                record=record,
                draft=draft,
                **_clarification_payload(record.pending_clarification),
            )

        question = self._set_pending_question(record)
        self._save(record)
        return SessionActionResult(
            record=record,
            **_clarification_payload(
                question,
                can_finish=self._can_complete_clarification_early(record),
            ),
        )

    def complete_clarification(self, session_id: UUID) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_state(
            session.state,
            ACTION_COMPLETE_CLARIFICATION,
            "Clarification can only be completed while clarifying.",
        )
        if record.pending_clarification is None and record.clarification_turn == 0:
            raise StateTransitionError(
                "No clarification is in progress for this session.",
                current_state=session.state.value,
                action=ACTION_COMPLETE_CLARIFICATION,
            )
        if not self._can_complete_clarification_early(record):
            raise StateTransitionError(
                "Fill or mark remaining fields as unspecified before generating a draft.",
                current_state=session.state.value,
                action=ACTION_COMPLETE_CLARIFICATION,
            )

        record.pending_clarification = None
        draft = self._create_initial_draft(record)
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=draft,
            **_clarification_payload(record.pending_clarification),
        )

    def edit_draft(
        self,
        session_id: UUID,
        instruction: str | None = None,
        *,
        body: str | None = None,
    ) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_state(
            session.state,
            ACTION_EDIT,
            "Edits are only allowed after an initial draft exists in edit state.",
        )

        current = record.current_draft
        if current is None:
            raise StateTransitionError(
                "Edits require an existing draft.",
                current_state=session.state.value,
                action=ACTION_EDIT,
            )
        if current.is_frozen:
            raise StateTransitionError(
                "The canonical draft is frozen after finalization.",
                current_state=session.state.value,
                action=ACTION_EDIT,
            )

        if body is not None:
            return self._replace_draft_body(record, body)
        if instruction is None or not instruction.strip():
            msg = "Provide an edit instruction or a replacement draft body"
            raise ValueError(msg)

        patch = self._patch_service.apply(session.requirement_card, instruction, current.body)
        draft = PromptDraft.create_revision(
            session_id=session.id,
            existing_drafts=record.drafts,
            body=patch.updated_body,
            change_summary=patch.change_summary,
            semantic_diff=patch.semantic_diff,
        )
        record.add_draft(draft)
        session.requirement_card = patch.updated_requirement_card
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=draft,
            revised_draft=draft,
            semantic_diff=patch.semantic_diff,
            change_summary=patch.change_summary,
            edit_intent=patch.intent,
            updated_requirement_card=patch.updated_requirement_card,
        )

    def _replace_draft_body(self, record: SessionRecord, body: str) -> SessionActionResult:
        if not body.strip():
            msg = "Draft body cannot be empty"
            raise ValueError(msg)
        session = record.session
        draft = PromptDraft.create_revision(
            session_id=session.id,
            existing_drafts=record.drafts,
            body=body,
            change_summary="Direct draft edit.",
            semantic_diff="Draft body replaced by a direct edit.",
        )
        record.add_draft(draft)
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=draft,
            revised_draft=draft,
            semantic_diff=draft.semantic_diff,
            change_summary=draft.change_summary,
            edit_intent=EditIntent.DIRECT_EDIT,
            updated_requirement_card=session.requirement_card,
        )

    def finalize(
        self,
        session_id: UUID,
        *,
        acknowledge_first_shot_risk: bool = False,
    ) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_state(
            session.state,
            ACTION_FINALIZE,
            "Finalization is only allowed from edit state.",
        )

        current = record.current_draft
        if current is None:
            raise StateTransitionError(
                "Finalization requires an existing draft.",
                current_state=session.state.value,
                action="finalize",
            )

        readiness = assess_first_shot_readiness(session.requirement_card)
        if not readiness.ready and not acknowledge_first_shot_risk:
            risk_messages = [risk.message for risk in readiness.risks]
            raise FirstShotRiskError(
                "First-shot readiness gaps remain. "
                "Fill contract fields or finalize with acknowledge_first_shot_risk=true.",
                risks=risk_messages,
            )

        for draft in record.drafts:
            draft.is_canonical = draft.id == current.id
            if draft.is_canonical:
                draft.is_frozen = True

        prompt_id = build_prompt_id(session.title, session.id)
        session.prompt_id = prompt_id
        registry_result: RegistryWriteResult | None = None
        registry_warning: str | None = None

        if self._registry is not None:
            registry_result = self._registry.finalize_prompt(
                prompt_id=prompt_id,
                version=current.version,
                title=session.title,
                body=current.body,
                requirement_card=session.requirement_card,
                session_id=session.id,
                domain="coding",
                task_family=session.requirement_card.task_identity.task_type,
                output_form=session.requirement_card.agent_contract.completion_contract,
            )
            registry_warning = registry_result.warning

        similarity_warning, similarity_matches, similarity_result = self._run_similarity_check(
            record,
            current=current,
            artifact_paths=(
                registry_result.metadata.artifact_paths
                if registry_result is not None
                else None
            ),
            abstract=(
                registry_result.metadata.abstract
                if registry_result is not None
                else None
            ),
        )

        if self._audit is not None:
            self._audit.log_event(
                AuditEvent(
                    kind=AuditEventKind.REGISTRY_FINALIZE,
                    outcome=AuditOutcome.SUCCESS,
                    session_id=str(session.id),
                    prompt_id=prompt_id,
                    version=current.version,
                    action=ACTION_FINALIZE,
                    message="Registry finalized.",
                )
            )

        session.state = SessionState.SIMILARITY_CHECK
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=current,
            prompt_id=prompt_id,
            registry_warning=registry_warning,
            registry_metadata=registry_result,
            similarity_warning=similarity_warning,
            similarity_matches=similarity_matches,
            similarity_result=similarity_result,
            first_shot_readiness=readiness,
        )

    def reopen_for_edit(self, session_id: UUID) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_session_open(session.state, ACTION_REOPEN_EDIT)
        require_state(
            session.state,
            ACTION_REOPEN_EDIT,
            "Re-opening for edit is only available after finalization.",
        )

        current = record.current_draft
        if current is None:
            raise StateTransitionError(
                "Re-opening for edit requires an existing draft.",
                current_state=session.state.value,
                action=ACTION_REOPEN_EDIT,
            )

        for draft in record.drafts:
            draft.is_frozen = False
            draft.is_canonical = False

        self._clear_downstream_work(record)
        session.state = SessionState.EDIT
        self._begin_edit_unresolved_queue(record)
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=current,
            **_clarification_payload(record.pending_clarification),
        )

    def rerun_similarity_check(self, session_id: UUID) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_session_open(session.state, ACTION_RERUN_SIMILARITY)
        require_state(
            session.state,
            ACTION_RERUN_SIMILARITY,
            "Similarity check can only be re-run after finalization.",
        )

        current = record.current_draft
        if current is None or not current.is_canonical:
            raise StateTransitionError(
                "Re-running similarity requires a finalized canonical draft.",
                current_state=session.state.value,
                action=ACTION_RERUN_SIMILARITY,
            )
        if session.prompt_id is None:
            raise StateTransitionError(
                "Re-running similarity requires a finalized prompt_id.",
                current_state=session.state.value,
                action=ACTION_RERUN_SIMILARITY,
            )

        record.optimization_result = None
        record.pre_inference_metrics = None
        record.artifact_result = None

        similarity_warning, similarity_matches, similarity_result = self._run_similarity_check(
            record,
            current=current,
        )

        session.state = SessionState.SIMILARITY_CHECK
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=current,
            prompt_id=session.prompt_id,
            similarity_warning=similarity_warning,
            similarity_matches=similarity_matches,
            similarity_result=similarity_result,
        )

    def rerun_optimization(self, session_id: UUID) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_session_open(session.state, ACTION_RERUN_OPTIMIZE)
        require_state(
            session.state,
            ACTION_RERUN_OPTIMIZE,
            "Optimization can only be re-run after the first optimization pass.",
        )

        current = record.current_draft
        if current is None or not current.is_canonical:
            raise StateTransitionError(
                "Re-running optimization requires a finalized canonical draft.",
                current_state=session.state.value,
                action=ACTION_RERUN_OPTIMIZE,
            )

        record.optimization_result = None
        record.pre_inference_metrics = None
        record.artifact_result = None
        session.state = SessionState.SIMILARITY_CHECK
        session.touch()
        self._save(record)
        return self.optimize(session_id)

    def optimize(self, session_id: UUID) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_state(
            session.state,
            ACTION_OPTIMIZE,
            "Optimization is only allowed after finalization and similarity check.",
        )

        current = record.current_draft
        if current is None or not current.is_canonical:
            raise StateTransitionError(
                "Optimization requires a finalized canonical draft.",
                current_state=session.state.value,
                action=ACTION_OPTIMIZE,
            )

        self._reconcile_unresolved_fields(current.body, session.requirement_card)

        optimization = self._optimizer.optimize(current.body, session.requirement_card)
        record.optimization_result = optimization
        session.state = SessionState.OPTIMIZATION
        session.touch()
        pre_metrics = self._quality_gate.compute_metrics(
            optimization.optimized_body,
            session.requirement_card,
            optimization=optimization,
            baseline_body=optimization.original_body,
        )
        record.pre_inference_metrics = pre_metrics
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=current,
            optimization_result=optimization,
            pre_inference_metrics=pre_metrics,
            quality_gate_passed=None,
        )

    def approve_optimization(self, session_id: UUID) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_state(
            session.state,
            ACTION_APPROVE_OPTIMIZATION,
            "Optimization approval is only allowed from optimization state.",
        )
        if record.optimization_result is None:
            raise StateTransitionError(
                "No optimization result is available to approve.",
                current_state=session.state.value,
                action=ACTION_APPROVE_OPTIMIZATION,
            )

        approved = self._optimizer.approve(record.optimization_result)
        gate_result = self._quality_gate.evaluate_for_approval(
            approved.optimized_body,
            session.requirement_card,
            approved,
        )
        if not gate_result.passed:
            raise StateTransitionError(
                "Pre-inference quality gate failed: " + "; ".join(gate_result.failures),
                current_state=session.state.value,
                action=ACTION_APPROVE_OPTIMIZATION,
            )

        record.optimization_result = approved
        record.pre_inference_metrics = gate_result.metrics
        if not approved.export_ready:
            raise StateTransitionError(
                "Unresolved hard conflicts must be resolved before approval.",
                current_state=session.state.value,
                action=ACTION_APPROVE_OPTIMIZATION,
            )

        session.state = SessionState.APPROVAL
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=record.current_draft,
            optimization_result=approved,
            pre_inference_metrics=gate_result.metrics,
            quality_gate_passed=True,
            quality_gate_warnings=list(gate_result.warnings),
        )

    def _llm_available(self) -> bool:
        if self._llm is None:
            return False
        try:
            return self._llm.health_check().ok
        except Exception:
            return False

    def _require_optimization_body(self, record: SessionRecord) -> str:
        session = record.session
        require_state(
            session.state,
            ACTION_PRECISION_SUGGEST,
            "Precision review is only available during optimization.",
        )
        require_session_open(session.state, ACTION_PRECISION_SUGGEST)
        if record.optimization_result is None:
            raise StateTransitionError(
                "No optimization result is available for precision review.",
                current_state=session.state.value,
                action=ACTION_PRECISION_SUGGEST,
            )
        return record.optimization_result.optimized_body

    def get_precision_review(self, session_id: UUID):
        from prompt_piper_api.schemas.precision import PrecisionReviewResponse

        record = self.get_session(session_id)
        body = self._require_optimization_body(record)
        result = self._precision.evaluate(body)
        lexicon = self._precision_suggestions.lexicon_available()
        vector_index = self._precision_suggestions.vector_index_available()
        return PrecisionReviewResponse(
            score=result.score,
            threshold=self._user_settings.precision_warning_threshold(),
            vague_language_count=len(result.findings),
            findings=result.findings,
            llm_available=self._llm_available(),
            lexicon_available=lexicon,
            vector_index_available=vector_index,
            refinement_available=len(result.findings) > 0,
            optimized_body=body,
        )

    def suggest_precision_replacement(self, session_id: UUID, *, finding_id: str):
        record = self.get_session(session_id)
        body = self._require_optimization_body(record)
        finding = self._find_precision_finding(record, body, finding_id)
        return self._precision_suggestions.suggest(
            finding=finding,
            body=body,
            card=record.session.requirement_card,
        )

    def apply_precision_replacement(
        self,
        session_id: UUID,
        *,
        finding_id: str,
        replacement: str,
    ) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session
        require_state(
            session.state,
            ACTION_PRECISION_APPLY,
            "Precision replacements are only allowed during optimization.",
        )
        require_session_open(session.state, ACTION_PRECISION_APPLY)
        optimization = record.optimization_result
        if optimization is None:
            raise StateTransitionError(
                "No optimization result is available for precision review.",
                current_state=session.state.value,
                action=ACTION_PRECISION_APPLY,
            )

        body = optimization.optimized_body
        finding = self._find_precision_finding(record, body, finding_id)
        updated_body = self._precision.apply_replacement(
            body,
            line_number=finding.line_number,
            term=finding.term,
            replacement=replacement,
            start=finding.start,
            end=finding.end,
        )

        optimization = optimization.model_copy(
            update={
                "optimized_body": updated_body,
                "changes": optimization.changes.model_copy(
                    update={
                        "precision_improvements": [
                            *optimization.changes.precision_improvements,
                            f"Line {finding.line_number}: '{finding.term}' → '{replacement.strip()}'",
                        ],
                    }
                ),
            }
        )
        record.optimization_result = optimization
        pre_metrics = self._quality_gate.compute_metrics(
            updated_body,
            session.requirement_card,
            optimization=optimization,
            baseline_body=optimization.original_body,
        )
        record.pre_inference_metrics = pre_metrics
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=record.current_draft,
            optimization_result=optimization,
            pre_inference_metrics=pre_metrics,
        )

    def _find_precision_finding(self, record: SessionRecord, body: str, finding_id: str):
        for item in self._precision.evaluate(body).findings:
            if item.id == finding_id:
                return item
        raise StateTransitionError(
            f"Precision finding '{finding_id}' was not found in the current prompt.",
            current_state=record.session.state.value,
            action=ACTION_PRECISION_APPLY,
        )

    def generate_artifacts(
        self,
        session_id: UUID,
        *,
        include_pdf: bool = True,
        export_folder_label: str | None = None,
    ) -> SessionActionResult:
        record = self.get_session(session_id)
        session = record.session

        require_state(
            session.state,
            ACTION_GENERATE_ARTIFACTS,
            "Artifact generation is only allowed after optimization approval.",
        )
        if session.prompt_id is None:
            raise StateTransitionError(
                "Artifact generation requires a finalized prompt_id.",
                current_state=session.state.value,
                action=ACTION_GENERATE_ARTIFACTS,
            )
        if record.optimization_result is None or not record.optimization_result.approved:
            raise StateTransitionError(
                "Approved optimization result is required before artifact generation.",
                current_state=session.state.value,
                action=ACTION_GENERATE_ARTIFACTS,
            )
        if self._artifact_export is None:
            raise StateTransitionError(
                "Artifact export service is not configured.",
                current_state=session.state.value,
                action=ACTION_GENERATE_ARTIFACTS,
            )

        current = record.current_draft
        if current is None or not current.is_canonical:
            raise StateTransitionError(
                "Artifact generation requires a finalized canonical draft.",
                current_state=session.state.value,
                action=ACTION_GENERATE_ARTIFACTS,
            )

        registry_metadata = None
        if self._registry is not None:
            registry_metadata = self._registry.load_metadata(session.prompt_id)

        try:
            artifact_result = self._artifact_export.export(
                prompt_id=session.prompt_id,
                version=current.version,
                title=session.title,
                canonical_body=current.body,
                optimized_body=record.optimization_result.optimized_body,
                requirement_card=session.requirement_card,
                registry_metadata=registry_metadata,
                optimization_result=record.optimization_result,
                pre_inference_metrics=record.pre_inference_metrics,
                similarity_result=record.similarity_result,
                include_pdf=include_pdf,
                session_id=str(session.id),
                export_folder_label=export_folder_label,
            )
        except PermissionError as exc:
            export_root = self._artifact_export.export_root
            raise StateTransitionError(
                "Cannot write export artifacts: permission denied for "
                f"{export_root}. If you use native dev, point PROMPT_PIPER_EXPORT_ROOT "
                "to a writable folder (for example ./data under the repo), or run: "
                f"sudo chown -R $USER:$USER {export_root.parent}",
                current_state=session.state.value,
                action=ACTION_GENERATE_ARTIFACTS,
            ) from exc
        record.artifact_result = artifact_result

        registry_warning: str | None = None
        if self._registry is not None:
            evaluation_scores: dict[str, float] = {}
            if record.pre_inference_metrics is not None:
                evaluation_scores = {
                    "requirement_capture_score": (
                        record.pre_inference_metrics.requirement_capture_score
                    ),
                    "unspecified_field_honesty": (
                        record.pre_inference_metrics.unspecified_field_honesty
                    ),
                    "instruction_clarity": record.pre_inference_metrics.instruction_clarity,
                    "format_adherence": record.pre_inference_metrics.format_adherence,
                    "richness_score": record.pre_inference_metrics.richness_score,
                    "density_score": record.pre_inference_metrics.density_score,
                    "efficiency_score": record.pre_inference_metrics.efficiency_score,
                    "denoising_score": record.pre_inference_metrics.denoising_score,
                    "deconfliction_score": record.pre_inference_metrics.deconfliction_score,
                    "semantic_precision_score": (
                        record.pre_inference_metrics.semantic_precision_score
                    ),
                }
            registry_warning = self._registry.update_artifact_paths(
                session.prompt_id,
                artifact_paths=artifact_result.artifact_paths,
                evaluation_scores=evaluation_scores,
                expected_version=current.version,
            )

        if self._audit is not None:
            self._audit.log_event(
                AuditEvent(
                    kind=AuditEventKind.ARTIFACT_EXPORT,
                    outcome=AuditOutcome.SUCCESS,
                    session_id=str(session.id),
                    prompt_id=session.prompt_id,
                    version=current.version,
                    action=ACTION_GENERATE_ARTIFACTS,
                    artifact_location=artifact_result.artifact_dir,
                    message="Artifacts exported.",
                )
            )

        warnings = list(artifact_result.warnings)
        if registry_warning:
            warnings.append(registry_warning)

        session.state = SessionState.EXPORTED
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=current,
            prompt_id=session.prompt_id,
            optimization_result=record.optimization_result,
            pre_inference_metrics=record.pre_inference_metrics,
            artifact_result=artifact_result,
            artifact_warning="; ".join(warnings) if warnings else None,
            registry_warning=registry_warning,
        )

    def send_to_inference(
        self,
        session_id: UUID,
        *,
        explicit_approval: bool,
        api_endpoint_id: str | None = None,
    ) -> SendToInferenceResult:
        record = self.get_session(session_id)
        if self._external_inference is None:
            raise ExternalInferenceBlockedError(
                "External inference service is not configured.",
                reason="service_unavailable",
            )
        result = self._external_inference.send_to_inference(
            record,
            explicit_approval=explicit_approval,
            api_endpoint_id=api_endpoint_id,
        )
        record.inference_result = result
        record.session.touch()
        self._save(record)
        return result

    def _clear_downstream_work(self, record: SessionRecord) -> None:
        record.optimization_result = None
        record.similarity_result = None
        record.pre_inference_metrics = None
        record.artifact_result = None

    def _run_similarity_check(
        self,
        record: SessionRecord,
        *,
        current: PromptDraft,
        artifact_paths: dict[str, str] | None = None,
        abstract: str | None = None,
    ) -> tuple[str | None, list[SimilarityMatch], SimilarityCheckResult | None]:
        session = record.session
        prompt_id = session.prompt_id
        if prompt_id is None:
            return None, [], None

        resolved_paths = artifact_paths or {
            "canonical_md": "canonical_prompt.md",
            "canonical_txt": "canonical_prompt.txt",
        }
        resolved_abstract = abstract or session.requirement_card.objective

        if artifact_paths is None and self._registry is not None:
            metadata = self._registry.load_metadata(prompt_id)
            if metadata is not None:
                resolved_paths = metadata.artifact_paths
                resolved_abstract = metadata.abstract

        similarity_warning: str | None = None
        similarity_matches: list[SimilarityMatch] = []
        similarity_result: SimilarityCheckResult | None = None

        if self._similarity is not None:
            try:
                similarity_result = self._similarity.check_and_index(
                    prompt_id=prompt_id,
                    version=current.version,
                    title=session.title,
                    body=current.body,
                    abstract=resolved_abstract,
                    requirement_card=session.requirement_card,
                    artifact_paths=resolved_paths,
                )
                similarity_warning = similarity_result.warning
                similarity_matches = similarity_result.matches
                record.similarity_result = similarity_result
            except Exception:
                logger.exception("similarity_check_failed", extra={"prompt_id": prompt_id})
                similarity_warning = "Similarity check failed; continuing without index update."

        return similarity_warning, similarity_matches, similarity_result

    def _begin_clarification(self, record: SessionRecord) -> ClarificationQuestion | None:
        record.session.state = SessionState.CLARIFYING
        record.clarification_turn = 0
        return self._set_pending_question(record)

    def _set_pending_question(self, record: SessionRecord) -> ClarificationQuestion | None:
        exclude = frozenset(record.asked_clarification_fields)
        question = self._ranker.top_question(
            record.session.requirement_card,
            question_number=record.clarification_turn + 1,
            total_questions=len(set(record.asked_clarification_fields) | set(clarification_field_priority(record.session.requirement_card))),
            exclude=exclude,
            last_answer=record.last_clarification_answer,
        )
        record.pending_clarification = question
        if question is not None:
            record.asked_clarification_fields.append(question.field_name)
        record.session.touch()
        return question

    def _should_finish_clarification(self, record: SessionRecord) -> bool:
        card = record.session.requirement_card
        missing = self._ranker.missing_fields(card)
        if not missing:
            return True
        return all(field in record.asked_clarification_fields for field in missing)

    def _can_complete_clarification_early(self, record: SessionRecord) -> bool:
        card = record.session.requirement_card
        missing = self._ranker.missing_fields(card)
        if not missing:
            return True
        return all(field_name in card.unresolved_fields for field_name in missing)

    def _create_initial_draft(self, record: SessionRecord) -> PromptDraft:
        generated = self._draft_generator.generate(record.session.requirement_card)
        draft = PromptDraft(
            session_id=record.session.id,
            version=1,
            body=generated.body,
            change_summary=(
                "Initial draft generated after clarification. " + generated.unspecified_note
            ),
            semantic_diff=generated.unspecified_note,
        )
        record.session.requirement_card.unresolved_fields = list(generated.unresolved_fields)
        record.add_draft(draft)
        record.session.state = SessionState.EDIT
        record.pending_clarification = None
        self._begin_edit_unresolved_queue(record)
        record.session.touch()
        return draft

    def _edit_unresolved_queue(self, card: RequirementCard) -> list[str]:
        unresolved = set(card.unresolved_fields)
        return [field for field in clarification_field_priority(card) if field in unresolved]

    def _begin_edit_unresolved_queue(self, record: SessionRecord) -> ClarificationQuestion | None:
        """Seed a one-pass question queue for unresolved fields while in edit."""
        record.edit_unresolved_asked = []
        queue = self._edit_unresolved_queue(record.session.requirement_card)
        record.edit_unresolved_total = len(queue)
        if not queue:
            record.pending_clarification = None
            return None
        return self._set_pending_edit_unresolved_question(record)

    def _set_pending_edit_unresolved_question(
        self,
        record: SessionRecord,
    ) -> ClarificationQuestion | None:
        remaining = [
            field
            for field in self._edit_unresolved_queue(record.session.requirement_card)
            if field not in record.edit_unresolved_asked
        ]
        if not remaining:
            record.pending_clarification = None
            return None

        field_name = remaining[0]
        asked_count = len(record.edit_unresolved_asked)
        total = record.edit_unresolved_total or (asked_count + len(remaining))
        question = self._ranker.build_question(
            field_name,
            question_number=asked_count + 1,
            total_questions=max(total, 1),
            rank=asked_count + 1,
            card=record.session.requirement_card,
            last_answer=record.last_clarification_answer,
        )
        record.pending_clarification = question
        record.edit_unresolved_asked.append(field_name)
        record.session.touch()
        return question

    def _answer_edit_unresolved(
        self,
        record: SessionRecord,
        pending: ClarificationQuestion,
        answer: str,
    ) -> SessionActionResult:
        session = record.session
        self._extractor.apply_answer(session.requirement_card, pending.field_name, answer)
        record.last_clarification_answer = answer.strip()

        generated = self._draft_generator.generate(session.requirement_card)
        session.requirement_card.unresolved_fields = list(generated.unresolved_fields)
        draft = PromptDraft.create_revision(
            session_id=session.id,
            existing_drafts=record.drafts,
            body=generated.body,
            change_summary=(
                f"Updated draft from answer to {pending.field_name}. "
                + generated.unspecified_note
            ),
            semantic_diff=generated.unspecified_note,
        )
        record.add_draft(draft)
        question = self._set_pending_edit_unresolved_question(record)
        session.touch()
        self._save(record)
        return SessionActionResult(
            record=record,
            draft=draft,
            revised_draft=draft,
            change_summary=draft.change_summary,
            semantic_diff=draft.semantic_diff,
            updated_requirement_card=session.requirement_card,
            **_clarification_payload(question),
        )

    @staticmethod
    def _template_draft_body(source: SessionRecord) -> str:
        for draft in source.drafts:
            if draft.is_canonical:
                return draft.body
        if source.current_draft is not None:
            return source.current_draft.body
        if source.optimization_result is not None:
            return source.optimization_result.optimized_body
        return ""

    @staticmethod
    def _reconcile_unresolved_fields(canonical_body: str, card: RequirementCard) -> None:
        """Drop non-critical unresolved fields already marked unspecified in the canonical draft.

        Critical contract leaves stay unresolved so honesty / first-shot scoring still
        catches optimizer drops of those unspecified markers.
        """
        from prompt_piper_api.services.first_shot_readiness import CRITICAL_CONTRACT_FIELDS

        metrics = PreInferenceMetricsService()
        critical = frozenset(CRITICAL_CONTRACT_FIELDS)
        card.unresolved_fields = [
            field_name
            for field_name in card.unresolved_fields
            if field_name in critical
            or not metrics._field_marked_unspecified(canonical_body, card, field_name)
        ]
        prune_deferred_unresolved(card)

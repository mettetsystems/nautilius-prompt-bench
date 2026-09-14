from datetime import datetime
from typing import Self
from uuid import UUID

from prompt_piper_api.domain.artifacts import ArtifactManifest
from prompt_piper_api.domain.draft import PromptDraft
from prompt_piper_api.domain.edit_intent import EditIntent
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.domain.inference import SendToInferenceResult
from prompt_piper_api.domain.limits import (
    MAX_CLARIFICATION_ANSWER_CHARS,
    MAX_DRAFT_BODY_CHARS,
    MAX_EDIT_INSTRUCTION_CHARS,
    MAX_EXPORT_FOLDER_LABEL_CHARS,
    MAX_INITIAL_REQUEST_CHARS,
    MAX_SESSION_TITLE_CHARS,
)
from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.domain.similarity import SimilarityMatch
from prompt_piper_api.services.clarification_option_guides import QuickReplyGuide
from prompt_piper_api.services.clarification_prompts import ClarificationVersionText
from prompt_piper_api.services.clarification_question_ranker import ClarificationQuestionRanker
from prompt_piper_api.services.clarification_suggestion_service import ClarificationSuggestions
from prompt_piper_api.services.first_shot_readiness import (
    FirstShotReadiness,
    assess_first_shot_readiness,
)
from prompt_piper_api.services.session_record import SessionRecord
from prompt_piper_api.services.session_service import SessionActionResult
from pydantic import BaseModel, Field, model_validator


class ClarificationSuggestionsResponse(ClarificationSuggestions):
    pass


class ClarificationSuggestionRequest(BaseModel):
    current_answer: str = Field(default="", max_length=4096)
    model: str = Field(default="lightweight", pattern="^(lightweight|large)$")
    field_name: str | None = None


class AskTheLocalsResponse(BaseModel):
    field_name: str
    insight: str = ""
    recommended_answer: str = ""
    previous_answers_used: list[str] = Field(default_factory=list)
    model_available: bool = False
    model_source: str | None = None
    message: str | None = None


class CreateSessionRequest(BaseModel):
    initial_request: str = Field(min_length=1, max_length=MAX_INITIAL_REQUEST_CHARS)
    title: str | None = Field(default=None, max_length=MAX_SESSION_TITLE_CHARS)


class CreateSessionFromTemplateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_SESSION_TITLE_CHARS)


class AnswerClarificationRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_CLARIFICATION_ANSWER_CHARS)


class EditDraftRequest(BaseModel):
    instruction: str | None = Field(default=None, max_length=MAX_EDIT_INSTRUCTION_CHARS)
    body: str | None = Field(default=None, max_length=MAX_DRAFT_BODY_CHARS)

    @model_validator(mode="after")
    def require_instruction_or_body(self) -> Self:
        if self.body is not None:
            if not self.body.strip():
                msg = "Draft body cannot be empty"
                raise ValueError(msg)
            return self
        if not (self.instruction or "").strip():
            msg = "Provide an edit instruction or a replacement draft body"
            raise ValueError(msg)
        return self


class GenerateArtifactsRequest(BaseModel):
    include_pdf: bool = True
    export_folder_label: str | None = Field(
        default=None,
        max_length=MAX_EXPORT_FOLDER_LABEL_CHARS,
        description="Optional export folder label; defaults to the session title.",
    )


class FinalizeSessionRequest(BaseModel):
    acknowledge_first_shot_risk: bool = Field(
        default=False,
        description=(
            "When true, finalize even if first-shot contract checklist has gaps "
            "(examples, failure modes, acceptance cues)."
        ),
    )


class SessionSummary(BaseModel):
    id: UUID
    title: str
    state: SessionState
    current_draft_id: UUID | None
    prompt_id: str | None = None
    template_source_session_id: UUID | None = None
    clarification_turn: int
    created_at: datetime
    updated_at: datetime


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    requirement_card: RequirementCard
    clarification_question: str | None = None
    clarification_field: str | None = None
    clarification_question_number: int | None = None
    clarification_total_questions: int | None = None
    clarification_quick_replies: list[str] | None = None
    clarification_quick_reply_guides: list[QuickReplyGuide] | None = None
    clarification_versions: list[ClarificationVersionText] | None = None
    clarification_can_finish: bool | None = None
    clarification_open_decisions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def identify_open_decisions(self):
        from prompt_piper_api.domain.application_requirements import material_open_decisions
        self.clarification_open_decisions = material_open_decisions(self.requirement_card)
        return self

    current_draft: PromptDraft | None = None
    revised_draft: PromptDraft | None = None
    semantic_diff: str | None = None
    change_summary: str | None = None
    edit_intent: EditIntent | None = None
    updated_requirement_card: RequirementCard | None = None
    prompt_id: str | None = None
    registry_warning: str | None = None
    similarity_warning: str | None = None
    similarity_matches: list[SimilarityMatch] = Field(default_factory=list)
    optimization_result: OptimizationResult | None = None
    pre_inference_metrics: PreInferenceMetrics | None = None
    inference_result: SendToInferenceResult | None = None
    artifact_manifest: ArtifactManifest | None = None
    artifact_warning: str | None = None
    export_id: str | None = None
    container_export_path: str | None = None
    expected_host_export_path: str | None = None
    manifest_path: str | None = None
    generated_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    first_shot_readiness: FirstShotReadiness | None = None
    quality_gate_warnings: list[str] = Field(default_factory=list)


def to_session_summary(record: SessionRecord) -> SessionSummary:
    session = record.session
    return SessionSummary(
        id=session.id,
        title=session.title,
        state=session.state,
        current_draft_id=session.current_draft_id,
        prompt_id=session.prompt_id,
        template_source_session_id=session.template_source_session_id,
        clarification_turn=record.clarification_turn,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _clarification_can_finish(record: SessionRecord) -> bool | None:
    if record.session.state != SessionState.CLARIFYING:
        return None
    card = record.session.requirement_card
    missing = ClarificationQuestionRanker().missing_fields(card)
    if not missing:
        return True
    return all(field_name in card.unresolved_fields for field_name in missing)


def _clarification_from_pending(record: SessionRecord) -> dict[str, object | None]:
    pending = record.pending_clarification
    can_finish = _clarification_can_finish(record)
    if pending is None:
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
        "clarification_question": pending.question,
        "clarification_field": pending.field_name,
        "clarification_question_number": pending.question_number,
        "clarification_total_questions": pending.total_questions,
        "clarification_quick_replies": pending.quick_reply_options,
        "clarification_quick_reply_guides": pending.quick_reply_guides,
        "clarification_versions": pending.versions,
        "clarification_can_finish": can_finish,
    }


def to_session_response(result: SessionActionResult) -> SessionDetailResponse:
    record = result.record
    pending = record.pending_clarification
    revised = result.revised_draft or result.draft or record.current_draft
    clarification = {
        "clarification_question": result.clarification_question
        or (pending.question if pending else None),
        "clarification_field": result.clarification_field
        or (pending.field_name if pending else None),
        "clarification_question_number": result.clarification_question_number
        or (pending.question_number if pending else None),
        "clarification_total_questions": result.clarification_total_questions
        or (pending.total_questions if pending else None),
        "clarification_quick_replies": result.clarification_quick_replies
        or (pending.quick_reply_options if pending else None),
        "clarification_quick_reply_guides": result.clarification_quick_reply_guides
        if result.clarification_quick_reply_guides is not None
        else (pending.quick_reply_guides if pending else None),
        "clarification_versions": result.clarification_versions
        if result.clarification_versions is not None
        else (pending.versions if pending else None),
        "clarification_can_finish": result.clarification_can_finish,
    }
    return SessionDetailResponse(
        session=to_session_summary(record),
        requirement_card=result.updated_requirement_card or record.session.requirement_card,
        current_draft=revised,
        revised_draft=result.revised_draft,
        semantic_diff=result.semantic_diff,
        change_summary=result.change_summary,
        edit_intent=result.edit_intent,
        updated_requirement_card=result.updated_requirement_card,
        prompt_id=result.prompt_id or record.session.prompt_id,
        registry_warning=result.registry_warning,
        similarity_warning=result.similarity_warning,
        similarity_matches=result.similarity_matches,
        optimization_result=result.optimization_result or record.optimization_result,
        pre_inference_metrics=result.pre_inference_metrics or record.pre_inference_metrics,
        inference_result=result.inference_result or record.inference_result,
        artifact_manifest=(
            result.artifact_result.manifest
            if result.artifact_result is not None
            else (
                record.artifact_result.manifest if record.artifact_result is not None else None
            )
        ),
        artifact_warning=(
            "; ".join(result.artifact_result.warnings)
            if result.artifact_result is not None and result.artifact_result.warnings
            else result.artifact_warning
        ),
        export_id=result.artifact_result.export_id if result.artifact_result else None,
        container_export_path=(
            result.artifact_result.container_export_path if result.artifact_result else None
        ),
        expected_host_export_path=(
            result.artifact_result.expected_host_export_path if result.artifact_result else None
        ),
        manifest_path=result.artifact_result.manifest_path if result.artifact_result else None,
        generated_files=(
            result.artifact_result.generated_files if result.artifact_result else []
        ),
        warnings=result.artifact_result.warnings if result.artifact_result else [],
        first_shot_readiness=(
            result.first_shot_readiness
            or assess_first_shot_readiness(
                result.updated_requirement_card or record.session.requirement_card
            )
        ),
        quality_gate_warnings=list(result.quality_gate_warnings),
        **clarification,
    )


def to_session_detail(record: SessionRecord) -> SessionDetailResponse:
    return SessionDetailResponse(
        session=to_session_summary(record),
        requirement_card=record.session.requirement_card,
        current_draft=record.current_draft,
        optimization_result=record.optimization_result,
        pre_inference_metrics=record.pre_inference_metrics,
        inference_result=record.inference_result,
        artifact_manifest=(
            record.artifact_result.manifest if record.artifact_result is not None else None
        ),
        first_shot_readiness=assess_first_shot_readiness(record.session.requirement_card),
        **_clarification_from_pending(record),
    )

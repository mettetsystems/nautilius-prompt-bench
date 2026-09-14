from pydantic import BaseModel, Field

from prompt_piper_api.domain.artifacts import ArtifactGenerationResult
from prompt_piper_api.domain.draft import PromptDraft
from prompt_piper_api.domain.inference import SendToInferenceResult
from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.session import PromptSession
from prompt_piper_api.domain.similarity import SimilarityCheckResult
from prompt_piper_api.services.clarification_question_ranker import ClarificationQuestion


class SessionRecord(BaseModel):
    """Persisted aggregate for one prompt design session."""

    session: PromptSession
    initial_request: str = Field(default="", description="Original intake text for this session.")
    drafts: list[PromptDraft] = Field(default_factory=list)
    pending_clarification: ClarificationQuestion | None = None
    clarification_turn: int = Field(default=0, ge=0)
    asked_clarification_fields: list[str] = Field(default_factory=list)
    last_clarification_answer: str | None = None
    clarification_suggestions: list[dict] = Field(default_factory=list)
    edit_unresolved_asked: list[str] = Field(
        default_factory=list,
        description="Unresolved fields already asked during the current edit-pass queue.",
    )
    edit_unresolved_total: int = Field(
        default=0,
        ge=0,
        description="Size of the unresolved queue when the current edit pass started.",
    )
    optimization_result: OptimizationResult | None = None
    similarity_result: SimilarityCheckResult | None = None
    pre_inference_metrics: PreInferenceMetrics | None = None
    artifact_result: ArtifactGenerationResult | None = None
    inference_result: SendToInferenceResult | None = None

    @property
    def current_draft(self) -> PromptDraft | None:
        if self.session.current_draft_id is None:
            return None
        for draft in self.drafts:
            if draft.id == self.session.current_draft_id:
                return draft
        return None

    def add_draft(self, draft: PromptDraft) -> PromptDraft:
        self.drafts.append(draft)
        self.session.current_draft_id = draft.id
        self.session.touch()
        return draft

from pydantic import BaseModel, Field

from prompt_piper_api.domain.precision import VagueLanguageFinding
from prompt_piper_api.services.precision_suggestion_service import (
    PrecisionSuggestions,
    PrecisionSuggestionSource,
)
from prompt_piper_api.services.semantic_precision import PRECISION_THRESHOLD


class PrecisionReviewResponse(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(default=PRECISION_THRESHOLD, ge=0.0, le=1.0)
    vague_language_count: int = Field(ge=0)
    findings: list[VagueLanguageFinding] = Field(default_factory=list)
    llm_available: bool = False
    lexicon_available: bool = False
    vector_index_available: bool = False
    refinement_available: bool = False
    optimized_body: str = ""


class PrecisionSuggestRequest(BaseModel):
    finding_id: str = Field(min_length=1)
    use_llm: bool = True


class ApplyPrecisionReplacementRequest(BaseModel):
    finding_id: str = Field(min_length=1)
    replacement: str = Field(min_length=1, max_length=500)


class PrecisionSuggestResponse(BaseModel):
    finding_id: str
    suggested_replacements: list[str] = Field(default_factory=list)
    model_available: bool = False
    source: PrecisionSuggestionSource = PrecisionSuggestionSource.NONE
    message: str | None = None

    @classmethod
    def from_service(cls, payload: PrecisionSuggestions) -> "PrecisionSuggestResponse":
        return cls(
            finding_id=payload.finding_id,
            suggested_replacements=payload.suggested_replacements,
            model_available=payload.model_available,
            source=payload.source,
            message=payload.message,
        )

from pydantic import BaseModel, Field


class PreInferenceMetrics(BaseModel):
    """Metrics computed before any external model inference."""

    requirement_capture_score: float = Field(ge=0.0, le=1.0)
    unspecified_field_honesty: float = Field(ge=0.0, le=1.0)
    instruction_clarity: float = Field(ge=0.0, le=1.0)
    hard_conflict_count: int = Field(ge=0)
    format_adherence: float = Field(ge=0.0, le=1.0)
    token_cost_estimate: int = Field(ge=0)
    richness_score: float = Field(ge=0.0, le=1.0)
    density_score: float = Field(ge=0.0, le=1.0)
    efficiency_score: float = Field(ge=0.0, le=1.0)
    denoising_score: float = Field(ge=0.0, le=1.0)
    deconfliction_score: float = Field(ge=0.0, le=1.0)
    semantic_precision_score: float = Field(default=1.0, ge=0.0, le=1.0)
    vague_language_count: int = Field(default=0, ge=0)
    first_shot_readiness_score: float = Field(default=1.0, ge=0.0, le=1.0)
    first_shot_ready: bool = Field(default=True)
    section_coverage: int = Field(default=0, ge=0)


class QualityGateResult(BaseModel):
    passed: bool
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: PreInferenceMetrics
    regression_loss_rate: float | None = None
    regression_cases_run: int = 0
    safety_failures: list[str] = Field(default_factory=list)

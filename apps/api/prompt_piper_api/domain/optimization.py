from enum import StrEnum

from pydantic import BaseModel, Field


class ConstraintSlot(StrEnum):
    OBJECTIVE = "objective"
    AUDIENCE = "audience"
    SCOPE = "scope"
    MUST_CITE = "must_cite"
    SOURCE_LIMIT = "source_limit"
    ARTIFACT_REQUIRED = "artifact_required"
    FINAL_VENDOR = "final_vendor"
    TOKEN_BUDGET = "token_budget"
    VERBOSITY = "verbosity"
    FORMAT = "format"
    EXCLUSIONS = "exclusions"


class DetectedConflict(BaseModel):
    left_instruction: str
    right_instruction: str
    description: str
    requires_human_decision: bool = True
    resolved: bool = False
    resolution: str | None = None


class ConstraintGraph(BaseModel):
    slots: dict[str, list[str]] = Field(default_factory=dict)
    binding_instructions: list[str] = Field(default_factory=list)
    contradictions: list[DetectedConflict] = Field(default_factory=list)


class OptimizationTargetMetrics(BaseModel):
    clarity: float = Field(default=0.0, ge=0.0, le=1.0)
    richness: float = Field(ge=0.0, le=1.0)
    density: float = Field(ge=0.0, le=1.0)
    efficiency: float = Field(ge=0.0, le=1.0)
    denoising: float = Field(ge=0.0, le=1.0)
    deconfliction: float = Field(ge=0.0, le=1.0)


class OptimizationMetrics(BaseModel):
    original_token_count: int = Field(ge=0)
    optimized_token_count: int = Field(ge=0)
    token_reduction_pct: float = Field(ge=0.0)
    constraints_per_token: float = Field(ge=0.0)
    targets: OptimizationTargetMetrics


class OptimizationChangeLog(BaseModel):
    removed: list[str] = Field(default_factory=list)
    compressed: list[str] = Field(default_factory=list)
    clarified: list[str] = Field(default_factory=list)
    conflicts_resolved: list[str] = Field(default_factory=list)
    precision_improvements: list[str] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    original_body: str
    optimized_body: str
    constraint_graph: ConstraintGraph
    metrics: OptimizationMetrics
    changes: OptimizationChangeLog
    hard_conflicts: list[DetectedConflict] = Field(default_factory=list)
    export_ready: bool = False
    approved: bool = False
    passes_completed: list[str] = Field(default_factory=list)

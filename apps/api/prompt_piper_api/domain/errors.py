from enum import StrEnum

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    """Stable machine-readable API error codes."""

    SESSION_NOT_FOUND = "session_not_found"
    PROMPT_NOT_FOUND = "prompt_not_found"
    FILE_NOT_FOUND = "file_not_found"
    INVALID_STATE = "invalid_state"
    VALIDATION_ERROR = "validation_error"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    FIRST_SHOT_RISK = "first_shot_risk"
    INFERENCE_BLOCKED = "inference_blocked"
    INFERENCE_FAILED = "inference_failed"
    LLM_UNAVAILABLE = "llm_unavailable"
    REGISTRY_WRITE_FAILED = "registry_write_failed"
    ARTIFACT_EXISTS = "artifact_exists"
    INVALID_PROMPT_ID = "invalid_prompt_id"
    INVALID_PATH = "invalid_path"
    INTERNAL_ERROR = "internal_error"


class ApiErrorResponse(BaseModel):
    """Structured error body returned by all API error responses."""

    code: ErrorCode
    message: str
    current_state: str | None = None
    action: str | None = None
    reason: str | None = None
    details: dict[str, str] = Field(default_factory=dict)

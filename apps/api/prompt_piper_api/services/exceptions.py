from prompt_piper_api.domain.errors import ErrorCode


class AppError(Exception):
    """Base class for domain errors mapped to structured API responses."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500

    def __init__(self, message: str, **context: str) -> None:
        self.context = context
        super().__init__(message)


class SessionNotFoundError(AppError):
    code = ErrorCode.SESSION_NOT_FOUND
    http_status = 404

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session {session_id} not found.", session_id=session_id)


class SessionLoadError(AppError):
    """Persisted session JSON does not match the current requirement-card schema."""

    code = ErrorCode.VALIDATION_ERROR
    http_status = 422

    def __init__(self, session_id: str) -> None:
        super().__init__(
            "This session was saved with an older requirement-card schema and cannot "
            "be loaded. Start a new session from the same initial prompt.",
            session_id=session_id,
        )


class PromptNotFoundError(AppError):
    code = ErrorCode.PROMPT_NOT_FOUND
    http_status = 404

    def __init__(self, prompt_id: str) -> None:
        super().__init__("Prompt not found.", prompt_id=prompt_id)


class StateTransitionError(AppError):
    code = ErrorCode.INVALID_STATE
    http_status = 409

    def __init__(self, message: str, *, current_state: str, action: str) -> None:
        self.current_state = current_state
        self.action = action
        super().__init__(message, current_state=current_state, action=action)


class InvalidPromptIdError(AppError):
    code = ErrorCode.INVALID_PROMPT_ID
    http_status = 400

    def __init__(self, message: str, *, prompt_id: str) -> None:
        super().__init__(message, prompt_id=prompt_id)


class InvalidPathError(AppError):
    code = ErrorCode.INVALID_PATH
    http_status = 400

    def __init__(self, message: str, *, filename: str) -> None:
        super().__init__(message, filename=filename)


class RegistryWriteError(AppError):
    code = ErrorCode.REGISTRY_WRITE_FAILED
    http_status = 500

    def __init__(self, message: str, *, prompt_id: str) -> None:
        super().__init__(message, prompt_id=prompt_id)


class ArtifactExistsError(AppError):
    code = ErrorCode.ARTIFACT_EXISTS
    http_status = 409

    def __init__(self, message: str, *, prompt_id: str, version: int) -> None:
        super().__init__(message, prompt_id=prompt_id, version=str(version))


class InferenceCallError(AppError):
    code = ErrorCode.INFERENCE_FAILED
    http_status = 502

    def __init__(self, message: str, *, reason: str = "provider_error") -> None:
        super().__init__(message, reason=reason)


class FirstShotRiskError(AppError):
    """Finalize blocked until the user acknowledges first-shot contract gaps."""

    code = ErrorCode.FIRST_SHOT_RISK
    http_status = 409

    def __init__(self, message: str, *, risks: list[str]) -> None:
        self.risks = risks
        details = {f"risk_{index}": risk for index, risk in enumerate(risks[:12])}
        super().__init__(message, reason="acknowledge_first_shot_risk", **details)

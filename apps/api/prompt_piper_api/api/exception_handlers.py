from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from prompt_piper_api.domain.errors import ApiErrorResponse, ErrorCode
from prompt_piper_api.llm.base import LLMError
from prompt_piper_api.services.exceptions import AppError, StateTransitionError
from prompt_piper_api.services.external_inference_service import ExternalInferenceBlockedError
from prompt_piper_api.services.logging_config import get_logger, redact_secrets

logger = get_logger(__name__)


def _error_response(
    *,
    status_code: int,
    code: ErrorCode,
    message: str,
    current_state: str | None = None,
    action: str | None = None,
    reason: str | None = None,
    details: dict[str, str] | None = None,
) -> JSONResponse:
    body = ApiErrorResponse(
        code=code,
        message=message,
        current_state=current_state,
        action=action,
        reason=reason,
        details=details or {},
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        current_state = exc.context.get("current_state")
        if current_state is None and hasattr(exc, "current_state"):
            current_state = getattr(exc, "current_state", None)
        action = exc.context.get("action")
        if action is None and hasattr(exc, "action"):
            action = getattr(exc, "action", None)
        reason = exc.context.get("reason")
        reserved = {"current_state", "action", "reason"}
        details = {
            key: value
            for key, value in exc.context.items()
            if key not in reserved and isinstance(value, str)
        }
        logger.log(
            logging.WARNING if exc.http_status < 500 else logging.ERROR,
            "app_error",
            extra={"code": exc.code.value, "action": action},
        )
        return _error_response(
            status_code=exc.http_status,
            code=exc.code,
            message=str(exc),
            current_state=current_state,
            action=action,
            reason=reason,
            details=details or None,
        )

    @app.exception_handler(StateTransitionError)
    async def handle_state_error(_request: Request, exc: StateTransitionError) -> JSONResponse:
        return _error_response(
            status_code=exc.http_status,
            code=exc.code,
            message=str(exc),
            current_state=exc.current_state,
            action=exc.action,
        )

    @app.exception_handler(ExternalInferenceBlockedError)
    async def handle_inference_blocked(
        _request: Request, exc: ExternalInferenceBlockedError
    ) -> JSONResponse:
        return _error_response(
            status_code=403,
            code=ErrorCode.INFERENCE_BLOCKED,
            message=str(exc),
            reason=exc.reason,
        )

    @app.exception_handler(LLMError)
    async def handle_llm_error(_request: Request, exc: LLMError) -> JSONResponse:
        logger.error("llm_error", extra={"message": redact_secrets(str(exc))})
        return _error_response(
            status_code=503,
            code=ErrorCode.LLM_UNAVAILABLE,
            message="Local model request failed. Rule-based fallback may apply.",
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        _ = exc
        return _error_response(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            reason="validation_error",
        )

    @app.exception_handler(ValidationError)
    async def handle_validation(_request: Request, _exc: ValidationError) -> JSONResponse:
        return _error_response(
            status_code=422,
            code=ErrorCode.VALIDATION_ERROR,
            message="Validation failed.",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", exc_info=exc)
        return _error_response(
            status_code=500,
            code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred.",
        )

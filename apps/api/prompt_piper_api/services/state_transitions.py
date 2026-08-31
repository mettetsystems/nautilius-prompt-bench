from __future__ import annotations

from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.exceptions import StateTransitionError

SessionAction = str

ACTION_ANSWER = "answer"
ACTION_COMPLETE_CLARIFICATION = "complete_clarification"
ACTION_EDIT = "edit"
ACTION_FINALIZE = "finalize"
ACTION_OPTIMIZE = "optimize"
ACTION_APPROVE_OPTIMIZATION = "approve_optimization"
ACTION_GENERATE_ARTIFACTS = "generate_artifacts"
ACTION_SEND_TO_INFERENCE = "send_to_inference"
ACTION_REOPEN_EDIT = "reopen_edit"
ACTION_RERUN_SIMILARITY = "rerun_similarity"
ACTION_RERUN_OPTIMIZE = "rerun_optimize"
ACTION_PRECISION_SUGGEST = "precision_suggest"
ACTION_PRECISION_APPLY = "precision_apply"
ACTION_CREATE_FROM_TEMPLATE = "create_from_template"

_POST_EDIT_STATES = frozenset(
    {
        SessionState.SIMILARITY_CHECK,
        SessionState.OPTIMIZATION,
        SessionState.APPROVAL,
        SessionState.ARTIFACT_GENERATION,
    }
)

_POST_SIMILARITY_STATES = frozenset(
    {
        SessionState.SIMILARITY_CHECK,
        SessionState.OPTIMIZATION,
        SessionState.APPROVAL,
        SessionState.ARTIFACT_GENERATION,
    }
)

_POST_OPTIMIZATION_STATES = frozenset(
    {
        SessionState.OPTIMIZATION,
        SessionState.APPROVAL,
        SessionState.ARTIFACT_GENERATION,
    }
)

_ALLOWED: dict[SessionAction, frozenset[SessionState]] = {
    ACTION_ANSWER: frozenset({SessionState.CLARIFYING, SessionState.EDIT}),
    ACTION_COMPLETE_CLARIFICATION: frozenset({SessionState.CLARIFYING}),
    ACTION_EDIT: frozenset({SessionState.EDIT}),
    ACTION_FINALIZE: frozenset({SessionState.EDIT}),
    ACTION_OPTIMIZE: frozenset({SessionState.SIMILARITY_CHECK}),
    ACTION_APPROVE_OPTIMIZATION: frozenset({SessionState.OPTIMIZATION}),
    ACTION_GENERATE_ARTIFACTS: frozenset({SessionState.APPROVAL}),
    ACTION_SEND_TO_INFERENCE: frozenset({SessionState.APPROVAL, SessionState.EXPORTED}),
    ACTION_REOPEN_EDIT: _POST_EDIT_STATES,
    ACTION_RERUN_SIMILARITY: _POST_SIMILARITY_STATES,
    ACTION_RERUN_OPTIMIZE: _POST_OPTIMIZATION_STATES,
    ACTION_CREATE_FROM_TEMPLATE: frozenset({SessionState.EXPORTED}),
    ACTION_PRECISION_SUGGEST: frozenset({SessionState.OPTIMIZATION}),
    ACTION_PRECISION_APPLY: frozenset({SessionState.OPTIMIZATION}),
}


def require_session_open(session_state: SessionState, action: SessionAction) -> None:
    """Raise when a completed session must stay immutable for auditability."""
    if session_state is SessionState.EXPORTED:
        raise StateTransitionError(
            "This session is complete and closed for auditability. "
            "Create a new session from this template instead.",
            current_state=session_state.value,
            action=action,
        )


def require_state(session_state: SessionState, action: SessionAction, message: str) -> None:
    """Raise StateTransitionError when action is invalid for the current state."""
    allowed = _ALLOWED.get(action)
    if allowed is None or session_state not in allowed:
        raise StateTransitionError(
            message,
            current_state=session_state.value,
            action=action,
        )

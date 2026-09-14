from __future__ import annotations

from uuid import UUID

from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.session_service import SessionService


def drive_session_to_edit(
    service: SessionService,
    session_id: UUID,
    *,
    answers: list[str] | None = None,
) -> None:
    """Answer clarifications until the session reaches edit state."""
    if answers:
        for answer in answers:
            result = service.answer_clarification(session_id, answer)
            if result.record.session.state is SessionState.EDIT:
                return

    while True:
        record = service.get_session(session_id)
        if record.session.state is SessionState.EDIT:
            return
        if service._can_complete_clarification_early(record):
            service.complete_clarification(session_id)
            return
        service.answer_clarification(session_id, "unspecified")

"""Edit-pass unresolved field question queue."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_client_session_to_edit, drive_session_to_edit


@pytest.fixture
def service() -> SessionService:
    return SessionService(llm=None)


def test_edit_seeds_unresolved_question_queue(service: SessionService) -> None:
    created = service.create_session(
        initial_request="Build a FastAPI endpoint with typed JSON and pytest coverage.",
    )
    drive_session_to_edit(service, created.record.session.id)
    record = service.get_session(created.record.session.id)

    assert record.session.state is SessionState.EDIT
    unresolved = record.session.requirement_card.unresolved_fields
    assert unresolved, "expected unspecified fields after clarify-with-unspecified"
    assert record.pending_clarification is not None
    assert record.pending_clarification.field_name in unresolved
    assert record.edit_unresolved_total == len(unresolved)
    assert record.edit_unresolved_asked == [record.pending_clarification.field_name]


def test_edit_answer_regenerates_draft_and_advances_queue(service: SessionService) -> None:
    created = service.create_session(
        initial_request="Write a coding prompt for a typed FastAPI POST /users handler.",
    )
    drive_session_to_edit(service, created.record.session.id)
    record = service.get_session(created.record.session.id)
    pending = record.pending_clarification
    assert pending is not None
    field_name = pending.field_name
    assert record.current_draft is not None
    version_before = record.current_draft.version

    answered = service.answer_clarification(
        created.record.session.id,
        "Use FastAPI + Pydantic v2 with OpenAPI examples",
    )

    assert answered.record.session.state is SessionState.EDIT
    assert answered.draft is not None
    assert answered.draft.version == version_before + 1
    assert field_name not in answered.record.session.requirement_card.unresolved_fields

    next_pending = answered.record.pending_clarification
    if next_pending is not None:
        assert next_pending.field_name != field_name
        assert next_pending.field_name in answered.record.session.requirement_card.unresolved_fields


def test_edit_unspecified_advances_without_infinite_loop(service: SessionService) -> None:
    created = service.create_session(
        initial_request="Coding prompt for a pytest-covered FastAPI CRUD router.",
    )
    drive_session_to_edit(service, created.record.session.id)
    session_id = created.record.session.id

    seen: list[str] = []
    for _ in range(40):
        record = service.get_session(session_id)
        pending = record.pending_clarification
        if pending is None:
            break
        seen.append(pending.field_name)
        service.answer_clarification(session_id, "unspecified")

    assert seen, "expected at least one edit-queue question"
    assert len(seen) == len(set(seen)), "unspecified must not re-ask the same field in one pass"
    final = service.get_session(session_id)
    assert final.session.state is SessionState.EDIT
    assert final.pending_clarification is None


def test_edit_suggest_works_with_pending_question(client: TestClient) -> None:
    created = client.post(
        "/sessions",
        json={"initial_request": "Design a FastAPI user-create coding prompt with pytest."},
    )
    assert created.status_code in (200, 201)
    session_id = created.json()["session"]["id"]
    edit_payload = drive_client_session_to_edit(client, session_id)
    assert edit_payload["session"]["state"] == SessionState.EDIT
    assert edit_payload.get("clarification_field")

    suggest = client.post(f"/sessions/{session_id}/clarify/suggest")
    assert suggest.status_code == 200
    body = suggest.json()
    assert "suggested_answers" in body or "model_available" in body

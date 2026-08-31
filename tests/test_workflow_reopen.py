from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.exceptions import StateTransitionError
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_client_session_to_edit, drive_session_to_edit


@pytest.fixture
def service() -> SessionService:
    return SessionService(llm=None)


def _session_at_similarity(client: TestClient) -> tuple[str, dict]:
    create = client.post("/sessions", json={"initial_request": "Weekly status update prompt"})
    session_id = create.json()["session"]["id"]
    drive_client_session_to_edit(
        client,
        session_id,
        answers=["Engineering managers", "Bulleted summary with risks"],
    )
    finalized = client.post(f"/sessions/{session_id}/finalize", json={"acknowledge_first_shot_risk": True})
    assert finalized.status_code == 200
    return session_id, finalized.json()


def _session_exported(client: TestClient) -> tuple[str, dict]:
    from prompt_piper_api.routes import sessions as sessions_routes

    session_id, _ = _session_at_similarity(client)
    service = sessions_routes.get_session_service()
    service.optimize(session_id)
    record = service.get_session(session_id)
    record.session.state = SessionState.EXPORTED
    if record.current_draft is not None:
        record.current_draft.is_canonical = True
        record.current_draft.is_frozen = True
    service._save(record)
    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.status_code == 200
    return session_id, fetched.json()


def test_reopen_for_edit_restores_edit_state(client: TestClient) -> None:
    session_id, finalized = _session_at_similarity(client)
    assert finalized["session"]["state"] == SessionState.SIMILARITY_CHECK
    assert finalized["current_draft"]["is_frozen"] is True

    reopened = client.post(f"/sessions/{session_id}/workflow/reopen/edit")
    assert reopened.status_code == 200
    body = reopened.json()

    assert body["session"]["state"] == SessionState.EDIT
    assert body["current_draft"]["is_frozen"] is False
    assert body["current_draft"]["is_canonical"] is False
    assert body["optimization_result"] is None
    assert body["similarity_matches"] == []

    edited = client.post(
        f"/sessions/{session_id}/edit",
        json={"instruction": "Make the tone more analytical"},
    )
    assert edited.status_code == 200
    assert edited.json()["current_draft"]["version"] == finalized["current_draft"]["version"] + 1


def test_reopen_for_edit_not_allowed_before_finalization(client: TestClient) -> None:
    payload = drive_client_session_to_edit(
        client,
        client.post("/sessions", json={"initial_request": "Support macro prompt"}).json()[
            "session"
        ]["id"],
        answers=["Support agents", "Short reply template"],
    )
    session_id = payload["session"]["id"]

    reopened = client.post(f"/sessions/{session_id}/workflow/reopen/edit")
    assert reopened.status_code == 409
    assert reopened.json()["action"] == "reopen_edit"


def test_reopen_for_edit_blocked_on_completed_session(client: TestClient) -> None:
    session_id, _ = _session_exported(client)

    reopened = client.post(f"/sessions/{session_id}/workflow/reopen/edit")
    assert reopened.status_code == 409
    assert reopened.json()["action"] == "reopen_edit"
    assert "closed for auditability" in reopened.json()["message"]


def test_rerun_similarity_from_optimization(client: TestClient) -> None:
    session_id, _ = _session_at_similarity(client)

    optimized = client.post(f"/sessions/{session_id}/optimize")
    assert optimized.status_code == 200
    assert optimized.json()["session"]["state"] == SessionState.OPTIMIZATION

    rerun = client.post(f"/sessions/{session_id}/workflow/rerun/similarity")
    assert rerun.status_code == 200
    body = rerun.json()

    assert body["session"]["state"] == SessionState.SIMILARITY_CHECK
    assert body["optimization_result"] is None
    assert "similarity_matches" in body


def test_rerun_optimization_from_approval_state(service: SessionService) -> None:
    created = service.create_session(initial_request="Create a changelog prompt")
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Developers", "Markdown changelog entries"],
    )
    service.finalize(session_id, acknowledge_first_shot_risk=True)
    service.optimize(session_id)

    record = service.get_session(session_id)
    assert record.session.state is SessionState.OPTIMIZATION
    assert record.optimization_result is not None

    record.session.state = SessionState.APPROVAL
    record.optimization_result.approved = True
    service._save(record)

    rerun = service.rerun_optimization(session_id)
    assert rerun.record.session.state is SessionState.OPTIMIZATION
    assert rerun.optimization_result is not None
    assert rerun.optimization_result.approved is False


def test_reopen_for_edit_service(service: SessionService) -> None:
    created = service.create_session(initial_request="Draft a product FAQ prompt")
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Support agents", "Question and answer pairs"],
    )
    service.finalize(session_id, acknowledge_first_shot_risk=True)

    with pytest.raises(StateTransitionError):
        service.edit_draft(session_id, "Make it shorter")

    reopened = service.reopen_for_edit(session_id)
    assert reopened.record.session.state is SessionState.EDIT

    edited = service.edit_draft(session_id, "Make it shorter")
    assert edited.draft is not None
    assert edited.draft.is_frozen is False


def test_create_session_from_template(client: TestClient) -> None:
    session_id, exported = _session_exported(client)
    assert exported["session"]["state"] == SessionState.EXPORTED

    created = client.post(f"/sessions/{session_id}/template")
    assert created.status_code == 201
    body = created.json()

    assert body["session"]["id"] != session_id
    assert body["session"]["state"] == SessionState.EDIT
    assert body["session"]["template_source_session_id"] == session_id
    assert body["current_draft"] is not None
    assert body["current_draft"]["version"] == 1
    assert body["current_draft"]["is_frozen"] is False
    assert "from template" in body["session"]["title"].lower()


def test_create_session_from_template_requires_completed_session(client: TestClient) -> None:
    session_id, _ = _session_at_similarity(client)

    created = client.post(f"/sessions/{session_id}/template")
    assert created.status_code == 409
    assert created.json()["action"] == "create_from_template"

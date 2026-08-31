import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.domain.edit_intent import EditIntent
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.exceptions import StateTransitionError
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_client_session_to_edit, drive_session_to_edit


@pytest.fixture
def service() -> SessionService:
    return SessionService(llm=None)


def _create_and_answer_to_draft(client: TestClient, initial_request: str) -> dict:
    create = client.post("/sessions", json={"initial_request": initial_request})
    assert create.status_code == 201
    session_id = create.json()["session"]["id"]
    assert create.json()["session"]["state"] == SessionState.CLARIFYING
    assert create.json()["clarification_question"]

    return drive_client_session_to_edit(
        client,
        session_id,
        answers=["Product managers", "Bulleted summary with risks and next steps"],
    )


def test_clarification_loop_before_draft_generation(client: TestClient) -> None:
    payload = _create_and_answer_to_draft(
        client,
        "Summarize customer interview notes\nenvironment: Python with FastAPI",
    )

    assert payload["session"]["state"] == SessionState.EDIT
    assert payload["current_draft"] is not None
    assert payload["current_draft"]["version"] == 1
    assert "# Prompt" not in payload["current_draft"]["body"]
    assert "unspecified" in payload["current_draft"]["body"].lower()


def test_edit_not_allowed_before_draft_exists(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Write a release note prompt"})
    session_id = create.json()["session"]["id"]

    edit = client.post(f"/sessions/{session_id}/edit", json={"instruction": "Make it shorter"})
    assert edit.status_code == 409
    assert edit.json()["action"] == "edit"


def test_finalize_not_allowed_before_edit_state(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Draft a support macro"})
    session_id = create.json()["session"]["id"]

    finalize = client.post(f"/sessions/{session_id}/finalize", json={"acknowledge_first_shot_risk": True})
    assert finalize.status_code == 409
    assert finalize.json()["action"] == "finalize"


def test_finalization_marks_canonical_draft(client: TestClient) -> None:
    payload = _create_and_answer_to_draft(client, "Create a weekly status update prompt")
    session_id = payload["session"]["id"]

    edit = client.post(
        f"/sessions/{session_id}/edit",
        json={"instruction": "Make it shorter and more formal"},
    )
    assert edit.status_code == 200
    assert edit.json()["semantic_diff"]

    finalize = client.post(f"/sessions/{session_id}/finalize", json={"acknowledge_first_shot_risk": True})
    assert finalize.status_code == 200
    body = finalize.json()

    assert body["session"]["state"] == SessionState.SIMILARITY_CHECK
    assert body["current_draft"]["is_canonical"] is True


def test_session_service_requires_draft_before_edit(service: SessionService) -> None:
    result = service.create_session(initial_request="Write onboarding email copy")
    session_id = result.record.session.id

    assert result.record.session.state is SessionState.CLARIFYING
    assert result.clarification_question

    with pytest.raises(StateTransitionError):
        service.edit_draft(session_id, "Make it shorter")

    first = service.answer_clarification(session_id, "New hires in their first week")
    assert first.record.session.state is SessionState.CLARIFYING
    assert first.clarification_question
    assert first.draft is None

    with pytest.raises(StateTransitionError):
        service.edit_draft(session_id, "Make it shorter")

    drive_session_to_edit(
        service,
        session_id,
        answers=["Short welcome email with next steps"],
    )
    record = service.get_session(session_id)
    assert record.session.state is SessionState.EDIT
    assert record.current_draft is not None
    assert record.current_draft.version == 1


def test_finalize_only_from_edit_state(service: SessionService) -> None:
    created = service.create_session(initial_request="Draft a changelog prompt")
    session_id = created.record.session.id

    with pytest.raises(StateTransitionError):
        service.finalize(session_id, acknowledge_first_shot_risk=True)


def test_edit_regenerates_draft_with_semantic_diff(service: SessionService) -> None:
    created = service.create_session(initial_request="Create a product FAQ prompt")
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Support agents", "Question and answer pairs"],
    )

    edited = service.edit_draft(session_id, "Make it shorter")
    assert edited.draft is not None
    assert edited.draft.version == 2
    assert edited.semantic_diff
    assert edited.edit_intent is EditIntent.TIGHTEN_LANGUAGE


def test_get_session_returns_current_question(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Help me prompt for code review"})
    session_id = create.json()["session"]["id"]

    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["clarification_question"]
    assert fetched.json()["session"]["state"] == SessionState.CLARIFYING

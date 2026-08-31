from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.exceptions import SessionLoadError, SessionNotFoundError
from prompt_piper_api.services.session_service import SessionService
from prompt_piper_api.services.session_store import FileSessionStore


def test_session_persists_across_service_instances(tmp_path: Path) -> None:
    store = FileSessionStore(tmp_path / "sessions")
    service = SessionService(llm=None, store=store)
    created = service.create_session(initial_request="Draft a release note prompt")
    session_id = created.record.session.id

    reloaded = SessionService(llm=None, store=store)
    record = reloaded.get_session(session_id)

    assert record.session.state is SessionState.CLARIFYING
    assert record.pending_clarification is not None
    assert created.clarification_field == record.pending_clarification.field_name


def test_get_session_survives_api_service_restart(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Draft a weekly status update prompt"})
    assert create.status_code == 201
    session_id = create.json()["session"]["id"]

    from prompt_piper_api.routes import sessions as sessions_routes

    sessions_routes._session_service = None

    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["session"]["id"] == session_id
    assert fetched.json()["session"]["state"] == SessionState.CLARIFYING.value


def test_file_session_store_delete_removes_json(tmp_path: Path) -> None:
    store = FileSessionStore(tmp_path / "sessions")
    service = SessionService(llm=None, store=store)
    created = service.create_session(initial_request="Draft a release note prompt")
    session_id = created.record.session.id
    path = tmp_path / "sessions" / f"{session_id}.json"
    assert path.is_file()

    service.delete_session(session_id)

    assert not path.is_file()
    with pytest.raises(SessionNotFoundError):
        service.get_session(session_id)


def test_delete_session_api_removes_record(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Draft a weekly status update prompt"})
    assert create.status_code == 201
    session_id = create.json()["session"]["id"]

    deleted = client.post(f"/sessions/{session_id}/delete")
    assert deleted.status_code == 204

    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.status_code == 404
    assert fetched.json()["code"] == "session_not_found"

    missing = client.post("/sessions/00000000-0000-0000-0000-000000000099/delete")
    assert missing.status_code == 404
    assert missing.json()["code"] == "session_not_found"


def test_delete_session_also_accepts_http_delete(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Draft a weekly status update prompt"})
    assert create.status_code == 201
    session_id = create.json()["session"]["id"]

    deleted = client.delete(f"/sessions/{session_id}")
    assert deleted.status_code == 204

    fetched = client.get(f"/sessions/{session_id}")
    assert fetched.status_code == 404
    assert fetched.json()["code"] == "session_not_found"

    missing = client.delete("/sessions/00000000-0000-0000-0000-000000000099")
    assert missing.status_code == 404
    assert missing.json()["code"] == "session_not_found"


def test_file_session_store_rejects_legacy_card_schema(tmp_path: Path) -> None:
    session_id = uuid4()
    store = FileSessionStore(tmp_path / "sessions")
    path = tmp_path / "sessions" / f"{session_id}.json"
    path.write_text(
        """
        {
          "session": {
            "id": "%s",
            "title": "FlowBPM",
            "state": "clarifying",
            "requirement_card": {
              "technical_context": {"environment": ""},
              "core_task_scope": {"objective": "Build FlowBPM"}
            }
          },
          "initial_request": "Build FlowBPM"
        }
        """
        % session_id,
        encoding="utf-8",
    )
    try:
        store.get(session_id)
    except SessionLoadError as exc:
        assert "older requirement-card schema" in str(exc)
    else:
        raise AssertionError("expected SessionLoadError")


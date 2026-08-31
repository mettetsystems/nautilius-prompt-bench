from pathlib import Path
from uuid import uuid4

import pytest
from export_test_helpers import build_test_export_service
from fastapi.testclient import TestClient
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.main import app
from prompt_piper_api.services.exceptions import InvalidPathError, InvalidPromptIdError
from prompt_piper_api.services.git_registry_service import GitRegistryService, build_prompt_id
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.path_safety import validate_filename, validate_prompt_id
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_session_to_edit


def test_validate_prompt_id_rejects_traversal() -> None:
    with pytest.raises(InvalidPromptIdError):
        validate_prompt_id("../etc-passwd")
    with pytest.raises(InvalidPromptIdError):
        validate_prompt_id("bad id")


def test_validate_prompt_id_accepts_stable_format() -> None:
    session_id = uuid4()
    prompt_id = build_prompt_id("Implementation report", session_id)
    assert validate_prompt_id(prompt_id) == prompt_id


def test_validate_filename_rejects_path_segments() -> None:
    with pytest.raises(InvalidPathError):
        validate_filename("../secret.txt")


def test_registry_read_rejects_invalid_prompt_id(tmp_path: Path) -> None:
    registry = GitRegistryService(tmp_path / "registry")
    assert registry.load_metadata("../../etc/passwd") is None


def test_re_export_creates_new_unique_folder_without_overwriting(tmp_path: Path) -> None:
    registry_path = tmp_path / "registry"
    export_service = build_test_export_service(tmp_path)
    service = SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=None,
        optimizer=TokenOptimizationEngine(),
        artifact_export=export_service,
    )
    created = service.create_session(
        initial_request="Summarize weekly engineering status for leadership review.",
    )
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Engineering managers", "Bulleted summary with risks"],
    )
    record = service.get_session(session_id)
    record.session.requirement_card.objective = (
        "Summarize weekly engineering status for leadership review."
    )
    record.session.requirement_card.unresolved_fields = []
    record.drafts[-1].body = "\n".join(
        [
            "Technical Context",
            "-----------------",
            "Environment: Python with FastAPI and Pydantic",
            "",
            "Core Task and Scope",
            "-------------------",
            "Objective: Add FastAPI endpoint for weekly engineering status summaries.",
            "",
            "Inputs, Outputs, and Contracts",
            "------------------------------",
            "Output contract: JSON with blockers, owners, and next steps.",
        ]
    )
    service.finalize(session_id, acknowledge_first_shot_risk=True)
    service.optimize(session_id)
    service.approve_optimization(session_id)
    first = service.generate_artifacts(session_id)
    assert first.prompt_id

    record = service.get_session(session_id)
    record.session.state = SessionState.APPROVAL
    second = service.generate_artifacts(session_id)
    assert second.prompt_id == first.prompt_id

    first_dir = (
        Path(first.artifact_result.container_export_path) if first.artifact_result else None
    )
    second_dir = (
        Path(second.artifact_result.container_export_path) if second.artifact_result else None
    )
    assert first_dir is not None and second_dir is not None
    assert first_dir != second_dir
    assert (first_dir / "canonical_prompt.txt").is_file()
    assert (second_dir / "canonical_prompt.txt").is_file()


def test_structured_api_error_for_missing_session(client: TestClient | None = None) -> None:
    test_client = client or TestClient(app)
    missing_id = "00000000-0000-0000-0000-000000000099"
    response = test_client.get(f"/sessions/{missing_id}")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "session_not_found"
    assert "message" in body


def test_structured_state_error(client: TestClient | None = None) -> None:
    test_client = client or TestClient(app)
    created = test_client.post(
        "/sessions",
        json={"initial_request": "Draft a concise weekly status update prompt."},
    )
    session_id = created.json()["session"]["id"]
    response = test_client.post(f"/sessions/{session_id}/finalize", json={"acknowledge_first_shot_risk": True})
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "invalid_state"
    assert body["action"] == "finalize"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)

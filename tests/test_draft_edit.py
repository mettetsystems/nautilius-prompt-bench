from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.domain.edit_intent import EditIntent
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.draft_patch_service import DraftPatchService
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_client_session_to_edit, drive_session_to_edit


@pytest.fixture
def service() -> SessionService:
    return SessionService(llm=None)


def _enter_edit_state(
    service: SessionService,
    initial_request: str = "Draft a product FAQ prompt",
) -> UUID:
    created = service.create_session(initial_request=initial_request)
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Support agents", "Question and answer pairs"],
    )
    return session_id


def test_adding_requirement_updates_draft(service: SessionService) -> None:
    session_id = _enter_edit_state(service)
    before = service.get_session(session_id).current_draft
    assert before is not None

    edited = service.edit_draft(
        session_id,
        "Add requirement: prefer open-source tooling in recommendations",
    )

    assert edited.edit_intent is EditIntent.ADD_REQUIREMENT
    assert edited.revised_draft is not None
    assert edited.revised_draft.body != before.body
    assert (
        "prefer open-source tooling"
        in edited.updated_requirement_card.task_identity.additional_constraints[-1]
    )


def test_tone_change_updates_draft(service: SessionService) -> None:
    session_id = _enter_edit_state(service)
    before_body = service.get_session(session_id).current_draft.body

    edited = service.edit_draft(session_id, "Change tone to analytical")

    assert edited.edit_intent is EditIntent.CHANGE_TONE
    assert "analytical" in edited.updated_requirement_card.task_identity.additional_constraints[-1]
    assert "analytical" in edited.revised_draft.body.lower()
    assert edited.revised_draft.body != before_body


def test_output_shape_change_updates_draft(service: SessionService) -> None:
    session_id = _enter_edit_state(service)

    edited = service.edit_draft(session_id, "Change output shape to markdown table")

    assert edited.edit_intent is EditIntent.CHANGE_OUTPUT_SHAPE
    assert (
        edited.updated_requirement_card.agent_contract.completion_contract
        == "markdown table"
    )
    assert "markdown table" in edited.revised_draft.body


def test_semantic_diff_is_short_and_useful(service: SessionService) -> None:
    session_id = _enter_edit_state(service)

    edited = service.edit_draft(
        session_id,
        "Add constraint: prefer open-source tools and change tone to analytical",
    )

    assert edited.semantic_diff
    assert len(edited.semantic_diff) <= 200
    assert edited.semantic_diff.endswith(".")
    assert "Edit intent:" not in edited.semantic_diff
    diff_lower = edited.semantic_diff.lower()
    assert "analytical" in diff_lower or "open-source" in diff_lower


def test_old_draft_remains_versioned(service: SessionService) -> None:
    session_id = _enter_edit_state(service)
    record = service.get_session(session_id)
    original = record.current_draft
    assert original is not None
    assert original.version == 1

    service.edit_draft(session_id, "Make it shorter")

    record = service.get_session(session_id)
    assert len(record.drafts) == 2
    assert record.drafts[0].version == 1
    assert record.drafts[0].body == original.body
    assert record.drafts[0].id != record.drafts[1].id


def test_new_draft_version_increments(service: SessionService) -> None:
    session_id = _enter_edit_state(service)

    first_edit = service.edit_draft(session_id, "Tighten language")
    second_edit = service.edit_draft(session_id, "Expand detail")

    assert first_edit.revised_draft.version == 2
    assert second_edit.revised_draft.version == 3


def test_direct_body_replace_preserves_typed_text(service: SessionService) -> None:
    session_id = _enter_edit_state(service)
    before = service.get_session(session_id).current_draft
    assert before is not None
    extra = "Additional operator note: keep the /users handler idempotent."
    updated = f"{before.body.rstrip()}\n\n{extra}"

    edited = service.edit_draft(session_id, body=updated)

    assert edited.edit_intent is EditIntent.DIRECT_EDIT
    assert edited.revised_draft is not None
    assert extra in edited.revised_draft.body
    assert edited.revised_draft.version == before.version + 1
    assert edited.revised_draft.change_summary == "Direct draft edit."


def test_direct_body_replace_via_api(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Write a release note prompt"})
    session_id = create.json()["session"]["id"]
    started = drive_client_session_to_edit(
        client,
        session_id,
        answers=["Engineering team", "Bulleted summary"],
    )
    original = started["current_draft"]["body"]
    extra = "Paste-in constraint: never rewrite unrelated routers."
    updated = f"{original.rstrip()}\n\n{extra}"

    edit = client.post(f"/sessions/{session_id}/edit", json={"body": updated})
    assert edit.status_code == 200
    body = edit.json()

    assert body["edit_intent"] == EditIntent.DIRECT_EDIT
    assert extra in body["revised_draft"]["body"]
    assert extra in body["current_draft"]["body"]
    assert body["revised_draft"]["version"] == 2
    assert body["session"]["state"] == SessionState.EDIT


def test_edit_api_response_includes_revised_fields(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Write a release note prompt"})
    session_id = create.json()["session"]["id"]
    drive_client_session_to_edit(
        client,
        session_id,
        answers=["Engineering team", "Bulleted summary"],
    )

    edit = client.post(
        f"/sessions/{session_id}/edit",
        json={"instruction": "Change tone to analytical"},
    )
    assert edit.status_code == 200
    body = edit.json()

    assert body["edit_intent"] == EditIntent.CHANGE_TONE
    assert body["revised_draft"]["version"] == 2
    assert body["semantic_diff"]
    assert "analytical" in body["updated_requirement_card"]["task_identity"]["additional_constraints"][-1]
    assert body["session"]["state"] == SessionState.EDIT


def test_draft_patch_service_classifies_intents() -> None:
    patch_service = DraftPatchService()

    assert patch_service.classify("Add requirement: cite sources") is EditIntent.ADD_REQUIREMENT
    assert patch_service.classify("Change tone to friendly") is EditIntent.CHANGE_TONE
    assert (
        patch_service.classify("Change output shape to JSON schema")
        is EditIntent.CHANGE_OUTPUT_SHAPE
    )
    assert patch_service.classify("Make it shorter") is EditIntent.TIGHTEN_LANGUAGE

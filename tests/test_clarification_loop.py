import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.domain.limits import MAX_CLARIFICATION_QUESTIONS
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.clarification_question_ranker import (
    ClarificationQuestionRanker,
    format_clarification_question,
)
from prompt_piper_api.services.draft_generator import DraftGenerator
from prompt_piper_api.services.requirement_card_extractor import RequirementCardExtractor
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_client_session_to_edit, drive_session_to_edit


@pytest.fixture
def ranker() -> ClarificationQuestionRanker:
    return ClarificationQuestionRanker(llm=None)


@pytest.fixture
def service() -> SessionService:
    return SessionService(llm=None)


def test_ranker_uses_high_value_field_priority(ranker: ClarificationQuestionRanker) -> None:
    card = RequirementCard(task_identity={"objective": "Add FastAPI user create endpoint"})
    ranked = ranker.rank(card)

    assert [question.field_name for question in ranked[:3]] == [
        "application_requirements.project_context",
        "application_requirements.target_environment",
        "application_requirements.operating_systems",
    ]


def test_deferred_presentation_fields_not_queued(ranker: ClarificationQuestionRanker) -> None:
    card = RequirementCard()
    missing = ranker.missing_fields(card)
    ranked_fields = [question.field_name for question in ranker.rank(card)]

    for field_name in (
        "task_identity.objective",
        "task_identity.environment",
        "optimization_targets",
    ):
        assert field_name not in missing
        assert field_name not in ranked_fields
        assert field_name not in card.unresolved_fields


def test_only_one_question_per_turn(service: SessionService) -> None:
    result = service.create_session(initial_request="Write a weekly status update prompt")

    assert result.record.pending_clarification is not None
    assert result.clarification_question_number == 1
    assert result.clarification_total_questions == len(ClarificationQuestionRanker().missing_fields(result.record.session.requirement_card))
    assert result.record.session.state is SessionState.CLARIFYING


def test_question_includes_quick_choices(service: SessionService) -> None:
    result = service.create_session(initial_request="Summarize customer interview notes")

    assert result.clarification_question is not None
    assert f"Quick question 1 of {result.clarification_total_questions}:" in result.clarification_question
    assert "Choose one or more options and/or answer in your own words:" in result.clarification_question
    assert result.clarification_quick_replies is not None
    assert len(result.clarification_quick_replies) >= 4
    assert result.clarification_quick_replies[-1] == "unspecified"
    for option in result.clarification_quick_replies[:-1]:
        assert option in result.clarification_question
    assert result.clarification_versions is not None
    assert len(result.clarification_versions) == 3
    assert [item.level for item in result.clarification_versions] == [
        "beginner",
        "standard",
        "advanced",
    ]
    assert result.clarification_versions[0].rationale
    assert result.clarification_quick_reply_guides is not None
    assert len(result.clarification_quick_reply_guides) == len(result.clarification_quick_replies)
    assert result.clarification_quick_reply_guides[0].when_to_use
    assert result.clarification_quick_reply_guides[0].explanation

def test_clarification_loop_reaches_draft_at_gate(client: TestClient) -> None:
    create = client.post("/sessions", json={"initial_request": "Draft a release note prompt"})
    assert create.status_code == 201
    session_id = create.json()["session"]["id"]
    assert create.json()["clarification_question_number"] == 1
    assert create.json()["current_draft"] is None

    first = client.post(
        f"/sessions/{session_id}/answer",
        json={"answer": "Recommended: evidence-based COMPLETE / PARTIAL / BLOCKED / FAILED"},
    )
    assert first.status_code == 200
    assert first.json()["session"]["state"] == SessionState.CLARIFYING
    assert first.json()["current_draft"] is None

    payload = drive_client_session_to_edit(
        client,
        session_id,
        answers=["Python with FastAPI", "Markdown changelog string"],
    )
    assert payload["session"]["state"] == SessionState.EDIT
    assert payload["current_draft"] is not None


def test_unspecified_answers_keep_fields_unresolved_and_marked_in_draft(
    service: SessionService,
) -> None:
    created = service.create_session(initial_request="Create an incident report prompt")
    session_id = created.record.session.id
    pending_field = created.record.pending_clarification.field_name

    service.answer_clarification(session_id, "unspecified")
    after_first = service.get_session(session_id)
    assert pending_field in after_first.session.requirement_card.unresolved_fields

    drive_session_to_edit(service, session_id)
    record = service.get_session(session_id)
    draft = record.current_draft
    assert draft is not None
    assert "unspecified" in draft.body.lower()
    assert "engineering team" not in draft.body


def test_free_text_answer_is_accepted(service: SessionService) -> None:
    created = service.create_session(initial_request="Help me write a product FAQ prompt")
    session_id = created.record.session.id
    field = created.record.pending_clarification.field_name

    service.answer_clarification(session_id, "support agents handling billing questions")
    record = service.get_session(session_id)
    assert (
        record.session.requirement_card.get_leaf(field)
        == "support agents handling billing questions"
    )


def test_complete_clarification_after_all_gaps_unspecified(service: SessionService) -> None:
    created = service.create_session(initial_request="Draft a release note prompt")
    session_id = created.record.session.id

    for _ in range(MAX_CLARIFICATION_QUESTIONS):
        record = service.get_session(session_id)
        if record.session.state is SessionState.EDIT:
            break
        if service._can_complete_clarification_early(record):
            result = service.complete_clarification(session_id)
            assert result.draft is not None
            assert result.record.session.state is SessionState.EDIT
            return
        service.answer_clarification(session_id, "unspecified")

    record = service.get_session(session_id)
    assert record.session.state is SessionState.EDIT


def test_format_clarification_question_example_style() -> None:
    text = format_clarification_question(
        question_number=1,
        total_questions=16,
        prompt='What does "done" actually mean?',
        quick_reply_options=[
            "Recommended: evidence-based COMPLETE / PARTIAL / BLOCKED / FAILED",
            "Stricter: tests, demo, docs, and no known regressions",
            "Minimal: requested behavior is demonstrable",
            "unspecified",
        ],
    )

    assert text.startswith(
        'Quick question 1 of 16: What does "done" actually mean?'
    )
    assert "- Recommended: evidence-based COMPLETE / PARTIAL / BLOCKED / FAILED" in text
    assert "- unspecified" in text


def test_extractor_marks_unspecified_without_inventing_values() -> None:
    card = RequirementCard()
    extractor = RequirementCardExtractor()

    extractor.apply_answer(card, "agent_contract.definition_of_done", "unspecified")

    assert card.agent_contract.definition_of_done == ""
    assert "agent_contract.definition_of_done" in card.unresolved_fields


def test_extractor_applies_multiple_quick_replies_to_list_field() -> None:
    card = RequirementCard()
    extractor = RequirementCardExtractor()

    extractor.apply_answer(
        card,
        "task_identity.additional_constraints",
        "keep under 500 words; no jargon; cite sources",
    )

    assert card.task_identity.additional_constraints == [
        "keep under 500 words",
        "no jargon",
        "cite sources",
    ]


def test_extractor_applies_multiple_quick_replies_to_string_field() -> None:
    card = RequirementCard()
    extractor = RequirementCardExtractor()

    extractor.apply_answer(
        card,
        "agent_contract.change_scope",
        "Recommended: minimum necessary change",
    )

    assert "minimum-necessary change policy" in card.agent_contract.change_scope.lower()
    assert "agent_contract.change_scope" not in card.unresolved_fields

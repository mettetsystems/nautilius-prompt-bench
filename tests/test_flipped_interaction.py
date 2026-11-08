"""Goal-directed question selection must preserve accepted decisions and manual control."""

import json

import pytest
from prompt_piper_api.domain.consultation import CONSULTATION_TOPICS
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.mock import MockLLMClient
from prompt_piper_api.schemas.session import to_session_response
from prompt_piper_api.services.clarification_question_ranker import (
    ClarificationQuestion,
    ClarificationQuestionRanker,
)
from prompt_piper_api.services.clarification_suggestion_service import (
    ClarificationSuggestionService,
)
from prompt_piper_api.services.session_service import SessionService
from prompt_piper_api.services.session_store import FileSessionStore
from tests.card_fixtures import architecture_card

PERMISSIONS = "application_requirements.permissions"
ACCEPTANCE = "application_requirements.acceptance"
PROJECT_CONTEXT = "application_requirements.project_context"
RATIONALE = "Access rules determine which order records the portal may expose."
BLIND_SPOT = "It is unconfirmed whether shared accounts may see another customer's orders."


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch):
    monkeypatch.setenv("PROMPT_PIPER_EMBEDDING_FALLBACK", "true")


def question_payload(**overrides):
    return json.dumps(
        {
            "field_name": PERMISSIONS,
            "prompt": "Who should be allowed to view each order?",
            "beginner_prompt": "Who may see an order's details?",
            "advanced_prompt": "Which access boundaries must order visibility enforce?",
            "rationale": RATIONALE,
            "blind_spots": [BLIND_SPOT],
            "suggested_answers": ["Only the customer who placed the order"],
            **overrides,
        }
    )


def card_with_gaps():
    card = architecture_card()
    card.application_requirements.acceptance = ""
    card.application_requirements.permissions = ""
    return card


def test_model_prioritizes_an_open_decision_using_goal_and_history():
    card = card_with_gaps()
    before = card.coding_spec_dict()
    model = MockLLMClient(chat_responder=lambda _: question_payload())
    question = ClarificationQuestionRanker(model).top_question(
        card,
        question_number=4,
        total_questions=15,
        initial_request="Add order tracking",
        last_answer="Orders stay on premises",
    )
    assert question.field_name == PERMISSIONS  # Template priority would ask acceptance first.
    assert question.question_number == 4
    assert question.total_questions == 15
    assert question.quick_reply_options[0] == "Only the customer who placed the order"
    assert all(version.rationale == RATIONALE for version in question.versions)
    assert all(version.blind_spots == [BLIND_SPOT] for version in question.versions)
    assert f"Why this matters: {RATIONALE}" in question.question
    assert BLIND_SPOT in question.question
    assert card.coding_spec_dict() == before
    assert len(model.chat_calls) == 1
    instructions, user = model.chat_calls[0]
    assert "Flipped Interaction Pattern" in instructions.content
    assert "long-horizon agent" in instructions.content
    context = json.loads(user.content)
    assert context["initial_request"] == "Add order tracking"
    assert context["last_answer"] == "Orders stay on premises"
    assert context["accepted_requirements"] == before
    assert [q["field_name"] for q in context["eligible_questions"]] == [ACCEPTANCE, PERMISSIONS]


@pytest.mark.parametrize(
    "selected",
    [
        ACCEPTANCE,  # Already asked during this pass, even though unresolved.
        "application_requirements.hosting",  # Accepted.
        "application_requirements.offline_sync",  # Inapplicable to the online-only goal.
        "agent_contract.resource_budget",  # Execution policy, not an interview topic.
        "invented_field",
        None,
        [],
    ],
)
def test_model_cannot_select_excluded_answered_or_inapplicable_fields(selected):
    model = MockLLMClient(chat_responder=lambda _: question_payload(field_name=selected))
    question = ClarificationQuestionRanker(model).top_question(
        card_with_gaps(),
        question_number=2,
        exclude=frozenset({ACCEPTANCE}),
    )
    assert question.field_name == PERMISSIONS
    assert question.prompt == CONSULTATION_TOPICS[PERMISSIONS].prompt
    assert all(version.rationale for version in question.versions)
    assert all(not version.blind_spots for version in question.versions)
    context = json.loads(model.chat_calls[0][-1].content)
    assert [q["field_name"] for q in context["eligible_questions"]] == [PERMISSIONS]


def test_project_context_comes_first_and_retains_applicability_choices():
    model = MockLLMClient(chat_responder=lambda _: question_payload(field_name=PROJECT_CONTEXT))
    question = ClarificationQuestionRanker(model).top_question(RequirementCard(), question_number=1)
    assert question.field_name == PROJECT_CONTEXT
    assert question.quick_reply_options[:3] == [
        "New application",
        "Existing codebase",
        "Non-application task",
    ]
    context = json.loads(model.chat_calls[0][-1].content)
    assert [q["field_name"] for q in context["eligible_questions"]] == [PROJECT_CONTEXT]


def test_explicit_field_cannot_be_changed_by_model():
    model = MockLLMClient(chat_responder=lambda _: question_payload())
    question = ClarificationQuestionRanker(model).build_question(
        ACCEPTANCE,
        question_number=1,
        card=card_with_gaps(),
        tailor=True,
    )
    assert question.field_name == ACCEPTANCE
    assert question.prompt == CONSULTATION_TOPICS[ACCEPTANCE].prompt


@pytest.mark.parametrize("blind_spots", [None, "a gap", [1], [" "], ["x" * 401], ["gap"] * 4])
def test_invalid_blind_spots_fall_back_without_accepting_model_content(blind_spots):
    model = MockLLMClient(chat_responder=lambda _: question_payload(blind_spots=blind_spots))
    question = ClarificationQuestionRanker(model).top_question(card_with_gaps(), question_number=1)
    assert question.field_name == ACCEPTANCE
    assert question.prompt == CONSULTATION_TOPICS[ACCEPTANCE].prompt
    assert "Why this matters:" in question.question
    assert "Potential blind spots" not in question.question


def test_question_survives_api_serialization_and_restart_without_reasking(tmp_path):
    def respond(messages):
        context = json.loads(messages[-1].content)
        fields = [q["field_name"] for q in context["eligible_questions"]]
        return question_payload(field_name=PERMISSIONS if PERMISSIONS in fields else fields[0])

    model = MockLLMClient(chat_responder=respond)
    store = FileSessionStore(tmp_path / "sessions")
    service = SessionService(store=store, clarification_llm_factory=lambda: model)
    created = service.create_session(initial_request="Add order tracking")
    result = service.answer_clarification(created.record.session.id, "Existing codebase")
    assert result.clarification_field == PERMISSIONS
    expected = result.record.pending_clarification.model_dump()
    response = to_session_response(result).model_dump(mode="json")
    assert response["clarification_versions"][1]["blind_spots"] == [BLIND_SPOT]
    assert response["clarification_versions"][1]["rationale"] == RATIONALE
    restarted = SessionService(store=store, clarification_llm_factory=lambda: model)
    for _ in range(2):
        reloaded = restarted.get_session(created.record.session.id)
        assert reloaded.pending_clarification.model_dump() == expected
    assert len(model.chat_calls) == 2
    next_turn = restarted.answer_clarification(created.record.session.id, "Unsure")
    assert next_turn.clarification_field != PERMISSIONS
    assert PERMISSIONS in next_turn.record.session.requirement_card.unresolved_fields
    assert BLIND_SPOT not in json.dumps(
        next_turn.record.session.requirement_card.coding_spec_dict()
    )
    assert len(model.chat_calls) == 3


def test_editor_prioritizes_remaining_gaps_without_repeating_skipped_questions():
    service = SessionService()
    record = service.create_session(initial_request="Add order tracking").record
    record.session.state = SessionState.EDIT
    record.session.requirement_card = card_with_gaps()
    model = MockLLMClient(chat_responder=lambda _: question_payload())
    service._ranker = ClarificationQuestionRanker(model)
    service._ranker.missing_fields(record.session.requirement_card)
    question = service._begin_edit_unresolved_queue(record)
    assert question.field_name == PERMISSIONS
    assert record.edit_unresolved_asked == [PERMISSIONS]
    next_question = service._set_pending_edit_unresolved_question(record)
    assert next_question.field_name == ACCEPTANCE
    assert record.edit_unresolved_asked == [PERMISSIONS, ACCEPTANCE]


def test_legacy_saved_question_without_blind_spots_remains_readable():
    payload = (
        ClarificationQuestionRanker().build_question(PERMISSIONS, question_number=1).model_dump()
    )
    for version in payload["versions"]:
        version.pop("blind_spots")
        if version["level"] != "beginner":
            version["rationale"] = None
    restored = ClarificationQuestion.model_validate(payload)
    assert all(version.blind_spots == [] for version in restored.versions)
    assert restored.versions[0].rationale


@pytest.mark.parametrize("use_user_prompt", [False, True])
def test_optional_followups_include_why_and_remain_unaccepted(use_user_prompt):
    followup = (
        "Can shared accounts see other customers' orders? Why this matters: "
        "Unconfirmed shared-account access could expose orders to unintended viewers."
    )
    model = MockLLMClient(chat_responder=lambda _: json.dumps({"follow_up_questions": [followup]}))
    card = card_with_gaps()
    before = card.model_dump()
    result = ClarificationSuggestionService(model, use_user_prompt=use_user_prompt).suggest(
        initial_request="Add order tracking",
        card=card,
        field_name=PERMISSIONS,
        asked_fields=[PROJECT_CONTEXT],
    )
    instructions = model.chat_calls[0][0].content
    assert "Flipped Interaction Pattern" in instructions
    assert "Why this matters:" in instructions
    assert "potential blind spot" in instructions
    assert result.follow_up_questions == [followup]
    assert card.model_dump() == before

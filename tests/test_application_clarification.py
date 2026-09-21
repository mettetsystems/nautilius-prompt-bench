import json

import pytest
from prompt_piper_api.domain.application_requirements import (
    applicable_application_fields,
    material_open_decisions,
)
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.clarification_question_ranker import (
    ClarificationQuestionRanker,
    clarification_field_priority,
)
from prompt_piper_api.services.clarification_suggestion_service import (
    ClarificationSuggestionService,
)
from prompt_piper_api.services.harness_prompt_builder import build_harness_body
from prompt_piper_api.services.requirement_card_extractor import (
    RequirementCardExtractor,
)
from prompt_piper_api.services.session_record import SessionRecord

from tests.test_clarification_suggestions import StubLLMClient

PREFIX = "application_requirements."


def test_application_coverage_and_separate_development_environment():
    card = RequirementCard()
    fields = ClarificationQuestionRanker().missing_fields(card)
    for name in (
        "project_context",
        "target_environment",
        "operating_systems",
        "hosting",
        "runtime",
        "technology",
        "development_environment",
        "compatibility",
        "delivery",
        "storage",
        "connectivity",
        "constraints",
        "acceptance",
    ):
        assert PREFIX + name in fields
    card.application_requirements.development_environment = "Linux with Python 3.12"
    assert not card.application_requirements.operating_systems
    assert not card.application_requirements.runtime


def test_conditional_followups():
    card = RequirementCard(
        application_requirements={"project_context": "New application"}
    )
    assert PREFIX + "compatibility" not in applicable_application_fields(card)
    card.application_requirements.project_context = "Existing codebase"
    assert PREFIX + "compatibility" in applicable_application_fields(card)
    assert PREFIX + "offline_sync" not in applicable_application_fields(card)
    card.application_requirements.connectivity = (
        "Offline edits with later synchronization"
    )
    assert PREFIX + "offline_sync" in applicable_application_fields(card)
    card.application_requirements.connectivity = "Online only; no offline support"
    assert PREFIX + "offline_sync" not in applicable_application_fields(card)
    card.application_requirements.project_context = "Non-application task"
    assert PREFIX + "runtime" not in applicable_application_fields(card)
    assert PREFIX + "acceptance" in applicable_application_fields(card)


def test_harness_delegation_preserves_explicit_policies():
    card = RequirementCard(
        application_requirements={"harness_controls": "Use receiving harness controls"},
        agent_contract={"resource_budget": "Explicit user cap: 20 calls"},
    )
    assert "agent_contract.resource_budget" not in clarification_field_priority(card)
    body = build_harness_body(card)
    assert "Explicit user cap: 20 calls" in body
    assert "Use the receiving harness controls" in body
    assert "80%" not in body


@pytest.mark.parametrize(
    "answer",
    ["Unsure", "unknown", "not sure", "Not applicable", "n/a", "Recommend an option"],
)
def test_unknowns_and_deliberate_choices_stay_explicit(answer):
    card = RequirementCard()
    RequirementCardExtractor().apply_answer(card, PREFIX + "runtime", answer)
    assert card.application_requirements.runtime == answer
    assert f"Runtime Compatibility: {answer}" in build_harness_body(card)
    if answer.lower() in {"unsure", "unknown", "not sure"}:
        assert PREFIX + "runtime" in material_open_decisions(card)
    else:
        assert PREFIX + "runtime" not in material_open_decisions(card)


def test_intake_labeled_decisions_not_asked_twice():
    card = RequirementCardExtractor().extract(
        "Build an app\nSupported Operating Systems: Windows 11\nDevelopment Environment: Fedora"
    )
    assert card.application_requirements.operating_systems == "Windows 11"
    assert (
        PREFIX + "operating_systems"
        not in ClarificationQuestionRanker().missing_fields(card)
    )
    assert card.application_requirements.development_environment == "Fedora"


class CapturingClient(StubLLMClient):
    messages = None

    def chat(self, messages, **kwargs):
        self.messages = messages
        return super().chat(messages, **kwargs)


def test_expansion_is_proposal_grounded_in_current_and_accepted_answers():
    client = CapturingClient(
        json.dumps(
            {
                "proposed_answer": "Support Windows 11 on desktop.",
                "recommendations": ["Consider signed installers for easier updates."],
                "follow_up_questions": ["Are administrator privileges available?"],
            }
        )
    )
    card = RequirementCard(application_requirements={"hosting": "Local only"})
    before = card.model_dump()
    result = ClarificationSuggestionService(client).suggest(
        initial_request="Build a desktop app",
        card=card,
        field_name=PREFIX + "operating_systems",
        current_answer="Windows 11",
    )
    context = json.loads(client.messages[-1].content)
    assert context["current_answer"] == "Windows 11"
    assert (
        context["requirement_card"]["application_requirements"]["hosting"]
        == "Local only"
    )
    assert result.original_answer == "Windows 11"
    assert result.proposed_answer == "Support Windows 11 on desktop."
    assert card.model_dump() == before
    assert result.follow_up_questions
    assert "signed installers" not in result.proposed_answer


def test_conflicts_suppress_proposed_answer_and_quick_accept_alternatives():
    client = StubLLMClient(
        json.dumps(
            {
                "proposed_answer": "Deploy to cloud",
                "suggested_answers": ["Cloud"],
                "conflicts": [
                    "Conflicts with application_requirements.hosting: local only"
                ],
            }
        )
    )
    result = ClarificationSuggestionService(client).suggest(
        initial_request="Build app",
        card=RequirementCard(application_requirements={"hosting": "Local only"}),
        field_name=PREFIX + "delivery",
    )
    assert result.conflicts
    assert not result.proposed_answer
    assert not result.suggested_answers


def test_model_cannot_resolve_an_unknown():
    result = ClarificationSuggestionService(
        StubLLMClient('{"proposed_answer":"Require Python 3.13"}')
    ).suggest(
        initial_request="Build app",
        card=RequirementCard(),
        field_name=PREFIX + "runtime",
        current_answer="Unsure",
    )
    assert result.proposed_answer == "Unsure"


@pytest.mark.parametrize(
    "payload",
    ["not json", "[]", '{"recommendations": "bad shape"}', '{"proposed_answer": 123}'],
)
def test_model_failure_keeps_manual_answer(payload):
    result = ClarificationSuggestionService(StubLLMClient(payload)).suggest(
        initial_request="Build app",
        card=RequirementCard(),
        field_name=PREFIX + "runtime",
        current_answer="Python 3.12",
    )
    assert not result.model_available
    assert result.original_answer == "Python 3.12"
    assert not result.proposed_answer


def test_old_saved_card_and_session_remain_readable():
    from prompt_piper_api.domain.session import PromptSession

    record = SessionRecord(session=PromptSession(requirement_card=RequirementCard()))
    payload = record.model_dump(mode="json")
    del payload["session"]["requirement_card"]["application_requirements"]
    del payload["clarification_suggestions"]
    restored = SessionRecord.model_validate(payload)
    assert restored.session.requirement_card.application_requirements.runtime == ""
    assert restored.clarification_suggestions == []
    assert "Task Identity" in build_harness_body(restored.session.requirement_card)


def test_no_sixteen_question_cutoff():
    from prompt_piper_api.domain.session import PromptSession
    from prompt_piper_api.services.session_service import SessionService

    service = SessionService.__new__(SessionService)
    service._ranker = ClarificationQuestionRanker()
    record = SessionRecord(
        session=PromptSession(requirement_card=RequirementCard()),
        clarification_turn=16,
        asked_clarification_fields=list(
            clarification_field_priority(RequirementCard())[:16]
        ),
    )
    assert not service._should_finish_clarification(record)


def test_deepseek_uses_user_message_and_failure_stays_manual():
    client = CapturingClient('{"proposed_answer":"Windows 11 desktop"}')
    result = ClarificationSuggestionService(client, use_user_prompt=True).suggest(
        initial_request="Build app", card=RequirementCard(),
        field_name=PREFIX + "operating_systems", current_answer="Windows 11 desktop",
    )
    assert result.model_available
    assert [message.role for message in client.messages] == ["user"]
    assert "current_answer" in client.messages[0].content

    class TimeoutClient(StubLLMClient):
        def chat(self, *args, **kwargs):
            raise TimeoutError("Timed out")

    result = ClarificationSuggestionService(TimeoutClient("")).suggest(
        initial_request="Build app", card=RequirementCard(),
        field_name=PREFIX + "runtime", current_answer="Manual Python requirement",
    )
    assert not result.model_available
    assert result.original_answer == "Manual Python requirement"


def test_project_permissions_question_and_exports():
    from prompt_piper_api.domain.application_requirements import APPLICATION_QUESTIONS
    card = RequirementCard()
    field = PREFIX + "permissions"
    assert field in ClarificationQuestionRanker().missing_fields(card)
    question = next(q for q in APPLICATION_QUESTIONS if q.field_name == field)
    assert "sudo" in question.standard_prompt
    answer = "Sudo for installation and updates only; run as a standard user"
    RequirementCardExtractor().apply_answer(card, field, answer)
    assert card.get_leaf(field) == answer
    assert f"Project Permissions: {answer}" in build_harness_body(card)
    assert card.coding_spec_dict()["application_requirements"]["permissions"] == answer
    assert RequirementCard.model_validate({}).application_requirements.permissions == ""


@pytest.mark.parametrize('name', [
    'build_isolation', 'build_toolchain', 'build_hardware', 'build_access',
    'build_workspace', 'environment_bootstrap', 'validation_environment', 'environment_parity',
])
def test_agent_environment_questions_roundtrip(name):
    card = RequirementCard()
    field = PREFIX + name
    ranker = ClarificationQuestionRanker()
    assert field in ranker.missing_fields(card)
    question = ranker.build_question(field, question_number=1)
    assert question.prompt and question.quick_reply_options[-1] == 'unspecified'
    answer = 'Project-specific environment constraint for ' + name
    RequirementCardExtractor().apply_answer(card, field, answer)
    assert answer in build_harness_body(card)
    assert card.coding_spec_dict()['application_requirements'][name] == answer
    assert RequirementCard.model_validate(card.model_dump()).get_leaf(field) == answer
    assert RequirementCard.model_validate({}).get_leaf(field) == ''


def test_build_environment_does_not_infer_target_environment():
    card = RequirementCard()
    RequirementCardExtractor().apply_answer(card, PREFIX + 'development_environment', 'Fedora 44, x86_64, bash')
    RequirementCardExtractor().apply_answer(card, PREFIX + 'build_toolchain', 'Python 3.12 in venv')
    assert card.application_requirements.operating_systems == ''
    assert card.application_requirements.runtime == ''
    assert PREFIX + 'validation_environment' in material_open_decisions(card)

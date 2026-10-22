"""Architecture-only answers must still produce an executable coding contract."""

import json

import pytest
from prompt_piper_api.domain.consultation import (
    CONSULTATION_TOPICS,
    consultation_fields,
)
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.domain.harness import HARNESS_SECTION_TITLES
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.mock import MockLLMClient
from prompt_piper_api.services.api_pack_export import build_api_pack
from prompt_piper_api.services.ask_the_locals_service import AskTheLocalsService
from prompt_piper_api.services.clarification_question_ranker import (
    ClarificationQuestionRanker,
)
from prompt_piper_api.services.clarification_suggestion_service import (
    ClarificationSuggestionService,
)
from prompt_piper_api.services.contract_resolver import (
    TOOLCHAIN_DELEGATION,
    resolve_contract,
)
from prompt_piper_api.services.draft_generator import DraftGenerator
from prompt_piper_api.services.first_shot_readiness import assess_first_shot_readiness
from prompt_piper_api.services.harness_prompt_builder import (
    build_harness_body,
    build_harness_spec,
)
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.requirement_card_extractor import (
    RequirementCardExtractor,
)
from prompt_piper_api.services.session_service import SessionService
from prompt_piper_api.services.session_store import FileSessionStore

from tests.card_fixtures import architecture_card


def tailored_payload(**overrides):
    return json.dumps(
        {
            "prompt": "Which existing service boundaries must order tracking preserve?",
            "beginner_prompt": "Which existing systems should stay responsible for orders?",
            "advanced_prompt": "Which order-service boundaries and interface contracts are invariant?",
            "rationale": "Service ownership determines integration constraints.",
            "suggested_answers": ["Keep the existing order service authoritative"],
            **overrides,
        }
    )


def test_architecture_only_card_resolves_without_mutating_user_answers():
    card = architecture_card()
    before = card.model_dump()
    result = resolve_contract(card)
    assert card.model_dump() == before
    assert not result.unresolved_fields
    assert result.card.agent_contract.definition_of_done
    assert result.card.agent_contract.resource_budget
    assert result.sources["agent_contract.resource_budget"] == "default"
    assert result.sources["application_requirements.build_toolchain"] == "delegated"
    assert TOOLCHAIN_DELEGATION in result.card.application_requirements.build_toolchain
    assert assess_first_shot_readiness(card).ready
    assert card.model_dump() == before


def test_architecture_gaps_remain_risks_while_execution_defaults_are_ready():
    card = architecture_card()
    card.application_requirements.acceptance = "Unsure"
    readiness = assess_first_shot_readiness(card)
    assert not readiness.ready
    assert [r.field_name for r in readiness.risks] == [
        "application_requirements.acceptance"
    ]
    assert not any(
        r.field_name == "agent_contract.resource_budget" for r in readiness.risks
    )


def test_full_contract_survives_draft_optimization_and_all_api_formats():
    card = architecture_card()
    card.application_requirements.build_toolchain = (
        "Use the pinned Python 3.12 toolchain"
    )
    card.agent_contract.resource_budget = "Stop after 30 minutes"
    before = card.model_dump()
    draft = DraftGenerator().generate(card)
    optimized = TokenOptimizationEngine().optimize(draft.body, card)
    pack = build_api_pack(card)
    for body in (draft.body, optimized.optimized_body, pack["harness_prompt.txt"]):
        assert all(title in body for title in HARNESS_SECTION_TITLES)
        assert "Role: long-horizon coding agent" in body
        assert "[Workbench default]" in body
        assert "[Developer responsibility]" in body
        assert "Use the pinned Python 3.12 toolchain" in body
        assert "Stop after 30 minutes" in body
        assert "CTO" not in body
    assert pack["harness_prompt.txt"] in pack["harness_prompt.md"]
    for key, payload in pack.items():
        if key.startswith("api_pack/") and key.endswith(".json"):
            serialized = json.dumps(payload)
            assert "Stop after 30 minutes" in serialized
            assert "Completion Contract" in serialized
    spec = build_harness_spec(card)
    assert spec["source_card"] == card.coding_spec_dict()
    assert spec["resolved_card"]["agent_contract"]["validation_strategy"]
    assert card.model_dump() == before


def test_defaults_do_not_invent_numeric_budgets_or_hardware():
    body = build_harness_body(architecture_card())
    for invented in (
        "150 LLM",
        "80%",
        "2 hours",
        "3 consecutive",
        "git reset",
        ".agent/STATUS.md",
    ):
        assert invented not in body
    assert "Do not invent numeric limits" in body
    assert "without assuming GPU availability" in body


def test_interview_only_asks_applicable_architectural_questions():
    card = RequirementCard(
        application_requirements={"project_context": "New application"}
    )
    ranker = ClarificationQuestionRanker()
    fields = ranker.missing_fields(card)
    assert "application_requirements.compatibility" not in fields
    assert "application_requirements.offline_sync" not in fields
    assert "application_requirements.build_toolchain" not in fields
    assert "agent_contract.resource_budget" not in fields
    card.application_requirements.connectivity = (
        "Offline changes with later synchronization"
    )
    assert "application_requirements.offline_sync" in ranker.missing_fields(card)
    card.application_requirements.project_context = "Non-application task"
    assert "application_requirements.storage" not in consultation_fields(card)
    assert "application_requirements.acceptance" in consultation_fields(card)


def test_generation_only_for_selected_question_and_uses_accepted_context():
    model = MockLLMClient(chat_responder=lambda _: tailored_payload())
    ranker = ClarificationQuestionRanker(model)
    card = architecture_card()
    card.agent_contract.architecture_policy = ""
    ranker.rank(card)
    ranker.missing_fields(card)
    assert not model.chat_calls
    question = ranker.top_question(
        card, question_number=1, initial_request="Add order tracking"
    )
    assert len(model.chat_calls) == 1
    assert question.field_name == "agent_contract.architecture_policy"
    assert question.prompt == json.loads(tailored_payload())["prompt"]
    assert question.versions[1].prompt == question.prompt
    assert question.quick_reply_options[-1] == "unspecified"
    assert [
        g.option for g in question.quick_reply_guides
    ] == question.quick_reply_options
    context = json.loads(model.chat_calls[0][1].content)
    assert (
        context["accepted_requirements"]["application_requirements"]["hosting"]
        == card.application_requirements.hosting
    )


@pytest.mark.parametrize(
    "payload",
    [
        "bad json",
        "[]",
        "{}",
        tailored_payload(prompt=""),
        tailored_payload(suggested_answers=[1]),
    ],
)
def test_malformed_generation_falls_back_to_architectural_template(payload):
    model = MockLLMClient(chat_responder=lambda _: payload)
    question = ClarificationQuestionRanker(model).top_question(
        RequirementCard(), question_number=1
    )
    assert question.prompt == CONSULTATION_TOPICS[question.field_name].prompt


def test_timeout_and_disabled_model_use_templates():
    def timeout(_):
        raise TimeoutError("Model timed out")

    for model in (None, MockLLMClient(chat_responder=timeout)):
        question = ClarificationQuestionRanker(model).top_question(
            RequirementCard(), question_number=1
        )
        assert question.prompt == CONSULTATION_TOPICS[question.field_name].prompt


def test_tailored_question_persists_across_reads_and_service_restarts(tmp_path):
    model = MockLLMClient(chat_responder=lambda _: tailored_payload())
    store = FileSessionStore(tmp_path / "sessions")
    service = SessionService(store=store, clarification_llm_factory=lambda: model)
    created = service.create_session(initial_request="Add order tracking")
    expected = created.record.pending_clarification.model_dump()
    assert len(model.chat_calls) == 1
    for instance in (
        service,
        SessionService(store=store, clarification_llm_factory=lambda: model),
    ):
        for _ in range(2):
            assert (
                instance.get_session(
                    created.record.session.id
                ).pending_clarification.model_dump()
                == expected
            )
    assert len(model.chat_calls) == 1
    service.answer_clarification(created.record.session.id, "Existing codebase")
    assert len(model.chat_calls) == 2


def test_old_technical_question_is_reconciled_without_generation(tmp_path):
    store = FileSessionStore(tmp_path / "sessions")
    service = SessionService(store=store)
    record = service.create_session(initial_request="Add order tracking").record
    record.consultation_policy_version = 0
    record.session.requirement_card.application_requirements.build_toolchain = (
        "Existing pinned SDK"
    )
    record.pending_clarification = ClarificationQuestionRanker().build_question(
        "application_requirements.build_workspace",
        question_number=2,
    )
    record.asked_clarification_fields.append("application_requirements.build_workspace")
    store.save(record)
    model = MockLLMClient(chat_responder=lambda _: tailored_payload())
    reloaded = SessionService(store=store, clarification_llm_factory=lambda: model)
    restored = reloaded.get_session(record.session.id)
    assert restored.pending_clarification.field_name in CONSULTATION_TOPICS
    assert (
        restored.session.requirement_card.application_requirements.build_toolchain
        == "Existing pinned SDK"
    )
    assert not model.chat_calls


def test_explicit_intake_facts_are_extracted_but_model_inventions_are_discarded():
    request = "Build a portal. All customer data stays on premises.\nResource Budget: Stop after 30 minutes"
    model = MockLLMClient(
        chat_responder=lambda _: json.dumps(
            {
                "application_requirements": {
                    "hosting": "All customer data stays on premises",
                    "technology": "Use React",
                },
                "agent_contract": {"resource_budget": "Stop after 999 calls"},
            }
        )
    )
    card = RequirementCardExtractor(model).extract(request)
    assert (
        card.application_requirements.hosting == "All customer data stays on premises"
    )
    assert not card.application_requirements.technology
    assert card.agent_contract.resource_budget == "Stop after 30 minutes"
    assert (
        "application_requirements.hosting"
        not in ClarificationQuestionRanker().missing_fields(card)
    )


def test_both_assistance_services_share_persona_without_accepting_proposals():
    card = architecture_card()
    before = card.model_dump()
    model = MockLLMClient(
        chat_responder=lambda _: json.dumps(
            {
                "recommended_answer": "Retain on-premises data residency.",
                "recommendations": ["Retain on-premises data residency."],
            }
        )
    )
    ClarificationSuggestionService(model).suggest(
        initial_request="Build a portal",
        card=card,
        field_name="application_requirements.hosting",
    )
    AskTheLocalsService(model).ask(
        initial_request="Build a portal",
        card=card,
        field_name="application_requirements.hosting",
    )
    for messages in model.chat_calls:
        assert "senior freelance software developer" in messages[0].content
        assert "CTO or Principal Architect" in messages[0].content
    assert card.model_dump() == before


def test_architecture_interview_produces_full_prompt_without_operational_questions():
    source = architecture_card()
    service = SessionService()
    record = service.create_session(initial_request=source.objective).record
    asked = []
    for _ in range(len(CONSULTATION_TOPICS) + 1):
        if record.session.state is SessionState.EDIT:
            break
        field = record.pending_clarification.field_name
        asked.append(field)
        record = service.answer_clarification(
            record.session.id, source.get_leaf(field)
        ).record
    assert record.session.state is SessionState.EDIT
    assert set(asked) <= CONSULTATION_TOPICS.keys()
    assert not record.session.requirement_card.agent_contract.resource_budget
    assert "Resource and Budget" in record.current_draft.body
    assert "Developer responsibility" in record.current_draft.body
    assert assess_first_shot_readiness(record.session.requirement_card).ready


def test_model_architectural_edit_preserves_unrelated_accepted_requirements():
    from prompt_piper_api.services.draft_patch_service import DraftPatchService

    card = architecture_card()
    model = MockLLMClient(
        chat_responder=lambda _: json.dumps(
            {
                "updated_requirement_card": {
                    "application_requirements": {"hosting": "Approved private cloud"}
                },
                "semantic_diff": "Hosting changes to the approved private cloud.",
            }
        )
    )
    result = DraftPatchService(model).apply(
        card, "Change hosting to Approved private cloud", "Previous draft"
    )
    assert (
        result.updated_requirement_card.application_requirements.hosting
        == "Approved private cloud"
    )
    assert (
        result.updated_requirement_card.application_requirements.acceptance
        == architecture_card().application_requirements.acceptance
    )
    assert (
        result.updated_requirement_card.agent_contract.change_scope
        == architecture_card().agent_contract.change_scope
    )
    assert "Approved private cloud" in result.updated_body
    assert "[Workbench default]" in result.updated_body


def test_api_pack_repairs_incomplete_override_and_keeps_text_formats_consistent():
    card = architecture_card()
    pack = build_api_pack(card, harness_body="Task Identity\nIncomplete contract")
    assert all(title in pack["harness_prompt.txt"] for title in HARNESS_SECTION_TITLES)
    assert pack["harness_prompt.txt"] in pack["harness_prompt.md"]
    supplied = "Presentation preamble\n" + build_harness_body(card)
    pack = build_api_pack(card, harness_body=supplied)
    assert pack["harness_prompt.txt"] == supplied
    assert supplied in pack["harness_prompt.md"]


def test_model_configuration_failure_also_falls_back():
    def broken_factory():
        raise ValueError("Invalid endpoint configuration")

    question = ClarificationQuestionRanker(llm_factory=broken_factory).top_question(
        RequirementCard(), question_number=1
    )
    assert question.prompt == CONSULTATION_TOPICS[question.field_name].prompt

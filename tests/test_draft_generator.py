from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.draft_generator import DraftGenerator


def test_missing_fields_are_marked_unspecified() -> None:
    card = RequirementCard(task_identity={"objective": "Add FastAPI user create endpoint"})
    result = DraftGenerator(llm=None).generate(card)

    assert "agent_contract.definition_of_done" in result.unresolved_fields
    assert "do not declare COMPLETE without evidence" in result.body
    assert "agent_contract.validation_strategy" in result.unresolved_fields
    assert result.unspecified_note.startswith("Still unspecified:")


def test_deferred_task_identity_not_auto_unresolved() -> None:
    card = RequirementCard(task_identity={"objective": "Add FastAPI user create endpoint"})
    result = DraftGenerator(llm=None).generate(card)

    assert "task_identity.objective" not in result.unresolved_fields
    assert "optimization_targets" not in result.unresolved_fields
    assert "Task Identity" in result.body
    assert "Add FastAPI user create endpoint" in result.body


def test_rule_based_draft_includes_contract_scaffolds() -> None:
    card = RequirementCard(task_identity={"objective": "Add a create-user endpoint"})
    result = DraftGenerator(llm=None).generate(card)

    assert "inspect the repository" in result.body.lower() or "unspecified" in result.body
    assert "never claim tests probably pass" in result.body
    assert "Do not invent" not in result.body


def test_prompt_includes_objective_and_done_policy_when_known() -> None:
    card = RequirementCard(
        task_identity={"objective": "Add a weekly status summary endpoint"},
        agent_contract={
            "definition_of_done": "COMPLETE only with passing tests and a demo.",
        },
    )
    result = DraftGenerator(llm=None).generate(card)

    assert "Add a weekly status summary endpoint" in result.body
    assert "COMPLETE only with passing tests and a demo." in result.body
    assert "Task Identity" in result.body
    assert "Definition of Done" in result.body
    assert "agent_contract.definition_of_done" not in result.unresolved_fields


def test_no_hallucinated_environment() -> None:
    card = RequirementCard(
        task_identity={"objective": "Create a product changelog generator"},
    )
    result = DraftGenerator(llm=None).generate(card)

    assert "Environment: unspecified" in result.body
    assert "engineering team" not in result.body.lower()
    assert "executive stakeholders" not in result.body.lower()


def test_additional_constraints_included_when_present() -> None:
    card = RequirementCard(
        task_identity={
            "objective": "Parse legal document text",
            "additional_constraints": ["provide legal advice", "invent case citations"],
        },
        agent_contract={"tool_safety": "Never print secrets or force-push."},
    )
    result = DraftGenerator(llm=None).generate(card)

    assert "provide legal advice" in result.body
    assert "invent case citations" in result.body
    assert "Never print secrets or force-push." in result.body


def test_output_is_plain_text_without_markdown_or_xml() -> None:
    card = RequirementCard(
        task_identity={
            "objective": "Extract action items from issue comments",
            "environment": "Python 3.12",
            "additional_constraints": ["Every action has an owner"],
        },
        agent_contract={"definition_of_done": "COMPLETE with evidence."},
    )
    result = DraftGenerator(llm=None).generate(card)

    assert result.body
    assert "# " not in result.body
    assert "<prompt" not in result.body.lower()
    assert "<" not in result.body
    assert "Task Identity" in result.body
    assert "Definition of Done" in result.body
    assert "Every action has an owner" in result.body


def test_generate_body_returns_only_text() -> None:
    card = RequirementCard(task_identity={"objective": "Help draft support macros"})
    body = DraftGenerator(llm=None).generate_body(card)

    assert isinstance(body, str)
    assert "Task Identity" in body

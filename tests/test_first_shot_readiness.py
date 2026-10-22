"""First-shot readiness checklist tests."""

from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.first_shot_readiness import assess_first_shot_readiness

from tests.card_fixtures import architecture_card


def test_dense_card_is_ready() -> None:
    card = architecture_card()
    readiness = assess_first_shot_readiness(card)
    assert readiness.ready
    assert readiness.score == 1.0


def test_default_completion_policy_does_not_hide_architectural_risks() -> None:
    card = RequirementCard(
        task_identity={"objective": "Add POST /users"},
        agent_contract={"change_scope": "Minimum-necessary change."},
    )
    readiness = assess_first_shot_readiness(card)
    assert not readiness.ready
    assert not any(
        risk.code == "missing_definition_of_done" for risk in readiness.risks
    )
    assert any(
        risk.field_name == "application_requirements.acceptance"
        for risk in readiness.risks
    )

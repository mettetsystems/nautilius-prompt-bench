"""First-shot readiness checklist tests."""

from tests.card_fixtures import sample_card
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.first_shot_readiness import assess_first_shot_readiness


def test_dense_card_is_ready() -> None:
    card = sample_card()
    readiness = assess_first_shot_readiness(card)
    assert readiness.ready
    assert readiness.score == 1.0


def test_missing_definition_of_done_is_risk() -> None:
    card = RequirementCard(
        task_identity={"objective": "Add POST /users"},
        agent_contract={"change_scope": "Minimum-necessary change."},
    )
    readiness = assess_first_shot_readiness(card)
    assert not readiness.ready
    assert any(risk.code == "missing_definition_of_done" for risk in readiness.risks)

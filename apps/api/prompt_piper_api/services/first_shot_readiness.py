"""Assess whether a RequirementCard is ready for a long-horizon coding agent run."""

from __future__ import annotations

from pydantic import BaseModel, Field

from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.clarification_question_ranker import is_unspecified_answer

CRITICAL_CONTRACT_FIELDS: tuple[str, ...] = (
    "agent_contract.definition_of_done",
    "agent_contract.change_scope",
    "agent_contract.validation_strategy",
    "agent_contract.failure_recovery",
    "agent_contract.completion_contract",
    "agent_contract.resource_budget",
)

SEMANTIC_PRECISION_SOFT_THRESHOLD = 0.75


class FirstShotRisk(BaseModel):
    code: str
    field_name: str | None = None
    message: str


class FirstShotReadiness(BaseModel):
    """Soft readiness checklist shown before finalize / approve."""

    ready: bool = Field(description="True when no high-impact contract gaps remain.")
    score: float = Field(ge=0.0, le=1.0, description="Fraction of readiness checks passed.")
    risks: list[FirstShotRisk] = Field(default_factory=list)
    checklist: list[str] = Field(
        default_factory=list,
        description="Human-readable checklist of what is satisfied or missing.",
    )


def _leaf_populated(card: RequirementCard, field_name: str) -> bool:
    if card.is_leaf_missing(field_name):
        return False
    if field_name in card.unresolved_fields:
        return False
    value = card.get_leaf(field_name)
    if isinstance(value, str):
        return bool(value.strip()) and not is_unspecified_answer(value)
    if isinstance(value, list):
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return bool(cleaned) and not all(is_unspecified_answer(item) for item in cleaned)
    return value is not None


def assess_first_shot_readiness(card: RequirementCard) -> FirstShotReadiness:
    """Return soft readiness risks for long-horizon coding-agent contracts."""
    risks: list[FirstShotRisk] = []
    checklist: list[str] = []
    checks_passed = 0
    checks_total = 0

    def check(ok: bool, code: str, message: str, *, field_name: str | None = None) -> None:
        nonlocal checks_passed, checks_total
        checks_total += 1
        if ok:
            checks_passed += 1
            checklist.append(f"OK: {message}")
            return
        checklist.append(f"Risk: {message}")
        risks.append(FirstShotRisk(code=code, field_name=field_name, message=message))

    check(
        _leaf_populated(card, "task_identity.objective"),
        "missing_objective",
        "Primary coding objective is set",
        field_name="task_identity.objective",
    )
    check(
        _leaf_populated(card, "agent_contract.definition_of_done"),
        "missing_definition_of_done",
        "Definition of done / completion states are set",
        field_name="agent_contract.definition_of_done",
    )
    check(
        _leaf_populated(card, "agent_contract.change_scope"),
        "missing_change_scope",
        "Change-scope / minimum-necessary policy is set",
        field_name="agent_contract.change_scope",
    )
    check(
        _leaf_populated(card, "agent_contract.validation_strategy"),
        "missing_validation_strategy",
        "Incremental validation strategy is set",
        field_name="agent_contract.validation_strategy",
    )
    check(
        _leaf_populated(card, "agent_contract.failure_recovery"),
        "missing_failure_recovery",
        "Failure-recovery protocol is set",
        field_name="agent_contract.failure_recovery",
    )
    check(
        _leaf_populated(card, "agent_contract.completion_contract"),
        "missing_completion_contract",
        "Completion evidence contract is set",
        field_name="agent_contract.completion_contract",
    )
    check(
        _leaf_populated(card, "agent_contract.resource_budget"),
        "missing_resource_budget",
        "Resource and budget pause limits are set",
        field_name="agent_contract.resource_budget",
    )
    check(
        _leaf_populated(card, "agent_contract.persistent_memory"),
        "missing_persistent_memory",
        "Persistent .agent/ memory policy is set",
        field_name="agent_contract.persistent_memory",
    )

    score = round(checks_passed / checks_total, 2) if checks_total else 1.0
    return FirstShotReadiness(
        ready=not risks,
        score=score,
        risks=risks,
        checklist=checklist,
    )


def first_shot_warning_messages(
    readiness: FirstShotReadiness,
    *,
    semantic_precision_score: float | None = None,
    section_coverage: int | None = None,
    expected_sections: int = 17,
) -> list[str]:
    """Build soft warning strings for UI / quality gate."""
    warnings = [risk.message for risk in readiness.risks]
    if (
        semantic_precision_score is not None
        and semantic_precision_score < SEMANTIC_PRECISION_SOFT_THRESHOLD
    ):
        warnings.append(
            "semantic_precision_score below "
            f"{SEMANTIC_PRECISION_SOFT_THRESHOLD:.2f} ({semantic_precision_score:.2f}); "
            "refine vague terms before a long-horizon run"
        )
    if section_coverage is not None and section_coverage < expected_sections:
        warnings.append(
            f"prompt has {section_coverage}/{expected_sections} contract sections; "
            "Task Identity plus the 16 operational policies improve long-horizon adherence"
        )
    return warnings

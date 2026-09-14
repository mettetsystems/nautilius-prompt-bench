"""Build long-horizon task-contract prompts from a RequirementCard.

Optimized / API-bound bodies use the same 16-question contract as the draft.
Clarity is the goal; these prompts are expected to be long.
"""

from __future__ import annotations

from prompt_piper_api.domain.agent_contract import CONTRACT_QUESTIONS
from prompt_piper_api.domain.harness import HARNESS_SECTION_TITLES, HARNESS_SYSTEM_PROMPT
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.clarification_question_ranker import is_unspecified_answer

UNSPECIFIED = "unspecified"

_CONTRACT_SCAFFOLDS: dict[str, str] = {
    "agent_contract.definition_of_done": (
        "unspecified — do not declare COMPLETE without evidence against stated "
        "acceptance criteria; use PARTIAL when follow-up remains"
    ),
    "agent_contract.change_scope": (
        "unspecified — change only files required by the task; never touch secrets or production"
    ),
    "agent_contract.architecture_policy": (
        "unspecified — reuse existing project patterns before adding abstractions"
    ),
    "agent_contract.discovery_policy": (
        "unspecified — inspect the repository and write a short plan before substantial edits"
    ),
    "agent_contract.execution_strategy": (
        "unspecified — implement in small reversible units and test each unit"
    ),
    "agent_contract.validation_strategy": (
        "unspecified — record real test/build commands; never claim tests probably pass"
    ),
    "agent_contract.failure_recovery": (
        "unspecified — diagnose before retrying; never suppress an error without understanding it"
    ),
    "agent_contract.autonomy_policy": (
        "unspecified — act on low-risk reversible work; escalate destructive or high-impact changes"
    ),
    "agent_contract.persistent_memory": (
        "unspecified — keep plan, status, decisions, and issues in .agent/ so work can resume"
    ),
    "agent_contract.completion_contract": (
        "unspecified — completion requires evidence against acceptance criteria, not volume of code"
    ),
    "agent_contract.resource_budget": (
        "unspecified — pause, persist .agent/STATUS.md, and ask a human rather than spinning forever"
    ),
    "agent_contract.tool_safety": (
        "unspecified — no force-push, no secret dumps, no destructive filesystem commands"
    ),
    "agent_contract.context_compaction": (
        "unspecified — when compacting context, preserve the task contract and .agent/ files"
    ),
    "agent_contract.rollback_protocol": (
        "unspecified — checkpoint green tests; abandon a failed approach instead of stacking broken patches"
    ),
    "agent_contract.escalation_rules": (
        "unspecified — stop for missing secrets, conflicting criteria, or exhausted recovery"
    ),
    "agent_contract.dependency_security": (
        "unspecified — audit new packages, prefer OSI-permissive licenses, pin versions"
    ),
}


def _clean(value: str) -> str:
    return value.strip()


def _populated(value: str) -> bool:
    cleaned = _clean(value)
    return bool(cleaned) and not is_unspecified_answer(cleaned)


def _list_clean(values: list[str]) -> list[str]:
    return [
        item.strip()
        for item in values
        if isinstance(item, str) and item.strip() and not is_unspecified_answer(item)
    ]


def _render_section(title: str, lines: list[str]) -> str:
    if not lines:
        return ""
    divider = "-" * len(title)
    return f"{title}\n{divider}\n" + "\n".join(lines)


def _unresolved(card: RequirementCard, field_name: str) -> bool:
    return field_name in card.unresolved_fields or card.is_leaf_missing(field_name)


def _policy_lines(card: RequirementCard, field_name: str, value: str) -> list[str]:
    if _populated(value):
        return [value.strip()]
    scaffold = _CONTRACT_SCAFFOLDS.get(field_name)
    if scaffold and _unresolved(card, field_name):
        return [scaffold]
    if _unresolved(card, field_name):
        return [UNSPECIFIED]
    return [UNSPECIFIED]


def build_harness_lines(card: RequirementCard) -> dict[str, list[str]]:
    """Return section title → lines for the long-horizon task contract."""
    task = card.task_identity
    identity: list[str] = ["Role: long-horizon coding agent"]
    if _populated(task.task_type):
        identity.append(f"Task type: {task.task_type.strip()}")
    if _populated(task.objective):
        identity.append(f"Objective: {task.objective.strip()}")
    elif _unresolved(card, "task_identity.objective"):
        identity.append(f"Objective: {UNSPECIFIED}")
    if _populated(task.environment):
        identity.append(f"Environment: {task.environment.strip()}")
    elif _unresolved(card, "task_identity.environment"):
        identity.append(f"Environment: {UNSPECIFIED}")
    extra = _list_clean(task.additional_constraints)
    if extra:
        identity.extend(f"Additional constraint: {item}" for item in extra)
    if card.optimization_targets.clarity and str(card.optimization_targets.clarity).strip():
        identity.append(f"Optimization priority: {card.optimization_targets.clarity.strip()}")

    from prompt_piper_api.domain.application_requirements import APPLICATION_QUESTIONS, applicable_application_fields
    relevant = applicable_application_fields(card)
    for question in APPLICATION_QUESTIONS:
        value = card.get_leaf(question.field_name).strip()
        if value or question.field_name in relevant:
            identity.append(f"{question.section_title}: {value or 'unspecified (open decision)'}")
    sections: dict[str, list[str]] = {"Task Identity": identity}
    contract = card.agent_contract
    for question in CONTRACT_QUESTIONS:
        leaf = question.field_name.split(".", 1)[1]
        value = getattr(contract, leaf)
        if not value and card.application_requirements.harness_controls == "Use receiving harness controls" and leaf in {"execution_strategy", "failure_recovery", "persistent_memory", "resource_budget", "context_compaction", "rollback_protocol"}:
            value = "Use the receiving harness controls; no additional policy specified."
        sections[question.section_title] = _policy_lines(card, question.field_name, value)
    return sections


def build_harness_body(card: RequirementCard) -> str:
    """Plain-text long-horizon contract prompt for drafts, optimization, and API packs."""
    sections = build_harness_lines(card)
    rendered = [
        _render_section(title, sections[title])
        for title in HARNESS_SECTION_TITLES
        if sections.get(title)
    ]
    return "\n\n".join(part for part in rendered if part)


def build_harness_spec(card: RequirementCard) -> dict[str, object]:
    """Structured task-contract spec for JSON/YAML export."""
    lines = build_harness_lines(card)
    principles = []
    for index, title in enumerate(HARNESS_SECTION_TITLES, start=1):
        slug = title.lower().replace(" ", "_").replace("and", "and")
        principles.append(
            {
                "id": slug,
                "title": title,
                "order": index,
                "lines": lines.get(title, []),
            }
        )
    return {
        "schema_version": "2.0",
        "kind": "long_horizon_task_contract",
        "principles": principles,
        "system_prompt": HARNESS_SYSTEM_PROMPT,
        "source_card": card.coding_spec_dict(),
    }


def harness_markdown(card: RequirementCard, *, title: str = "Long-horizon coding agent contract") -> str:
    """Markdown wrapper around the plain-text contract body (for human paste)."""
    body = build_harness_body(card)
    return f"# {title}\n\n```text\n{body}\n```\n"

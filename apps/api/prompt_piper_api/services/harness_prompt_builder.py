"""Build long-horizon task-contract prompts from a RequirementCard.

Optimized / API-bound bodies use the same 16-question contract as the draft.
Clarity is the goal; these prompts are expected to be long.
"""

from __future__ import annotations

from prompt_piper_api.domain.agent_contract import CONTRACT_QUESTIONS
from prompt_piper_api.domain.harness import HARNESS_SECTION_TITLES, HARNESS_SYSTEM_PROMPT
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.clarification_question_ranker import is_unspecified_answer
from prompt_piper_api.services.contract_resolver import resolve_contract

UNSPECIFIED = "unspecified"


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


def build_harness_lines(card: RequirementCard) -> dict[str, list[str]]:
    """Return section title → lines for the long-horizon task contract."""
    resolved = resolve_contract(card)
    card = resolved.card
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
        identity.append(
            "Implementation environment: delegated to the receiving agent; "
            "inspect project constraints and actual execution environment."
        )
    extra = _list_clean(task.additional_constraints)
    if extra:
        identity.extend(f"Additional constraint: {item}" for item in extra)
    if card.optimization_targets.clarity and str(card.optimization_targets.clarity).strip():
        identity.append(f"Optimization priority: {card.optimization_targets.clarity.strip()}")

    from prompt_piper_api.domain.application_requirements import (
        APPLICATION_QUESTIONS,
        applicable_application_fields,
    )

    relevant = applicable_application_fields(card)
    for question in APPLICATION_QUESTIONS:
        value = card.get_leaf(question.field_name).strip()
        source = resolved.sources[question.field_name]
        if source != "not_applicable" and (value or question.field_name in relevant):
            label = {"default": "Workbench default", "delegated": "Developer responsibility"}.get(
                source
            )
            prefix = f"[{label}] " if label else ""
            identity.append(
                f"{question.section_title}: {prefix}"
                f"{value or 'unspecified (open architectural decision)'}"
            )
    for field_name in resolved.unresolved_fields:
        identity.append(
            f"Open architectural decision: {field_name} — unspecified; "
            "clarify before work that depends on it."
        )
    identity.append(
        "Workbench defaults and developer responsibilities apply only within "
        "accepted requirements and receiving-harness permissions. Explicit "
        "requirements take precedence; escalate conflicts instead of silently "
        "choosing a winner."
    )
    sections: dict[str, list[str]] = {"Task Identity": identity}
    contract = card.agent_contract
    for question in CONTRACT_QUESTIONS:
        leaf = question.field_name.split(".", 1)[1]
        value = getattr(contract, leaf)
        label = "[Workbench default] " if resolved.sources[question.field_name] == "default" else ""
        sections[question.section_title] = [label + value]
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
        "resolved_card": resolve_contract(card).coding_spec_dict(),
    }


def harness_markdown(
    card: RequirementCard, *, title: str = "Long-horizon coding agent contract"
) -> str:
    """Markdown wrapper around the plain-text contract body (for human paste)."""
    body = build_harness_body(card)
    return f"# {title}\n\n```text\n{body}\n```\n"

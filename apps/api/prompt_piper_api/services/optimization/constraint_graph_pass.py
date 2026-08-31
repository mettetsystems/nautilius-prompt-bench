from __future__ import annotations

import re

from prompt_piper_api.domain.optimization import ConstraintGraph, ConstraintSlot, DetectedConflict
from prompt_piper_api.domain.requirement_card import RequirementCard

_SECTION_RE = re.compile(
    r"^(Task Identity|Definition of Done|Change Scope|Architecture Policy|"
    r"Discovery Policy|Execution Strategy|Validation Strategy|Failure Recovery|"
    r"Autonomy Policy|Persistent Agent Memory|Completion Contract|"
    r"Resource and Budget Governance|Tool Safety and Shell Restrictions|"
    r"Context Compaction and State Persistence|Rollback and Backtracking|"
    r"Escalation and HITL Interruption|Dependency and Security Verification|"
    r"Long-Horizon Coding Agent Contract|"
    r"Technical Context|Core Task and Scope|Inputs, Outputs, and Contracts|"
    r"Architectural Rules and Constraints|Edge Cases and Error Strategy|"
    r"Response Formatting|Role and Objective|Tech Stack|Context and Input|"
    r"Constraints|Expected Output)\n-+\n",
    re.MULTILINE | re.IGNORECASE,
)

_CONFLICT_RULES: tuple[tuple[str, str, str, bool], ...] = (
    (
        r"\b(exhaustive|comprehensive|all details)\b",
        r"\b(minimal tokens|be concise|keep it brief|short answer|code only)\b",
        "be exhaustive vs minimal tokens",
        True,
    ),
    (
        r"\b(minimum[- ]necessary change|only files named)\b",
        r"\b((?:may|can|allowed to) rewrite unrelated|unrestricted authority|change anything)\b",
        "minimum-necessary change vs unrestricted edits",
        True,
    ),
    (
        r"\b(pause and persist|request human review)\b",
        r"\b(never pause|never escalate|spin indefinitely)\b",
        "pause-and-persist vs never stop",
        True,
    ),
    (
        r"\b(standard library only|stdlib only|no third[- ]party)\b",
        r"\b(may add|add (a |the )?(well-known|new) packages?|pip install|npm install)\b",
        "stdlib-only vs adding new dependencies",
        True,
    ),
    (
        r"\bno force[- ]push\b",
        r"\b(git push --force is allowed|force[- ]push(?:es)? allowed|may force[- ]push)\b",
        "no force-push vs force-push allowed",
        True,
    ),
)


def estimate_tokens(text: str) -> int:
    return len(text.split())


def extract_section(body: str, title: str) -> list[str]:
    """Return non-empty lines under a title + dash-underline header.

    Markdown table separators such as ``| --- | --- |`` are not section
    underlines. A DOTALL lookahead from the next letter-line to the next
    dash-line previously swallowed Task Identity down to a single line
    whenever a pasted table sat in that section.
    """
    lines = body.splitlines()
    wanted = title.strip().lower()
    capturing = False
    captured: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        nxt = lines[index + 1] if index + 1 < len(lines) else ""
        if line.strip() and re.fullmatch(r"-+", nxt.strip()):
            if capturing:
                break
            if line.strip().lower() == wanted:
                capturing = True
                index += 2
                continue
        if capturing and line.strip():
            captured.append(line.strip())
        index += 1
    return captured


class ConstraintGraphPass:
    """Pass 1: normalize instructions into typed slots and detect contradictions."""

    def run(self, body: str, card: RequirementCard) -> ConstraintGraph:
        slots: dict[str, list[str]] = {slot.value: [] for slot in ConstraintSlot}
        contract = card.agent_contract
        task = card.task_identity

        if task.objective.strip():
            slots[ConstraintSlot.OBJECTIVE.value].append(task.objective.strip())
        slots[ConstraintSlot.OBJECTIVE.value].extend(extract_section(body, "Task Identity"))
        if contract.definition_of_done.strip():
            slots[ConstraintSlot.OBJECTIVE.value].append(contract.definition_of_done.strip())

        if task.environment.strip():
            slots[ConstraintSlot.AUDIENCE.value].append(task.environment.strip())

        if contract.change_scope.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.change_scope.strip())
        if contract.architecture_policy.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.architecture_policy.strip())
        if contract.discovery_policy.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.discovery_policy.strip())
        if contract.execution_strategy.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.execution_strategy.strip())
        slots[ConstraintSlot.SCOPE.value].extend(task.additional_constraints)

        if contract.tool_safety.strip():
            slots[ConstraintSlot.EXCLUSIONS.value].append(contract.tool_safety.strip())
        if contract.dependency_security.strip():
            slots[ConstraintSlot.EXCLUSIONS.value].append(contract.dependency_security.strip())

        if contract.completion_contract.strip():
            slots[ConstraintSlot.FORMAT.value].append(contract.completion_contract.strip())
        slots[ConstraintSlot.FORMAT.value].extend(extract_section(body, "Completion Contract"))

        if contract.resource_budget.strip():
            slots[ConstraintSlot.TOKEN_BUDGET.value].append(contract.resource_budget.strip())
        if contract.context_compaction.strip():
            slots[ConstraintSlot.VERBOSITY.value].append(contract.context_compaction.strip())
        if contract.persistent_memory.strip():
            slots[ConstraintSlot.ARTIFACT_REQUIRED.value].append(contract.persistent_memory.strip())
        if contract.validation_strategy.strip():
            slots[ConstraintSlot.ARTIFACT_REQUIRED.value].append(contract.validation_strategy.strip())
        if contract.failure_recovery.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.failure_recovery.strip())
        if contract.autonomy_policy.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.autonomy_policy.strip())
        if contract.rollback_protocol.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.rollback_protocol.strip())
        if contract.escalation_rules.strip():
            slots[ConstraintSlot.SCOPE.value].append(contract.escalation_rules.strip())

        binding = self._binding_instructions(slots)
        contradictions = self._detect_contradictions(body, slots)

        return ConstraintGraph(
            slots={key: values for key, values in slots.items() if values},
            binding_instructions=binding,
            contradictions=contradictions,
        )

    @staticmethod
    def _binding_instructions(slots: dict[str, list[str]]) -> list[str]:
        binding: list[str] = []
        for slot in (
            ConstraintSlot.OBJECTIVE,
            ConstraintSlot.TOKEN_BUDGET,
            ConstraintSlot.FORMAT,
            ConstraintSlot.MUST_CITE,
            ConstraintSlot.ARTIFACT_REQUIRED,
            ConstraintSlot.SCOPE,
            ConstraintSlot.EXCLUSIONS,
        ):
            binding.extend(slots.get(slot.value, []))
        return binding

    @staticmethod
    def _detect_contradictions(body: str, slots: dict[str, list[str]]) -> list[DetectedConflict]:
        combined = body + "\n" + "\n".join(
            value for values in slots.values() for value in values
        )
        conflicts: list[DetectedConflict] = []
        for left_pattern, right_pattern, description, requires_human in _CONFLICT_RULES:
            left_match = re.search(left_pattern, combined, re.I)
            right_match = re.search(right_pattern, combined, re.I)
            if left_match and right_match:
                conflicts.append(
                    DetectedConflict(
                        left_instruction=left_match.group(0),
                        right_instruction=right_match.group(0),
                        description=description,
                        requires_human_decision=requires_human,
                    )
                )
        return conflicts

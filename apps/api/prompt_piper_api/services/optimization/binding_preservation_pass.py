from __future__ import annotations

import re

from prompt_piper_api.domain.optimization import ConstraintGraph
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.optimization.constraint_graph_pass import extract_section
from prompt_piper_api.services.requirement_capture import (
    RequirementCaptureEvaluator,
    body_chunks,
    collect_optimization_binding_phrases,
    normalize_phrase_for_capture,
)

_SECTION_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Task Identity",
        ("objective:", "task type:", "environment:", "role:", "additional constraint"),
    ),
    (
        "Definition of Done",
        ("complete", "partial", "blocked", "failed", "acceptance"),
    ),
    (
        "Change Scope",
        ("minimum-necessary", "minimum necessary", "may not", "secrets"),
    ),
    (
        "Architecture Policy",
        ("existing project patterns", "modularity", "stdlib"),
    ),
    (
        "Discovery Policy",
        ("inspect", "before making substantial", "implementation plan"),
    ),
    (
        "Execution Strategy",
        ("lifecycle", "implement small unit", "milestone"),
    ),
    (
        "Validation Strategy",
        ("validation pyramid", "tests probably pass", "pytest"),
    ),
    (
        "Failure Recovery",
        ("hypothesis", "minimal fix", "suppress an error"),
    ),
    (
        "Autonomy Policy",
        ("escalate", "autonomous", "high-impact"),
    ),
    (
        "Persistent Agent Memory",
        (".agent/", "plan.md", "status.md", "decisions.md", "issues.md"),
    ),
    (
        "Completion Contract",
        ("completion report", "run instructions", "acceptance criteria"),
    ),
    (
        "Resource and Budget Governance",
        ("api calls", "wall-clock", "pause_and_persist", "budget"),
    ),
    (
        "Tool Safety and Shell Restrictions",
        ("force", "rm -rf", "secret", "sandbox"),
    ),
    (
        "Context Compaction and State Persistence",
        ("compaction", "context window", "reinject"),
    ),
    (
        "Rollback and Backtracking",
        ("git reset", "checkpoint", "last green"),
    ),
    (
        "Escalation and HITL Interruption",
        ("missing credentials", "human", "pause execution"),
    ),
    (
        "Dependency and Security Verification",
        ("sast", "license", "vulnerability", "mit", "apache"),
    ),
)


def _preferred_section_for_phrase(phrase: str, *, harness_body: bool) -> str:
    del harness_body
    lowered = phrase.lower()
    for section, hints in _SECTION_HINTS:
        if any(hint in lowered for hint in hints):
            return section
    return "Task Identity"


def _looks_like_harness(body: str) -> bool:
    lowered = body.lower()
    return "task identity" in lowered or ("role and objective" in lowered and "tech stack" in lowered)


class BindingPreservationPass:
    """Ensure binding constraint-graph instructions survive compression passes."""

    def __init__(self, evaluator: RequirementCaptureEvaluator | None = None) -> None:
        self._evaluator = evaluator or RequirementCaptureEvaluator()

    def run(
        self,
        body: str,
        graph: ConstraintGraph,
        card: RequirementCard,
    ) -> tuple[str, list[str]]:
        phrases = collect_optimization_binding_phrases(graph, card)
        chunks = body_chunks(body)
        missing = [
            phrase
            for phrase in phrases
            if not self._evaluator.captures_phrase(phrase, body, chunks)
        ]
        if not missing:
            return body, []

        harness_body = _looks_like_harness(body)
        preserved: list[str] = []
        by_section: dict[str, list[str]] = {}
        for phrase in missing:
            section = _preferred_section_for_phrase(phrase, harness_body=harness_body)
            by_section.setdefault(section, []).append(phrase)

        updated = body
        for section_title, section_phrases in by_section.items():
            constraints = extract_section(updated, section_title)
            existing = {normalize_phrase_for_capture(line) for line in constraints}
            added = False
            for phrase in section_phrases:
                key = normalize_phrase_for_capture(phrase)
                if key in existing:
                    continue
                constraints.append(phrase)
                existing.add(key)
                preserved.append(f"Preserved binding requirement: {phrase}")
                added = True
            if not added:
                continue
            if re.search(
                rf"^{re.escape(section_title)}\n-+\n",
                updated,
                re.MULTILINE | re.IGNORECASE,
            ):
                updated = self._replace_section(updated, section_title, constraints)
            else:
                divider = "-" * len(section_title)
                updated = (
                    f"{updated.rstrip()}\n\n{section_title}\n{divider}\n"
                    + "\n".join(constraints)
                )

        return updated, preserved

    @staticmethod
    def _replace_section(body: str, title: str, lines: list[str]) -> str:
        pattern = re.compile(
            rf"^({re.escape(title)}\n-+\n)(.*?)(?=\n[A-Za-z].*\n-+\n|\Z)",
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        replacement = r"\1" + "\n".join(lines) + "\n"
        updated, count = pattern.subn(replacement, body, count=1)
        return updated if count else body

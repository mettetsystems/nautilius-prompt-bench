from __future__ import annotations

import re

from prompt_piper_api.domain.optimization import ConstraintGraph, DetectedConflict
from prompt_piper_api.services.optimization.constraint_graph_pass import _CONFLICT_RULES


class DeconflictionPass:
    """Pass 4: detect and resolve contradictions; surface hard conflicts to the user."""

    def run(
        self,
        body: str,
        graph: ConstraintGraph,
    ) -> tuple[str, list[DetectedConflict], list[str]]:
        resolved_notes: list[str] = []
        hard_conflicts: list[DetectedConflict] = []
        updated_body = body

        for conflict in graph.contradictions:
            if not conflict.requires_human_decision:
                updated_body, note = self._auto_resolve(updated_body, conflict)
                if note:
                    resolved_notes.append(note)
                    conflict.resolved = True
                    conflict.resolution = note
                continue
            hard_conflicts.append(conflict)

        updated_body, soft_resolved = self._resolve_soft_conflicts(updated_body)
        resolved_notes.extend(soft_resolved)

        return updated_body, hard_conflicts, resolved_notes

    @staticmethod
    def _auto_resolve(body: str, conflict: DetectedConflict) -> tuple[str, str | None]:
        return body, None

    @staticmethod
    def _resolve_soft_conflicts(body: str) -> tuple[str, list[str]]:
        resolved: list[str] = []
        updated = body

        if re.search(r"\bprioritize clarity\b", body, re.I) and re.search(
            r"\bkeep it brief\b", body, re.I
        ):
            updated = re.sub(
                r"\bkeep it brief\b",
                "keep operational rules explicit",
                updated,
                flags=re.I,
            )
            resolved.append("Kept clarity over brevity when both were requested.")

        return updated, resolved

    @staticmethod
    def detect_in_body(body: str) -> list[DetectedConflict]:
        conflicts: list[DetectedConflict] = []
        for left_pattern, right_pattern, description, requires_human in _CONFLICT_RULES:
            left_match = re.search(left_pattern, body, re.I)
            right_match = re.search(right_pattern, body, re.I)
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

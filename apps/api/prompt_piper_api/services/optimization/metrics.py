from __future__ import annotations

from prompt_piper_api.domain.agent_contract import CONTRACT_FIELD_NAMES
from prompt_piper_api.domain.optimization import (
    ConstraintGraph,
    ConstraintSlot,
    DetectedConflict,
    OptimizationChangeLog,
    OptimizationMetrics,
    OptimizationResult,
    OptimizationTargetMetrics,
)
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.clarification_question_ranker import is_unspecified_answer
from prompt_piper_api.services.optimization.constraint_graph_pass import estimate_tokens


class OptimizationMetricsCalculator:
    """Compute clarity-first target scores and informational token metrics."""

    RICHNESS_FIELDS = (
        ConstraintSlot.OBJECTIVE,
        ConstraintSlot.AUDIENCE,
        ConstraintSlot.SCOPE,
        ConstraintSlot.EXCLUSIONS,
        ConstraintSlot.FORMAT,
        ConstraintSlot.ARTIFACT_REQUIRED,
        ConstraintSlot.TOKEN_BUDGET,
    )

    def compute(
        self,
        *,
        original_body: str,
        optimized_body: str,
        graph: ConstraintGraph,
        removed_count: int,
        hard_conflicts: list[DetectedConflict],
        resolved_count: int,
        card: RequirementCard | None = None,
    ) -> OptimizationMetrics:
        original_tokens = estimate_tokens(original_body)
        optimized_tokens = max(estimate_tokens(optimized_body), 1)
        constraint_count = sum(len(values) for values in graph.slots.values())
        binding_count = len(graph.binding_instructions)

        richness = self._richness_score(graph)
        density = min(1.0, (constraint_count / optimized_tokens) * 8.0)
        efficiency = self._efficiency_score(original_tokens, optimized_tokens)
        denoising = min(1.0, removed_count / max(removed_count + 1, 1))
        if removed_count == 0:
            denoising = 0.7 if original_tokens <= optimized_tokens else 0.5
        deconfliction = self._deconfliction_score(hard_conflicts, resolved_count, graph)
        clarity = self._clarity_score(
            card=card,
            body=optimized_body,
            richness=richness,
            deconfliction=deconfliction,
        )

        reduction = 0.0
        if original_tokens > 0:
            reduction = max(0.0, (original_tokens - optimized_tokens) / original_tokens * 100.0)

        return OptimizationMetrics(
            original_token_count=original_tokens,
            optimized_token_count=optimized_tokens,
            token_reduction_pct=round(reduction, 2),
            constraints_per_token=round(binding_count / optimized_tokens, 3),
            targets=OptimizationTargetMetrics(
                clarity=round(clarity, 3),
                richness=round(richness, 3),
                density=round(density, 3),
                efficiency=round(efficiency, 3),
                denoising=round(denoising, 3),
                deconfliction=round(deconfliction, 3),
            ),
        )

    def _clarity_score(
        self,
        *,
        card: RequirementCard | None,
        body: str,
        richness: float,
        deconfliction: float,
    ) -> float:
        coverage = 0.0
        if card is not None:
            filled = 0
            for field_name in CONTRACT_FIELD_NAMES:
                value = card.get_leaf(field_name)
                if isinstance(value, str) and value.strip() and not is_unspecified_answer(value):
                    filled += 1
            coverage = filled / max(len(CONTRACT_FIELD_NAMES), 1)
        lowered = body.lower()
        explicitness = 0.0
        if "complete" in lowered and "partial" in lowered:
            explicitness += 0.25
        if ".agent/" in lowered:
            explicitness += 0.25
        if "acceptance" in lowered or "evidence" in lowered:
            explicitness += 0.25
        if "task identity" in lowered or "definition of done" in lowered:
            explicitness += 0.25
        explicitness = min(1.0, explicitness)
        return min(1.0, 0.45 * coverage + 0.25 * explicitness + 0.15 * richness + 0.15 * deconfliction)

    def _richness_score(self, graph: ConstraintGraph) -> float:
        covered = sum(
            1 for slot in self.RICHNESS_FIELDS if graph.slots.get(slot.value)
        )
        return covered / len(self.RICHNESS_FIELDS)

    @staticmethod
    def _efficiency_score(original_tokens: int, optimized_tokens: int) -> float:
        """Reward preserving or expanding meaning; penalize aggressive cuts."""
        if original_tokens == 0:
            return 1.0
        ratio = optimized_tokens / original_tokens
        if ratio >= 1.0:
            return 1.0
        if ratio >= 0.9:
            return 0.9
        if ratio >= 0.7:
            return 0.6
        return 0.3

    @staticmethod
    def _deconfliction_score(
        hard_conflicts: list[DetectedConflict],
        resolved_count: int,
        graph: ConstraintGraph,
    ) -> float:
        total = len(graph.contradictions)
        if total == 0 and not hard_conflicts:
            return 1.0
        unresolved = len(hard_conflicts)
        if unresolved > 0:
            return max(0.0, 1.0 - unresolved / max(total + unresolved, 1))
        return min(1.0, 0.5 + resolved_count * 0.25)


class ApprovalExportPass:
    """Pass 5: package optimized prompt, metrics, and approval gate."""

    def run(
        self,
        *,
        original_body: str,
        optimized_body: str,
        graph: ConstraintGraph,
        card: RequirementCard,
        removed: list[str],
        compressed: list[str],
        conflicts_resolved: list[str],
        hard_conflicts: list[DetectedConflict],
    ) -> OptimizationResult:
        metrics = OptimizationMetricsCalculator().compute(
            original_body=original_body,
            optimized_body=optimized_body,
            graph=graph,
            removed_count=len(removed),
            hard_conflicts=hard_conflicts,
            resolved_count=len(conflicts_resolved),
            card=card,
        )

        return OptimizationResult(
            original_body=original_body,
            optimized_body=optimized_body,
            constraint_graph=graph,
            metrics=metrics,
            changes=OptimizationChangeLog(
                removed=removed,
                compressed=[],
                clarified=compressed,
                conflicts_resolved=conflicts_resolved,
            ),
            hard_conflicts=hard_conflicts,
            export_ready=False,
            approved=False,
            passes_completed=[
                "constraint_graph",
                "clarity_expansion",
                "denoising",
                "deconfliction",
                "approval_export",
            ],
        )

    @staticmethod
    def objective_preserved(original_body: str, optimized_body: str, card: RequirementCard) -> bool:
        objective = card.objective.strip().lower()
        if not objective:
            return True
        return objective in optimized_body.lower() or objective in original_body.lower()

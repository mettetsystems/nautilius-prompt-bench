from __future__ import annotations

import re

from prompt_piper_api.config import get_settings
from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.draft_generator import UNSPECIFIED
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.format_checker import (
    coding_section_coverage,
    format_adherence_score,
    harness_section_coverage,
)
from prompt_piper_api.services.first_shot_readiness import assess_first_shot_readiness
from prompt_piper_api.services.optimization.constraint_graph_pass import ConstraintGraphPass
from prompt_piper_api.services.optimization.metrics import OptimizationMetricsCalculator
from prompt_piper_api.services.requirement_capture import RequirementCaptureEvaluator
from prompt_piper_api.services.semantic_precision import SemanticPrecisionEvaluator
from prompt_piper_api.services.tokenizer_approx import estimate_token_cost

_FIELD_SECTION_HINTS: dict[str, tuple[str, ...]] = {
    "task_identity.objective": ("objective", "task identity"),
    "task_identity.task_type": ("task type", "task identity"),
    "task_identity.environment": ("environment", "task identity"),
    "task_identity.additional_constraints": ("additional constraint", "task identity"),
    "agent_contract.definition_of_done": ("definition of done", "complete"),
    "agent_contract.change_scope": ("change scope", "minimum"),
    "agent_contract.architecture_policy": ("architecture policy", "patterns"),
    "agent_contract.discovery_policy": ("discovery policy", "inspect"),
    "agent_contract.execution_strategy": ("execution strategy", "lifecycle"),
    "agent_contract.validation_strategy": ("validation strategy", "validation pyramid"),
    "agent_contract.failure_recovery": ("failure recovery", "hypothesis"),
    "agent_contract.autonomy_policy": ("autonomy policy", "escalate"),
    "agent_contract.persistent_memory": ("persistent agent memory", ".agent/"),
    "agent_contract.completion_contract": ("completion contract", "acceptance criteria"),
    "agent_contract.resource_budget": ("resource and budget", "api calls"),
    "agent_contract.tool_safety": ("tool safety", "sandbox"),
    "agent_contract.context_compaction": ("context compaction", "window"),
    "agent_contract.rollback_protocol": ("rollback", "checkpoint"),
    "agent_contract.escalation_rules": ("escalation", "human"),
    "agent_contract.dependency_security": ("dependency", "license"),
    "optimization_targets": ("optimization", "task identity"),
}


class PreInferenceMetricsService:
    """Compute deterministic pre-inference quality metrics."""

    def __init__(
        self,
        *,
        embedding: EmbeddingService | None = None,
        capture_evaluator: RequirementCaptureEvaluator | None = None,
    ) -> None:
        if capture_evaluator is not None:
            self._capture = capture_evaluator
        else:
            if embedding is None:
                settings = get_settings()
                embedding = EmbeddingService(
                    model_name=settings.prompt_piper_embedding_model,
                    prefer_fallback=settings.prompt_piper_embedding_fallback,
                )
            self._capture = RequirementCaptureEvaluator(embedding)
        self._precision = SemanticPrecisionEvaluator()

    def compute(
        self,
        body: str,
        card: RequirementCard,
        *,
        optimization: OptimizationResult | None = None,
        baseline_body: str | None = None,
    ) -> PreInferenceMetrics:
        graph = (
            optimization.constraint_graph
            if optimization is not None
            else ConstraintGraphPass().run(body, card)
        )
        hard_conflicts = (
            optimization.hard_conflicts
            if optimization is not None
            else graph.contradictions
        )

        if optimization is not None:
            targets = optimization.metrics.targets
        else:
            calc = OptimizationMetricsCalculator()
            targets = calc.compute(
                original_body=baseline_body or body,
                optimized_body=body,
                graph=graph,
                removed_count=0,
                hard_conflicts=list(hard_conflicts),
                resolved_count=0,
            ).targets

        precision = self._precision.evaluate(body)
        readiness = assess_first_shot_readiness(card)
        draft_coverage = coding_section_coverage(body)
        harness_coverage = harness_section_coverage(body)
        section_coverage = max(draft_coverage, harness_coverage)

        return PreInferenceMetrics(
            requirement_capture_score=self._capture.score(
                body,
                card,
                constraint_graph=graph if optimization is not None else None,
            ),
            unspecified_field_honesty=self._unspecified_field_honesty(body, card),
            instruction_clarity=self._instruction_clarity(body),
            hard_conflict_count=len(hard_conflicts),
            format_adherence=format_adherence_score(body),
            token_cost_estimate=estimate_token_cost(body),
            richness_score=targets.richness,
            density_score=targets.density,
            efficiency_score=targets.efficiency,
            denoising_score=targets.denoising,
            deconfliction_score=targets.deconfliction,
            semantic_precision_score=precision.score,
            vague_language_count=len(precision.findings),
            first_shot_readiness_score=readiness.score,
            first_shot_ready=readiness.ready,
            section_coverage=section_coverage,
        )

    def _unspecified_field_honesty(self, body: str, card: RequirementCard) -> float:
        if not card.unresolved_fields:
            return 1.0

        for field_name in card.unresolved_fields:
            if not self._field_marked_unspecified(body, card, field_name):
                return 0.0
        return 1.0

    @staticmethod
    def _field_marked_unspecified(body: str, card: RequirementCard, field_name: str) -> bool:
        if field_name == "optimization_targets":
            targets = card.optimization_targets.model_dump()
            if any(value is not None and str(value).strip() for value in targets.values()):
                return True
        else:
            try:
                value = card.get_leaf(field_name)
            except ValueError:
                value = ""
            if isinstance(value, list):
                if value:
                    return True
            elif isinstance(value, str) and value.strip():
                return True

        hints = _FIELD_SECTION_HINTS.get(
            field_name,
            (field_name.split(".")[-1].replace("_", " "),),
        )
        for hint in hints:
            pattern = re.compile(
                rf"{re.escape(hint)}[^\n]*\b{re.escape(UNSPECIFIED)}\b",
                re.IGNORECASE,
            )
            if pattern.search(body):
                return True
            if re.search(rf"\b{re.escape(UNSPECIFIED)}\b", body, re.I) and hint in body.lower():
                return True
        return False

    @staticmethod
    def _instruction_clarity(body: str) -> float:
        if not body.strip():
            return 0.0
        lines = [line.strip() for line in body.splitlines() if line.strip()]
        if not lines:
            return 0.0

        score = 0.0
        if any(
            line.lower().startswith(
                ("task identity", "definition of done", "change scope", "architecture")
            )
            for line in lines
        ):
            score += 0.4
        imperative = sum(
            1
            for line in lines
            if re.match(
                r"^(keep|use|meet|avoid|do not|provide|implement|write|return|raise)\b",
                line,
                re.I,
            )
        )
        score += min(0.3, imperative * 0.1)
        avg_len = sum(len(line.split()) for line in lines) / len(lines)
        if 4 <= avg_len <= 24:
            score += 0.3
        elif avg_len < 40:
            score += 0.15
        return round(min(1.0, score), 2)

from __future__ import annotations

from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics, QualityGateResult
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.first_shot_readiness import (
    SEMANTIC_PRECISION_SOFT_THRESHOLD,
    assess_first_shot_readiness,
    first_shot_warning_messages,
)
from prompt_piper_api.services.pre_inference_metrics_service import PreInferenceMetricsService
from prompt_piper_api.services.regression_evaluator import RegressionEvaluator, RegressionSummary


class QualityGateService:
    """Pre-inference quality gate for finalized and optimized prompts."""

    MIN_REQUIREMENT_CAPTURE = 0.90
    MAX_REGRESSION_LOSS_RATE = 0.10
    # Soft→hard: precision below this becomes a hard failure when enforce_first_shot=True.
    MIN_SEMANTIC_PRECISION = SEMANTIC_PRECISION_SOFT_THRESHOLD

    def __init__(
        self,
        *,
        metrics_service: PreInferenceMetricsService | None = None,
        regression_evaluator: RegressionEvaluator | None = None,
        enforce_first_shot: bool = False,
    ) -> None:
        self._metrics = metrics_service or PreInferenceMetricsService()
        self._regression = regression_evaluator or RegressionEvaluator()
        self._enforce_first_shot = enforce_first_shot

    def compute_metrics(
        self,
        body: str,
        card: RequirementCard,
        *,
        optimization: OptimizationResult | None = None,
        baseline_body: str | None = None,
    ) -> PreInferenceMetrics:
        return self._metrics.compute(
            body,
            card,
            optimization=optimization,
            baseline_body=baseline_body,
        )

    def evaluate(
        self,
        metrics: PreInferenceMetrics,
        *,
        card: RequirementCard | None = None,
        safety_failures: list[str] | None = None,
        regression: RegressionSummary | None = None,
    ) -> QualityGateResult:
        failures: list[str] = []
        warnings: list[str] = []
        safety = list(safety_failures or [])
        if regression is not None:
            safety.extend(regression.safety_failures)

        if metrics.requirement_capture_score < self.MIN_REQUIREMENT_CAPTURE:
            failures.append(
                "requirement_capture_score below 0.90 "
                f"({metrics.requirement_capture_score})"
            )
        if metrics.unspecified_field_honesty != 1.0:
            failures.append(
                "unspecified_field_honesty must be 1.00 "
                f"({metrics.unspecified_field_honesty})"
            )
        if metrics.format_adherence != 1.0:
            failures.append(
                f"format_adherence must be 1.00 ({metrics.format_adherence})"
            )
        if metrics.hard_conflict_count > 0:
            failures.append(
                f"hard_conflict_count must be 0 ({metrics.hard_conflict_count})"
            )
        if safety:
            failures.append("critical safety test failed")

        regression_loss_rate = regression.loss_rate if regression else None
        if regression is not None and regression.loss_rate > self.MAX_REGRESSION_LOSS_RATE:
            failures.append(
                "optimized version loses pairwise comparison on more than 10% "
                f"of regression cases ({regression.loss_rate:.1%})"
            )

        readiness = assess_first_shot_readiness(card) if card is not None else None
        if readiness is not None:
            warnings.extend(
                first_shot_warning_messages(
                    readiness,
                    semantic_precision_score=metrics.semantic_precision_score,
                    section_coverage=metrics.section_coverage,
                )
            )
        elif metrics.semantic_precision_score < self.MIN_SEMANTIC_PRECISION:
            warnings.append(
                "semantic_precision_score below "
                f"{self.MIN_SEMANTIC_PRECISION:.2f} ({metrics.semantic_precision_score:.2f})"
            )

        if self._enforce_first_shot:
            if metrics.semantic_precision_score < self.MIN_SEMANTIC_PRECISION:
                failures.append(
                    "semantic_precision_score below "
                    f"{self.MIN_SEMANTIC_PRECISION:.2f} ({metrics.semantic_precision_score})"
                )
            if readiness is not None and not readiness.ready:
                failures.append(
                    "first_shot_readiness gaps remain: "
                    + "; ".join(risk.message for risk in readiness.risks[:4])
                )

        return QualityGateResult(
            passed=not failures,
            failures=failures,
            warnings=warnings,
            metrics=metrics,
            regression_loss_rate=regression_loss_rate,
            regression_cases_run=regression.cases_run if regression else 0,
            safety_failures=safety,
        )

    def evaluate_for_approval(
        self,
        body: str,
        card: RequirementCard,
        optimization: OptimizationResult,
    ) -> QualityGateResult:
        metrics = self.compute_metrics(
            body,
            card,
            optimization=optimization,
            baseline_body=optimization.original_body,
        )
        return self.evaluate(metrics, card=card)

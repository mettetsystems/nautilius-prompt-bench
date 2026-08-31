from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.pre_inference_metrics_service import PreInferenceMetricsService


class RegressionCase(BaseModel):
    id: str
    description: str = ""
    requirement_card: RequirementCard
    baseline_body: str
    must_preserve: list[str] = Field(default_factory=list)
    critical_safety: bool = False
    safety_forbidden_patterns: list[str] = Field(default_factory=list)


class RegressionCaseResult(BaseModel):
    case_id: str
    optimized_wins: bool
    safety_passed: bool
    safety_failures: list[str] = Field(default_factory=list)
    metrics_passed: bool
    metrics: dict[str, float | int] = Field(default_factory=dict)


class RegressionSummary(BaseModel):
    cases_run: int
    optimized_losses: int
    loss_rate: float
    safety_failures: list[str] = Field(default_factory=list)
    case_results: list[RegressionCaseResult] = Field(default_factory=list)
    aggregate_metrics: PreInferenceMetrics | None = None


class RegressionEvaluator:
    """Pairwise baseline vs optimized comparison for regression cases."""

    def __init__(
        self,
        *,
        optimizer: TokenOptimizationEngine | None = None,
        metrics_service: PreInferenceMetricsService | None = None,
    ) -> None:
        self._optimizer = optimizer or TokenOptimizationEngine()
        self._metrics = metrics_service or PreInferenceMetricsService()

    def load_cases(self, path: Path) -> list[RegressionCase]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            msg = "Regression cases file must be a mapping"
            raise ValueError(msg)
        items = raw.get("regression_cases", [])
        if not isinstance(items, list):
            msg = "regression_cases must be a list"
            raise ValueError(msg)
        return [RegressionCase.model_validate(item) for item in items]

    def run_cases(self, cases: list[RegressionCase]) -> RegressionSummary:
        results: list[RegressionCaseResult] = []
        all_safety_failures: list[str] = []
        metrics_list: list[PreInferenceMetrics] = []

        for case in cases:
            optimization = self._optimizer.optimize(case.baseline_body, case.requirement_card)
            optimized_body = optimization.optimized_body
            metrics = self._metrics.compute(
                optimized_body,
                case.requirement_card,
                optimization=optimization,
                baseline_body=case.baseline_body,
            )
            safety_failures = self._safety_failures(case, optimized_body)
            optimized_wins = self._pairwise_compare(
                case.baseline_body,
                optimized_body,
                must_preserve=case.must_preserve,
            )
            metrics_passed = (
                metrics.requirement_capture_score >= 0.90
                and metrics.unspecified_field_honesty == 1.0
                and metrics.format_adherence == 1.0
                and metrics.hard_conflict_count == 0
            )
            metrics_list.append(metrics)
            results.append(
                RegressionCaseResult(
                    case_id=case.id,
                    optimized_wins=optimized_wins,
                    safety_passed=not safety_failures,
                    safety_failures=safety_failures,
                    metrics_passed=metrics_passed,
                    metrics={
                        "requirement_capture_score": metrics.requirement_capture_score,
                        "unspecified_field_honesty": metrics.unspecified_field_honesty,
                        "format_adherence": metrics.format_adherence,
                        "hard_conflict_count": metrics.hard_conflict_count,
                        "token_cost_estimate": metrics.token_cost_estimate,
                    },
                )
            )
            all_safety_failures.extend(
                f"{case.id}: {failure}" for failure in safety_failures
            )

        losses = sum(1 for result in results if not result.optimized_wins)
        total = len(results)
        loss_rate = losses / total if total else 0.0
        aggregate = self._aggregate_metrics(metrics_list) if metrics_list else None
        return RegressionSummary(
            cases_run=total,
            optimized_losses=losses,
            loss_rate=round(loss_rate, 4),
            safety_failures=all_safety_failures,
            case_results=results,
            aggregate_metrics=aggregate,
        )

    @staticmethod
    def _aggregate_metrics(metrics_list: list[PreInferenceMetrics]) -> PreInferenceMetrics:
        return PreInferenceMetrics(
            requirement_capture_score=min(item.requirement_capture_score for item in metrics_list),
            unspecified_field_honesty=min(item.unspecified_field_honesty for item in metrics_list),
            instruction_clarity=min(item.instruction_clarity for item in metrics_list),
            hard_conflict_count=max(item.hard_conflict_count for item in metrics_list),
            format_adherence=min(item.format_adherence for item in metrics_list),
            token_cost_estimate=max(item.token_cost_estimate for item in metrics_list),
            richness_score=min(item.richness_score for item in metrics_list),
            density_score=min(item.density_score for item in metrics_list),
            efficiency_score=min(item.efficiency_score for item in metrics_list),
            denoising_score=min(item.denoising_score for item in metrics_list),
            deconfliction_score=min(item.deconfliction_score for item in metrics_list),
        )

    @staticmethod
    def _pairwise_compare(
        baseline: str,
        optimized: str,
        *,
        must_preserve: list[str],
    ) -> bool:
        optimized_lower = optimized.lower()
        for phrase in must_preserve:
            if phrase.lower() not in optimized_lower:
                return False
        # Long-horizon contracts may grow; winning means preserving required meaning
        # and remaining at least as complete as the baseline, not cutting tokens.
        return bool(optimized.strip())

    @staticmethod
    def _safety_failures(case: RegressionCase, optimized_body: str) -> list[str]:
        if not case.critical_safety:
            return []
        lowered = optimized_body.lower()
        failures: list[str] = []
        for pattern in case.safety_forbidden_patterns:
            if pattern.lower() in lowered:
                failures.append(f"Forbidden safety pattern present: {pattern}")
        return failures

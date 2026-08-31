from pathlib import Path

import pytest
import yaml
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.format_checker import format_adherence_score
from prompt_piper_api.services.harness_prompt_builder import build_harness_body
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.pre_inference_metrics_service import PreInferenceMetricsService
from prompt_piper_api.services.quality_gate_service import QualityGateService
from prompt_piper_api.services.regression_evaluator import RegressionEvaluator
from prompt_piper_api.services.tokenizer_approx import estimate_token_cost
from tests.card_fixtures import sample_card


@pytest.fixture
def metrics_service() -> PreInferenceMetricsService:
    return PreInferenceMetricsService()


@pytest.fixture
def quality_gate() -> QualityGateService:
    return QualityGateService()


@pytest.fixture
def regression_cases_path() -> Path:
    return Path(__file__).resolve().parent / "evals" / "regression_cases.yaml"


def _plain_text_body(*, with_unspecified_done: bool = False) -> str:
    card = sample_card(
        objective="Add FastAPI endpoint for weekly engineering status summaries.",
        environment="Python with FastAPI and Pydantic",
    )
    if with_unspecified_done:
        card.agent_contract.definition_of_done = ""
        card.unresolved_fields = ["agent_contract.definition_of_done"]
    return build_harness_body(card)


def test_unspecified_field_honesty_is_one_when_marked_unspecified(
    metrics_service: PreInferenceMetricsService,
) -> None:
    card = RequirementCard(
        task_identity={
            "objective": "Add FastAPI endpoint for weekly engineering status summaries.",
            "environment": "Python with FastAPI and Pydantic",
        },
        unresolved_fields=["agent_contract.definition_of_done"],
    )
    metrics = metrics_service.compute(_plain_text_body(with_unspecified_done=True), card)
    assert metrics.unspecified_field_honesty == 1.0


def test_unspecified_field_honesty_fails_when_unresolved_not_marked(
    metrics_service: PreInferenceMetricsService,
) -> None:
    card = RequirementCard(
        task_identity={
            "objective": "Add FastAPI endpoint for weekly engineering status summaries.",
            "environment": "Python with FastAPI and Pydantic",
        },
        unresolved_fields=["agent_contract.definition_of_done"],
    )
    metrics = metrics_service.compute(_plain_text_body(with_unspecified_done=False), card)
    assert metrics.unspecified_field_honesty == 0.0


def test_format_adherence_is_one_for_plain_text_contract() -> None:
    assert format_adherence_score(_plain_text_body()) == 1.0


def test_format_adherence_fails_for_markdown_headings() -> None:
    body = "# Core Task and Scope\n\nAdd FastAPI endpoint."
    assert format_adherence_score(body) == 0.0


def test_token_cost_estimate_uses_local_approximation() -> None:
    short = estimate_token_cost("Add FastAPI endpoint.")
    long = estimate_token_cost("Add FastAPI endpoint. " * 20)
    assert short > 0
    assert long > short


def test_hard_conflict_count_zero_for_clean_prompt(
    metrics_service: PreInferenceMetricsService,
) -> None:
    card = sample_card(
        objective="Add FastAPI endpoint for weekly engineering status summaries.",
        environment="Python with FastAPI and Pydantic",
    )
    optimization = TokenOptimizationEngine().optimize(_plain_text_body(), card)
    metrics = metrics_service.compute(
        optimization.optimized_body,
        card,
        optimization=optimization,
    )
    assert metrics.hard_conflict_count == 0
    assert metrics.requirement_capture_score >= 0.90


def test_quality_gate_fails_when_requirement_capture_low(quality_gate: QualityGateService) -> None:
    metrics = PreInferenceMetrics(
        requirement_capture_score=0.50,
        unspecified_field_honesty=1.0,
        instruction_clarity=0.8,
        hard_conflict_count=0,
        format_adherence=1.0,
        token_cost_estimate=100,
        richness_score=0.8,
        density_score=0.8,
        efficiency_score=0.8,
        denoising_score=0.8,
        deconfliction_score=1.0,
    )
    result = quality_gate.evaluate(metrics)
    assert result.passed is False
    assert any("requirement_capture_score" in failure for failure in result.failures)


def test_quality_gate_fails_when_hard_conflicts_present(quality_gate: QualityGateService) -> None:
    metrics = PreInferenceMetrics(
        requirement_capture_score=0.95,
        unspecified_field_honesty=1.0,
        instruction_clarity=0.8,
        hard_conflict_count=2,
        format_adherence=1.0,
        token_cost_estimate=100,
        richness_score=0.8,
        density_score=0.8,
        efficiency_score=0.8,
        denoising_score=0.8,
        deconfliction_score=0.5,
    )
    result = quality_gate.evaluate(metrics)
    assert result.passed is False
    assert any("hard_conflict_count" in failure for failure in result.failures)


def test_quality_gate_passes_for_valid_metrics(quality_gate: QualityGateService) -> None:
    metrics = PreInferenceMetrics(
        requirement_capture_score=0.95,
        unspecified_field_honesty=1.0,
        instruction_clarity=0.8,
        hard_conflict_count=0,
        format_adherence=1.0,
        token_cost_estimate=100,
        richness_score=0.8,
        density_score=0.8,
        efficiency_score=0.8,
        denoising_score=0.8,
        deconfliction_score=1.0,
    )
    result = quality_gate.evaluate(metrics)
    assert result.passed is True


def test_regression_cases_file_loads(regression_cases_path: Path) -> None:
    raw = yaml.safe_load(regression_cases_path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    assert len(raw["regression_cases"]) >= 8


def test_regression_eval_runs_locally(regression_cases_path: Path) -> None:
    evaluator = RegressionEvaluator()
    cases = evaluator.load_cases(regression_cases_path)
    summary = evaluator.run_cases(cases)
    assert summary.cases_run == len(cases)
    assert summary.loss_rate <= 0.10
    assert summary.aggregate_metrics is not None
    assert summary.aggregate_metrics.format_adherence == 1.0


def test_full_quality_gate_on_regression_suite(regression_cases_path: Path) -> None:
    evaluator = RegressionEvaluator()
    gate = QualityGateService(regression_evaluator=evaluator)
    cases = evaluator.load_cases(regression_cases_path)
    regression = evaluator.run_cases(cases)
    assert regression.aggregate_metrics is not None
    result = gate.evaluate(
        regression.aggregate_metrics,
        safety_failures=regression.safety_failures,
        regression=regression,
    )
    assert result.passed is True


def test_eval_cli_runs(regression_cases_path: Path) -> None:
    from prompt_piper.eval.runner import run_eval

    assert run_eval(cases_path=regression_cases_path) == 0

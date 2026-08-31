from __future__ import annotations

from tests.card_fixtures import sample_card
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.pre_inference_metrics_service import PreInferenceMetricsService
from prompt_piper_api.services.quality_gate_service import QualityGateService
from prompt_piper_api.services.requirement_capture import RequirementCaptureEvaluator
from prompt_piper_api.services.harness_prompt_builder import build_harness_body


def _fastapi_card():
    return sample_card(
        objective=(
            "Implement a FastAPI endpoint that creates users with Pydantic validation "
            "and returns the persisted user record"
        ),
        extra_constraints=[
            "no speculative claims about schema",
            "cite existing model fields only",
        ],
    )


def _fastapi_canonical() -> str:
    return build_harness_body(_fastapi_card())


def test_mustang_like_optimization_passes_binding_capture_gate() -> None:
    card = _fastapi_card()
    canonical = _fastapi_canonical()
    optimization = TokenOptimizationEngine().optimize(canonical, card)
    metrics_service = PreInferenceMetricsService(
        capture_evaluator=RequirementCaptureEvaluator(EmbeddingService(prefer_fallback=True)),
    )
    metrics = metrics_service.compute(
        optimization.optimized_body,
        card,
        optimization=optimization,
    )

    assert metrics.requirement_capture_score >= 0.90
    assert metrics.unspecified_field_honesty == 1.0
    assert metrics.format_adherence == 1.0
    assert QualityGateService(metrics_service=metrics_service).evaluate_for_approval(
        optimization.optimized_body,
        card,
        optimization,
    ).passed

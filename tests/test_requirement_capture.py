from __future__ import annotations

from prompt_piper_api.domain.requirement_card import OptimizationTargets, RequirementCard
from tests.card_fixtures import sample_card
from prompt_piper_api.services.harness_prompt_builder import build_harness_body
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.optimization.constraint_graph_pass import ConstraintGraphPass
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.pre_inference_metrics_service import PreInferenceMetricsService
from prompt_piper_api.services.requirement_capture import (
    RequirementCaptureEvaluator,
    body_chunks,
    normalize_phrase_for_capture,
)
from prompt_piper_api.services.similarity_utils import hash_embed


class GroupedSemanticEmbedder:
    """Test embedder that maps concept groups to identical vectors."""

    _GROUPS: tuple[frozenset[str], ...] = (
        frozenset({"propeller", "fan looking part of an airplane", "the fan looking part of an airplane"}),
        frozenset({"hood scoop", "part the air goes into a car hood", "a hood scoop"}),
        frozenset({"fastapi", "python with fastapi"}),
    )

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            normalized = text.lower()
            group_id = "other"
            for index, group in enumerate(self._GROUPS):
                if any(token in normalized for token in group):
                    group_id = f"group-{index}"
                    break
            vectors.append(hash_embed(group_id, dimensions=384))
        return vectors


def test_normalize_phrase_for_capture_ignores_vague_words() -> None:
    original = "Don't use really big words for beginners"
    cleaned = "Don't use big words for beginners"
    assert normalize_phrase_for_capture(original) == normalize_phrase_for_capture(cleaned)


def test_binding_capture_ignores_optional_card_fields() -> None:
    card = RequirementCard(
        task_identity={
            "objective": "Add FastAPI endpoint for weekly engineering status summaries.",
            "task_type": "new feature logic",
            "environment": "Python with FastAPI",
        },
        optimization_targets=OptimizationTargets(richness="include enough detail"),
    )
    body = (
        "Task Identity\n-------------\n"
        "Task type: new feature logic\n"
        "Objective: Add FastAPI endpoint for weekly engineering status summaries.\n"
        "Environment: Python with FastAPI\n"
    )
    graph = ConstraintGraphPass().run(body, card)
    evaluator = RequirementCaptureEvaluator(EmbeddingService(prefer_fallback=True))
    full_score = evaluator.score(body, card)
    binding_score = evaluator.score(body, card, constraint_graph=graph)
    assert full_score < 1.0
    assert binding_score == 1.0


def test_verbatim_requirement_still_captures() -> None:
    evaluator = RequirementCaptureEvaluator(EmbeddingService(prefer_fallback=True))
    card = RequirementCard(
        task_identity={
            "objective": "Summarize weekly status",
            "environment": "Python with FastAPI",
        },
    )
    body = (
        "Task Identity\n-------------\nObjective: Summarize weekly status\n"
        "Environment: Python with FastAPI"
    )

    assert evaluator.score(body, card) == 1.0


def test_rephrased_constraint_can_capture_lexically() -> None:
    evaluator = RequirementCaptureEvaluator(EmbeddingService(prefer_fallback=True))
    card = RequirementCard(
        task_identity={"additional_constraints": ["Keep the response within 300 words"]}
    )
    body = (
        "Task Identity\n-------------\n"
        "Additional constraint: Keep the response within 300 words."
    )

    assert evaluator.captures_phrase(
        card.task_identity.additional_constraints[0],
        body,
        body_chunks(body),
    )


def test_precise_refinement_counts_as_capture() -> None:
    embedding = EmbeddingService(embedder=GroupedSemanticEmbedder())
    evaluator = RequirementCaptureEvaluator(embedding)
    requirement = "the fan looking part of an airplane"
    body = (
        "Inputs, Outputs, and Contracts\n"
        "------------------------------\n"
        "Output contract: Inspect the propeller assembly before flight."
    )

    assert evaluator.captures_phrase(requirement, body, body_chunks(body))


def test_unrelated_phrase_does_not_capture() -> None:
    embedding = EmbeddingService(embedder=GroupedSemanticEmbedder())
    evaluator = RequirementCaptureEvaluator(embedding)
    requirement = "the fan looking part of an airplane"
    body = (
        "Core Task and Scope\n-------------------\n"
        "Objective: Write release notes for the billing team."
    )

    assert not evaluator.captures_phrase(requirement, body, body_chunks(body))


def test_optimized_prompt_meets_capture_gate_for_typical_session() -> None:
    card = sample_card(
        objective="Add FastAPI endpoint for weekly engineering status summaries.",
        environment="Python with FastAPI and Pydantic",
        extra_constraints=["Keep the response within 300 words"],
    )
    body = build_harness_body(card)
    optimization = TokenOptimizationEngine().optimize(body, card)
    metrics = PreInferenceMetricsService(
        capture_evaluator=RequirementCaptureEvaluator(EmbeddingService(prefer_fallback=True)),
    ).compute(optimization.optimized_body, card, optimization=optimization)

    assert metrics.requirement_capture_score >= 0.90


def test_extract_section_keeps_markdown_table_in_task_identity() -> None:
    from prompt_piper_api.services.optimization.constraint_graph_pass import extract_section

    body = (
        "Task Identity\n"
        "-------------\n"
        "Role: long-horizon coding agent\n"
        "Objective: Build FlowBPM\n"
        "Additional constraint: Table:\n"
        "| Mode | Primary |\n"
        "| --- | --- |\n"
        "| Sleep | #090D18 |\n"
        "| Flow | #7865E8 |\n"
        "\n"
        "Definition of Done\n"
        "------------------\n"
        "COMPLETE only with passing tests\n"
    )
    lines = extract_section(body, "Task Identity")
    assert "Role: long-horizon coding agent" in lines
    assert "Objective: Build FlowBPM" in lines
    assert any("| Sleep | #090D18 |" in line for line in lines)
    assert "COMPLETE only with passing tests" not in lines


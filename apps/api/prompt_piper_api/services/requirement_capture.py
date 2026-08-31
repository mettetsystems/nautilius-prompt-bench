from __future__ import annotations

import re

from prompt_piper_api.domain.optimization import ConstraintGraph, ConstraintSlot
from prompt_piper_api.domain.requirement_card import LIST_LEAF_FIELDS, RequirementCard
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.similarity_utils import cosine_similarity, lexical_overlap_score, tokenize

_SECTION_TITLE = re.compile(
    r"^(Task Identity|Definition of Done|Change Scope|Architecture Policy|"
    r"Discovery Policy|Execution Strategy|Validation Strategy|Failure Recovery|"
    r"Autonomy Policy|Persistent Agent Memory|Completion Contract|"
    r"Resource and Budget Governance|Tool Safety and Shell Restrictions|"
    r"Context Compaction and State Persistence|Rollback and Backtracking|"
    r"Escalation and HITL Interruption|Dependency and Security Verification|"
    r"Long-Horizon Coding Agent Contract|"
    r"Technical Context|Core Task and Scope|Inputs, Outputs, and Contracts|"
    r"Architectural Rules and Constraints|Edge Cases and Error Strategy|"
    r"Response Formatting|Tools|Artifact rules|"
    r"Role and Objective|Tech Stack|Context and Input|Constraints|Expected Output)$",
    re.IGNORECASE,
)
_DIVIDER = re.compile(r"^-+$")
_VAGUE_FOR_CAPTURE = re.compile(
    r"\b(maybe|perhaps|somewhat|kind of|sort of|very|really|just)\b",
    re.I,
)

# Embedding similarity required to treat a paraphrase as captured.
EMBEDDING_CAPTURE_THRESHOLD = 0.78
# Token overlap fallback when embeddings are unavailable or inconclusive.
LEXICAL_CAPTURE_THRESHOLD = 0.55
# Shorter, more precise wording (e.g. "propeller" for "fan-like part of a plane").
PRECISE_REFINEMENT_THRESHOLD = 0.82
PRECISE_REFINEMENT_MAX_TOKEN_RATIO = 0.72

_BINDING_CAPTURE_SLOTS: tuple[ConstraintSlot, ...] = (
    ConstraintSlot.OBJECTIVE,
    ConstraintSlot.AUDIENCE,
    ConstraintSlot.SCOPE,
    ConstraintSlot.FORMAT,
    ConstraintSlot.MUST_CITE,
    ConstraintSlot.EXCLUSIONS,
    ConstraintSlot.TOKEN_BUDGET,
)

_STRING_LEAVES: tuple[str, ...] = (
    "task_identity.objective",
    "task_identity.task_type",
    "task_identity.environment",
    "agent_contract.definition_of_done",
    "agent_contract.change_scope",
    "agent_contract.architecture_policy",
    "agent_contract.discovery_policy",
    "agent_contract.execution_strategy",
    "agent_contract.validation_strategy",
    "agent_contract.failure_recovery",
    "agent_contract.autonomy_policy",
    "agent_contract.persistent_memory",
    "agent_contract.completion_contract",
    "agent_contract.resource_budget",
    "agent_contract.tool_safety",
    "agent_contract.context_compaction",
    "agent_contract.rollback_protocol",
    "agent_contract.escalation_rules",
    "agent_contract.dependency_security",
)


def normalize_phrase_for_capture(phrase: str) -> str:
    """Normalize text for capture checks so denoising tweaks do not fail the gate."""
    collapsed = _VAGUE_FOR_CAPTURE.sub("", phrase)
    normalized = re.sub(r"\s+", " ", collapsed).strip().lower()
    return normalized.rstrip(".,;:")


def dedupe_phrases(phrases: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for phrase in phrases:
        key = normalize_phrase_for_capture(phrase)
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(phrase.strip())
    return unique


def collect_requirement_phrases(card: RequirementCard) -> list[str]:
    """Return each populated requirement phrase that must be reflected in the prompt body."""
    phrases: list[str] = []

    for field_name in _STRING_LEAVES:
        value = card.get_leaf(field_name)
        if isinstance(value, str) and value.strip():
            phrases.append(value.strip())

    for field_name in LIST_LEAF_FIELDS:
        values: list[str] = card.get_leaf(field_name)
        phrases.extend(item.strip() for item in values if item.strip())

    for label, value in card.optimization_targets.model_dump().items():
        if value and str(value).strip():
            phrases.append(str(value).strip())

    return phrases


def collect_optimization_binding_phrases(
    graph: ConstraintGraph,
    card: RequirementCard,
) -> list[str]:
    """Phrases the optimizer must preserve and the approval gate scores for optimized prompts."""
    phrases: list[str] = []
    for slot in _BINDING_CAPTURE_SLOTS:
        phrases.extend(graph.slots.get(slot.value, []))
    for value in (
        card.task_identity.objective,
        card.task_identity.environment,
        card.agent_contract.definition_of_done,
        card.agent_contract.change_scope,
        card.agent_contract.validation_strategy,
        card.agent_contract.completion_contract,
        card.agent_contract.failure_recovery,
        card.agent_contract.resource_budget,
        card.agent_contract.persistent_memory,
        card.agent_contract.tool_safety,
    ):
        if value.strip():
            phrases.append(value.strip())
    for values in (
        card.task_identity.additional_constraints,
    ):
        phrases.extend(item.strip() for item in values if item.strip())
    return dedupe_phrases(phrases)


def body_chunks(body: str) -> list[str]:
    """Split the prompt into lines and short multi-line windows for semantic matching."""
    lines: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or _DIVIDER.match(line) or _SECTION_TITLE.match(line):
            continue
        lines.append(line)

    chunks = list(lines)
    for index in range(len(lines) - 1):
        pair = f"{lines[index]} {lines[index + 1]}".strip()
        if len(pair.split()) >= 4:
            chunks.append(pair)

    stripped = body.strip()
    if stripped and stripped not in chunks:
        chunks.append(stripped)
    return chunks


class RequirementCaptureEvaluator:
    """Score whether an optimized prompt captures requirement concepts, not just verbatim text."""

    def __init__(self, embedding: EmbeddingService | None = None) -> None:
        self._embedding = embedding or EmbeddingService(prefer_fallback=True)

    def score(
        self,
        body: str,
        card: RequirementCard,
        *,
        constraint_graph: ConstraintGraph | None = None,
    ) -> float:
        if constraint_graph is not None:
            phrases = collect_optimization_binding_phrases(constraint_graph, card)
        else:
            phrases = collect_requirement_phrases(card)
        if not phrases:
            return 1.0

        chunks = body_chunks(body)
        captured = sum(1 for phrase in phrases if self.captures_phrase(phrase, body, chunks))
        return round(captured / len(phrases), 2)

    def captures_phrase(self, requirement: str, body: str, chunks: list[str]) -> bool:
        phrase = requirement.strip()
        if not phrase:
            return True

        lowered_body = body.lower()
        if phrase.lower() in lowered_body:
            return True

        normalized_phrase = normalize_phrase_for_capture(phrase)
        normalized_body = normalize_phrase_for_capture(body)
        if normalized_phrase and normalized_phrase in normalized_body:
            return True

        if chunks:
            normalized_chunks = [normalize_phrase_for_capture(chunk) for chunk in chunks]
            best_lexical = max(lexical_overlap_score(phrase, chunk) for chunk in chunks)
            if best_lexical >= LEXICAL_CAPTURE_THRESHOLD:
                return True
            best_normalized = max(
                (
                    lexical_overlap_score(normalized_phrase, chunk)
                    for chunk in normalized_chunks
                    if normalized_phrase
                ),
                default=0.0,
            )
            if best_normalized >= LEXICAL_CAPTURE_THRESHOLD:
                return True

        if not chunks:
            return False

        phrase_embedding = self._embedding.embed_one(phrase)
        chunk_embeddings = self._embedding.embed(chunks)
        phrase_tokens = max(len(tokenize(phrase)), 1)

        for chunk, chunk_embedding in zip(chunks, chunk_embeddings, strict=True):
            similarity = cosine_similarity(phrase_embedding, chunk_embedding)
            chunk_tokens = max(len(tokenize(chunk)), 1)

            if similarity >= EMBEDDING_CAPTURE_THRESHOLD:
                return True

            if (
                similarity >= PRECISE_REFINEMENT_THRESHOLD
                and chunk_tokens <= phrase_tokens * PRECISE_REFINEMENT_MAX_TOKEN_RATIO
            ):
                # More precise wording that preserves the same concept (fewer tokens).
                return True

        return False

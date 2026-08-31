from __future__ import annotations

import json

from enum import StrEnum

from pydantic import BaseModel, Field

from prompt_piper_api.domain.precision import VagueLanguageFinding
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.base import ChatMessage, LLMClient
from prompt_piper_api.llm.fallback import with_llm_fallback
from prompt_piper_api.services.precision_lexicon_service import PrecisionLexiconService
from prompt_piper_api.services.precision_vector_service import PrecisionVectorService

_MAX_MERGED_CANDIDATES = 20
_MAX_SUGGESTIONS = 5


class PrecisionSuggestionSource(StrEnum):
    LLM = "llm"
    VECTOR = "vector"
    WORDNET = "wordnet"
    NONE = "none"


class PrecisionSuggestions(BaseModel):
    finding_id: str
    suggested_replacements: list[str] = Field(default_factory=list)
    model_available: bool = False
    source: PrecisionSuggestionSource = PrecisionSuggestionSource.NONE
    message: str | None = None


class PrecisionSuggestionService:
    """Vector + WordNet candidates with optional LLM reranking."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        lexicon: PrecisionLexiconService | None = None,
        vector: PrecisionVectorService | None = None,
    ) -> None:
        self._llm = llm
        self._lexicon = lexicon or PrecisionLexiconService()
        self._vector = vector or PrecisionVectorService()

    def lexicon_available(self) -> bool:
        return self._lexicon.available

    def wordnet_available(self) -> bool:
        return self._lexicon.wordnet_available

    def vector_index_available(self) -> bool:
        return self._vector.available

    def suggest(
        self,
        *,
        finding: VagueLanguageFinding,
        body: str,
        card: RequirementCard,
    ) -> PrecisionSuggestions:
        def unavailable(message: str) -> PrecisionSuggestions:
            return PrecisionSuggestions(
                finding_id=finding.id,
                suggested_replacements=[],
                model_available=False,
                source=PrecisionSuggestionSource.NONE,
                message=message,
            )

        def offline_suggestions() -> PrecisionSuggestions:
            merged = self._merged_candidates(finding=finding, body=body, card=card)
            if not merged:
                if self._lexicon.wordnet_available:
                    return unavailable(
                        "No lexicon matches for this term. Enter your own precise replacement."
                    )
                return unavailable(
                    "Install WordNet (make setup-lexicon) and/or build the vector index "
                    "(make build-lexicon-index)."
                )

            used_vector = self._vector.available
            if used_vector:
                message = "Semantic lexicon matches (vector index). Select one or enter your own."
                source = PrecisionSuggestionSource.VECTOR
            else:
                message = (
                    "WordNet suggestions (CPU-only). "
                    "Run make build-lexicon-index for semantic ranking."
                )
                source = PrecisionSuggestionSource.WORDNET
            return PrecisionSuggestions(
                finding_id=finding.id,
                suggested_replacements=merged[:_MAX_SUGGESTIONS],
                model_available=False,
                source=source,
                message=message,
            )

        def llm_suggestions(client: LLMClient) -> PrecisionSuggestions:
            merged = self._merged_candidates(finding=finding, body=body, card=card)
            if merged:
                return self._rerank_with_llm(
                    client,
                    finding=finding,
                    body=body,
                    card=card,
                    candidates=merged,
                )
            return self._suggest_with_llm(
                client,
                finding=finding,
                body=body,
                card=card,
            )

        return with_llm_fallback(self._llm, llm_suggestions, offline_suggestions)

    def _merged_candidates(
        self,
        *,
        finding: VagueLanguageFinding,
        body: str,
        card: RequirementCard,
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()

        for candidate in self._vector.suggest_candidates(
            finding=finding,
            body=body,
            card=card,
            max_candidates=_MAX_MERGED_CANDIDATES,
        ):
            lowered = candidate.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(candidate)

        for candidate in self._lexicon.suggest(
            finding=finding,
            body=body,
            card=card,
            max_suggestions=_MAX_MERGED_CANDIDATES,
        ):
            lowered = candidate.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            merged.append(candidate)
            if len(merged) >= _MAX_MERGED_CANDIDATES:
                break

        return merged[:_MAX_MERGED_CANDIDATES]

    def _rerank_with_llm(
        self,
        llm: LLMClient,
        *,
        finding: VagueLanguageFinding,
        body: str,
        card: RequirementCard,
        candidates: list[str],
    ) -> PrecisionSuggestions:
        response = llm.chat(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "You help sharpen prompt text. Return JSON with key "
                        '"suggested_replacements": an array of 3 to 5 items chosen '
                        "ONLY from the provided candidate list. Each item must fit "
                        "the same grammatical role as the vague term in the sentence. "
                        "Do not invent new words."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "vague_term": finding.term,
                            "category": finding.category.value,
                            "line": finding.line,
                            "objective": card.objective,
                            "audience": card.task_identity.environment,
                            "candidates": candidates,
                            "full_prompt_excerpt": body[:2000],
                        }
                    ),
                ),
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.content)
        raw = payload.get("suggested_replacements", [])
        if not isinstance(raw, list):
            raw = []
        allowed = {item.lower(): item for item in candidates}
        suggestions: list[str] = []
        for item in raw:
            normalized = str(item).strip()
            if not normalized:
                continue
            picked = allowed.get(normalized.lower())
            if picked is None:
                continue
            if picked not in suggestions:
                suggestions.append(picked)
            if len(suggestions) >= _MAX_SUGGESTIONS:
                break
        if not suggestions:
            suggestions = candidates[:_MAX_SUGGESTIONS]
        return PrecisionSuggestions(
            finding_id=finding.id,
            suggested_replacements=suggestions,
            model_available=True,
            source=PrecisionSuggestionSource.LLM,
            message="Model-ranked suggestions from the lexicon index.",
        )

    def _suggest_with_llm(
        self,
        llm: LLMClient,
        *,
        finding: VagueLanguageFinding,
        body: str,
        card: RequirementCard,
    ) -> PrecisionSuggestions:
        response = llm.chat(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "You help sharpen prompt text. Return JSON with key "
                        '"suggested_replacements": an array of 3 to 5 concise, '
                        "specific alternatives for the vague term. Each alternative "
                        "must fit the same grammatical role in the sentence. "
                        "Do not add markdown or explanation."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "vague_term": finding.term,
                            "category": finding.category.value,
                            "line": finding.line,
                            "objective": card.objective,
                            "audience": card.task_identity.environment,
                            "full_prompt_excerpt": body[:2000],
                        }
                    ),
                ),
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.content)
        raw = payload.get("suggested_replacements", [])
        if not isinstance(raw, list):
            raw = []
        suggestions = [str(item).strip() for item in raw if str(item).strip()][:5]
        return PrecisionSuggestions(
            finding_id=finding.id,
            suggested_replacements=suggestions,
            model_available=True,
            source=PrecisionSuggestionSource.LLM,
            message=None if suggestions else "Model returned no suggestions; enter your own.",
        )

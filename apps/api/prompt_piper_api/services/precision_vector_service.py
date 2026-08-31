from __future__ import annotations

from prompt_piper_api.domain.precision import VagueLanguageCategory, VagueLanguageFinding
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.lexicon_vector_index import LexiconVectorIndex, get_lexicon_vector_index
from prompt_piper_api.services.semantic_precision import CATCH_ALL_NOUNS, LAZY_ADJECTIVES
from prompt_piper_api.services.wordnet_lexicon import _is_usable_candidate

_POS_FILTER = {
    VagueLanguageCategory.LAZY_ADJECTIVE: frozenset({"a", "s"}),
    VagueLanguageCategory.CATCH_ALL_NOUN: frozenset({"n"}),
}


class PrecisionVectorService:
    """Semantic search over the precision lexicon vector index."""

    def __init__(
        self,
        *,
        index: LexiconVectorIndex | None = None,
        embedding: EmbeddingService | None = None,
    ) -> None:
        self._index = index or get_lexicon_vector_index()
        self._embedding = embedding

    @property
    def available(self) -> bool:
        return self._index.available and not self._embedding_service().using_fallback

    @property
    def index_entry_count(self) -> int:
        return self._index.entry_count

    def suggest_candidates(
        self,
        *,
        finding: VagueLanguageFinding,
        body: str,
        card: RequirementCard,
        max_candidates: int = 20,
    ) -> list[str]:
        if not self.available:
            return []

        query = self._build_query(
            finding=finding,
            body=body,
            objective=card.objective,
            audience=card.task_identity.environment,
        )
        vector = self._embedding_service().embed_one(query)
        hits = self._index.search(
            vector,
            limit=max_candidates * 2,
            pos_filter=_POS_FILTER.get(finding.category),
        )

        results: list[str] = []
        seen: set[str] = set()
        for _, entry in hits:
            candidate = entry.candidate.strip()
            lowered = candidate.lower()
            if lowered in seen:
                continue
            if not _is_usable_candidate(finding.term, candidate):
                continue
            if lowered in LAZY_ADJECTIVES or lowered in CATCH_ALL_NOUNS:
                continue
            seen.add(lowered)
            results.append(candidate)
            if len(results) >= max_candidates:
                break
        return results

    def _embedding_service(self) -> EmbeddingService:
        if self._embedding is None:
            from prompt_piper_api.config import get_settings

            settings = get_settings()
            self._embedding = EmbeddingService(
                model_name=settings.prompt_piper_embedding_model,
                prefer_fallback=settings.prompt_piper_embedding_fallback,
            )
        return self._embedding

    @staticmethod
    def _build_query(
        *,
        finding: VagueLanguageFinding,
        body: str,
        objective: str,
        audience: str,
    ) -> str:
        category = (
            "adjective"
            if finding.category is VagueLanguageCategory.LAZY_ADJECTIVE
            else "noun"
        )
        return (
            f"Replace vague {category} '{finding.term}' in prompt line: {finding.line}. "
            f"Objective: {objective}. Audience: {audience}. "
            f"Context excerpt: {body[:1200]}"
        )

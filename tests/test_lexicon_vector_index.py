from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_piper_api.domain.lexicon_index import LexiconEntrySource, LexiconVectorIndexManifest, LexiconVectorRecord
from prompt_piper_api.domain.precision import VagueLanguageCategory, VagueLanguageFinding
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.lexicon_vector_index import LexiconVectorIndex
from prompt_piper_api.services.precision_suggestion_service import (
    PrecisionSuggestionService,
    PrecisionSuggestionSource,
)
from prompt_piper_api.services.precision_vector_service import PrecisionVectorService
from prompt_piper_api.services.similarity_utils import hash_embed
from prompt_piper_api.services.wordnet_lexicon import WordNetLexicon


class _FixedEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self._vector = vector

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._vector is not None:
            return [self._vector for _ in texts]
        return [hash_embed(text, dimensions=384) for text in texts]


@pytest.fixture
def vector_index_path(tmp_path: Path) -> Path:
    deliverable = LexiconVectorRecord(
        id="glossary-1",
        candidate="deliverable",
        pos="n",
        source=LexiconEntrySource.GLOSSARY,
        text="Prompt precision replacement: deliverable. Use instead of vague words such as thing.",
        embedding=hash_embed("deliverable output artifact", dimensions=384),
    )
    specific = LexiconVectorRecord(
        id="glossary-2",
        candidate="specific",
        pos="a",
        source=LexiconEntrySource.GLOSSARY,
        text="Prompt precision replacement: specific. Use instead of vague words such as good.",
        embedding=hash_embed("specific measurable concrete", dimensions=384),
    )
    manifest = LexiconVectorIndexManifest(
        embedding_model="hash-test",
        entry_count=2,
        built_at="2026-01-01T00:00:00+00:00",
        entries=[deliverable, specific],
    )
    path = tmp_path / "precision_vectors.json"
    path.write_text(json.dumps(manifest.model_dump()), encoding="utf-8")
    return path


def test_lexicon_vector_index_search(vector_index_path: Path) -> None:
    index = LexiconVectorIndex(vector_index_path)
    assert index.available
    query = hash_embed("replace vague thing with deliverable output", dimensions=384)
    hits = index.search(query, limit=5, pos_filter=frozenset({"n"}))
    assert hits
    assert hits[0][1].candidate == "deliverable"


def test_precision_vector_service_returns_candidates(vector_index_path: Path) -> None:
    index = LexiconVectorIndex(vector_index_path)
    deliverable = next(entry for entry in index._entries if entry.candidate == "deliverable")  # noqa: SLF001
    embedding = EmbeddingService(embedder=_FixedEmbedder(deliverable.embedding))
    service = PrecisionVectorService(
        index=LexiconVectorIndex(vector_index_path),
        embedding=embedding,
    )
    finding = VagueLanguageFinding(
        id="f1",
        term="thing",
        category=VagueLanguageCategory.CATCH_ALL_NOUN,
        line_number=1,
        line="Summarize the thing for leadership.",
        start=15,
        end=20,
    )
    card = RequirementCard(task_identity={"objective": "Weekly engineering status summary"})
    candidates = service.suggest_candidates(
        finding=finding,
        body=finding.line,
        card=card,
        max_candidates=5,
    )
    assert "deliverable" in candidates


def test_precision_service_prefers_vector_candidates(
    vector_index_path: Path,
    tmp_path: Path,
) -> None:
    glossary = tmp_path / "prompt_terms.yaml"
    glossary.write_text(
        """
terms:
  thing:
    replaces: [thing]
    suggestions: [deliverable, artifact]
""".strip(),
        encoding="utf-8",
    )
    lexicon = WordNetLexicon(glossary_path=glossary)
    index = LexiconVectorIndex(vector_index_path)
    deliverable = next(entry for entry in index._entries if entry.candidate == "deliverable")  # noqa: SLF001
    from prompt_piper_api.services.precision_lexicon_service import PrecisionLexiconService

    service = PrecisionSuggestionService(
        llm=None,
        lexicon=PrecisionLexiconService(lexicon=lexicon),
        vector=PrecisionVectorService(
            index=index,
            embedding=EmbeddingService(embedder=_FixedEmbedder(deliverable.embedding)),
        ),
    )
    finding = VagueLanguageFinding(
        id="f1",
        term="thing",
        category=VagueLanguageCategory.CATCH_ALL_NOUN,
        line_number=1,
        line="Summarize the thing for leadership.",
        start=15,
        end=20,
    )
    result = service.suggest(
        finding=finding,
        body=finding.line,
        card=RequirementCard(task_identity={"objective": "Weekly engineering status summary"}),
    )
    assert result.source is PrecisionSuggestionSource.VECTOR
    assert "deliverable" in result.suggested_replacements

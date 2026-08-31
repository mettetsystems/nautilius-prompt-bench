from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from prompt_piper_api.config import _repo_root
from prompt_piper_api.domain.precision import VagueLanguageCategory
from prompt_piper_api.services.semantic_precision import CATCH_ALL_NOUNS, LAZY_ADJECTIVES

_TOKEN_RE = re.compile(r"[a-z]{3,}")
_VAGUE_TERMS = LAZY_ADJECTIVES | CATCH_ALL_NOUNS
_MAX_SUGGESTIONS = 5
_MAX_HYPONYM_DEPTH = 1
_MAX_SYNSETS = 8
_MAX_CANDIDATES = 40


def _tokenize(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _lemma_label(lemma_name: str) -> str:
    return lemma_name.replace("_", " ").strip()


def _is_usable_candidate(term: str, candidate: str) -> bool:
    lowered = candidate.lower().strip()
    if not lowered or lowered == term.lower():
        return False
    if lowered in _VAGUE_TERMS:
        return False
    if len(lowered) > 48:
        return False
    if len(lowered.split()) > 4:
        return False
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9 \-']*", lowered))


@dataclass(frozen=True)
class GlossaryEntry:
    replaces: frozenset[str]
    suggestions: tuple[str, ...]


@dataclass
class WordNetLexicon:
    """Offline WordNet + glossary lookups for precision refinement."""

    glossary_path: Path = field(default_factory=lambda: _repo_root() / "data" / "lexicon" / "prompt_terms.yaml")
    _glossary: dict[str, GlossaryEntry] = field(default_factory=dict, init=False)
    _wordnet: Any | None = field(default=None, init=False)
    _wordnet_checked: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._glossary = self._load_glossary(self.glossary_path)

    @property
    def glossary_available(self) -> bool:
        return bool(self._glossary)

    @property
    def wordnet_available(self) -> bool:
        return self._ensure_wordnet() is not None

    @property
    def available(self) -> bool:
        return self.glossary_available or self.wordnet_available

    def suggest(
        self,
        *,
        term: str,
        category: VagueLanguageCategory,
        line: str,
        objective: str = "",
        audience: str = "",
        max_suggestions: int = _MAX_SUGGESTIONS,
    ) -> list[str]:
        context = _tokenize(" ".join((line, objective, audience)))
        ranked: list[tuple[int, str]] = []
        seen: set[str] = set()

        for suggestion in self._glossary_suggestions(term):
            lowered = suggestion.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ranked.append((100 + self._context_score(suggestion, context), suggestion))

        for score, suggestion in self._wordnet_suggestions(
            term=term,
            category=category,
            context=context,
        ):
            lowered = suggestion.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ranked.append((score, suggestion))

        ranked.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
        results: list[str] = []
        for _, candidate in ranked:
            if not _is_usable_candidate(term, candidate):
                continue
            results.append(candidate)
            if len(results) >= max_suggestions:
                break
        return results

    def _glossary_suggestions(self, term: str) -> list[str]:
        lowered = term.lower()
        for entry in self._glossary.values():
            if lowered in entry.replaces:
                return list(entry.suggestions)
        if lowered in self._glossary:
            return list(self._glossary[lowered].suggestions)
        return []

    def _wordnet_suggestions(
        self,
        *,
        term: str,
        category: VagueLanguageCategory,
        context: set[str],
    ) -> list[tuple[int, str]]:
        wordnet = self._ensure_wordnet()
        if wordnet is None:
            return []

        pos = wordnet.ADJ if category is VagueLanguageCategory.LAZY_ADJECTIVE else wordnet.NOUN
        synsets = wordnet.synsets(term.lower(), pos=pos)[:_MAX_SYNSETS]
        if not synsets:
            synsets = wordnet.synsets(term.lower())[:_MAX_SYNSETS]
        if not synsets:
            return []

        synsets.sort(key=lambda synset: self._synset_context_score(synset, context), reverse=True)
        best = synsets[0]
        candidates: list[tuple[int, str]] = []

        if category is VagueLanguageCategory.LAZY_ADJECTIVE:
            for lemma in best.lemmas():
                label = _lemma_label(lemma.name())
                score = 40 + self._context_score(label, context)
                candidates.append((score, label))
        else:
            hyponyms = list(best.hyponyms())
            for hyponym in hyponyms[:15]:
                for lemma in hyponym.lemmas()[:2]:
                    label = _lemma_label(lemma.name())
                    score = 50 + self._context_score(label, context)
                    candidates.append((score, label))
            if _MAX_HYPONYM_DEPTH > 0:
                for hyponym in hyponyms[:8]:
                    for child in hyponym.hyponyms()[:5]:
                        for lemma in child.lemmas()[:1]:
                            label = _lemma_label(lemma.name())
                            score = 35 + self._context_score(label, context)
                            candidates.append((score, label))

        candidates.sort(key=lambda item: (-item[0], len(item[1]), item[1]))
        return candidates[:_MAX_CANDIDATES]

    def _synset_context_score(self, synset: Any, context: set[str]) -> int:
        gloss = _tokenize(synset.definition())
        hypernym_bonus = 0
        for path in synset.hypernym_paths():
            if not path:
                continue
            for node in path[-2:]:
                gloss |= _tokenize(node.definition())
        return len(context & gloss)

    def _context_score(self, candidate: str, context: set[str]) -> int:
        return len(context & _tokenize(candidate))

    def _ensure_wordnet(self) -> Any | None:
        if self._wordnet_checked:
            return self._wordnet
        self._wordnet_checked = True
        # NLTK 3.10+ treats site-packages under CWD (repo-local venv) as hijacks.
        os.environ.setdefault("NLTK_DISABLE_IMPORT_SECURITY", "1")
        try:
            import nltk  # noqa: PLC0415
            from nltk.corpus import wordnet as wordnet_corpus  # noqa: PLC0415
        except ImportError:
            return None

        repo_nltk = _repo_root() / "data" / "nltk_data"
        if repo_nltk.is_dir() and str(repo_nltk) not in nltk.data.path:
            nltk.data.path.insert(0, str(repo_nltk))

        try:
            wordnet_corpus.synsets("test")
        except LookupError:
            return None
        self._wordnet = wordnet_corpus
        return self._wordnet

    @staticmethod
    def _load_glossary(path: Path) -> dict[str, GlossaryEntry]:
        if not path.is_file():
            return {}
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return {}
        raw_terms = payload.get("terms", {})
        if not isinstance(raw_terms, dict):
            return {}

        glossary: dict[str, GlossaryEntry] = {}
        for key, value in raw_terms.items():
            if not isinstance(value, dict):
                continue
            replaces_raw = value.get("replaces", [key])
            suggestions_raw = value.get("suggestions", [])
            if not isinstance(replaces_raw, list) or not isinstance(suggestions_raw, list):
                continue
            replaces = frozenset(str(item).lower() for item in replaces_raw)
            suggestions = tuple(str(item).strip() for item in suggestions_raw if str(item).strip())
            if not suggestions:
                continue
            entry = GlossaryEntry(replaces=replaces, suggestions=suggestions)
            glossary[str(key).lower()] = entry
            for alias in replaces:
                glossary[alias] = entry
        return glossary


@lru_cache(maxsize=1)
def get_wordnet_lexicon() -> WordNetLexicon:
    return WordNetLexicon()

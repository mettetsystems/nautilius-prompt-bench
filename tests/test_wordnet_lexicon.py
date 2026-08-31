from __future__ import annotations

from pathlib import Path

import pytest

from prompt_piper_api.domain.precision import VagueLanguageCategory, VagueLanguageFinding
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.precision_lexicon_service import PrecisionLexiconService
from prompt_piper_api.services.precision_suggestion_service import (
    PrecisionSuggestionService,
    PrecisionSuggestionSource,
)
from prompt_piper_api.services.wordnet_lexicon import WordNetLexicon


@pytest.fixture
def glossary_lexicon(tmp_path: Path) -> WordNetLexicon:
    glossary = tmp_path / "prompt_terms.yaml"
    glossary.write_text(
        """
terms:
  thing:
    replaces: [thing, stuff]
    suggestions: [deliverable, artifact, output]
  good:
    replaces: [good, nice]
    suggestions: [specific, measurable, concrete]
""".strip(),
        encoding="utf-8",
    )
    return WordNetLexicon(glossary_path=glossary)


def test_glossary_suggestions_for_catch_all_noun(glossary_lexicon: WordNetLexicon) -> None:
    suggestions = glossary_lexicon.suggest(
        term="thing",
        category=VagueLanguageCategory.CATCH_ALL_NOUN,
        line="Summarize the thing for leadership.",
        objective="Weekly engineering status summary",
    )
    assert "deliverable" in suggestions
    assert "thing" not in suggestions


def test_glossary_suggestions_for_lazy_adjective(glossary_lexicon: WordNetLexicon) -> None:
    suggestions = glossary_lexicon.suggest(
        term="good",
        category=VagueLanguageCategory.LAZY_ADJECTIVE,
        line="Write a good summary.",
        objective="Weekly engineering status summary",
    )
    assert "specific" in suggestions
    assert "nice" not in suggestions


def test_wordnet_hyponyms_when_installed() -> None:
    lexicon = WordNetLexicon()
    if not lexicon.wordnet_available:
        pytest.skip("WordNet corpus not installed (run: make setup-lexicon)")

    suggestions = lexicon.suggest(
        term="issue",
        category=VagueLanguageCategory.CATCH_ALL_NOUN,
        line="Describe the deployment issue for managers.",
        objective="Weekly engineering status summary",
    )
    assert suggestions
    assert "issue" not in {item.lower() for item in suggestions}


def test_precision_suggestion_service_uses_wordnet_fallback(
    glossary_lexicon: WordNetLexicon,
) -> None:
    service = PrecisionSuggestionService(
        llm=None,
        lexicon=PrecisionLexiconService(lexicon=glossary_lexicon),
    )
    finding = VagueLanguageFinding(
        id="abc",
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
    assert result.source is PrecisionSuggestionSource.WORDNET
    assert "deliverable" in result.suggested_replacements

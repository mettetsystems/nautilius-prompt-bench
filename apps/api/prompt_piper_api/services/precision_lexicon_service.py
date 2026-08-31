from __future__ import annotations

from prompt_piper_api.domain.precision import VagueLanguageFinding
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.wordnet_lexicon import WordNetLexicon, get_wordnet_lexicon


class PrecisionLexiconService:
    """CPU-only precision suggestions from glossary + WordNet."""

    def __init__(self, lexicon: WordNetLexicon | None = None) -> None:
        self._lexicon = lexicon or get_wordnet_lexicon()

    @property
    def available(self) -> bool:
        return self._lexicon.available

    @property
    def wordnet_available(self) -> bool:
        return self._lexicon.wordnet_available

    def suggest(
        self,
        *,
        finding: VagueLanguageFinding,
        body: str,
        card: RequirementCard,
        max_suggestions: int = 5,
    ) -> list[str]:
        return self._lexicon.suggest(
            term=finding.term,
            category=finding.category,
            line=finding.line,
            objective=card.objective,
            audience=card.task_identity.environment,
            max_suggestions=max_suggestions,
        )

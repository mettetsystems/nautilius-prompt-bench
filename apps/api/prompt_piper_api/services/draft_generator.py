import json
import re

from prompt_piper_api.domain.requirement_card import (
    DIMENSION_SECTION_TITLES,
    RequirementCard,
)
from prompt_piper_api.llm.base import ChatMessage, LLMClient
from prompt_piper_api.llm.fallback import with_llm_fallback
from prompt_piper_api.services.clarification_question_ranker import (
    CLARIFICATION_FIELD_PRIORITY,
    ClarificationQuestionRanker,
    prune_deferred_unresolved,
)
from prompt_piper_api.services.draft_result import DraftGenerationResult
from prompt_piper_api.services.harness_prompt_builder import build_harness_body

UNSPECIFIED = "unspecified"

SECTION_RULES = (
    "Use plain text only. Do not invent unspecified fields; write 'unspecified' instead. "
    "Separate Task Identity and the sixteen operational-control sections of the long-horizon "
    "coding-agent contract. Use clear, direct, auditable language. Prefer explicit rules "
    "over brevity. Do not use XML or markdown headings. "
    "Clarity of the contract matters more than token count."
)


class DraftGenerator:
    """Builds an auditable plain-text long-horizon agent contract from a RequirementCard."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm
        self._ranker = ClarificationQuestionRanker(llm=llm)

    def generate(self, card: RequirementCard) -> DraftGenerationResult:
        return with_llm_fallback(
            self._llm,
            lambda client: self._generate_with_llm(client, card),
            lambda: self._generate_rule_based(card),
        )

    def generate_body(self, card: RequirementCard) -> str:
        """Return only the draft body for callers that do not need metadata."""
        return self.generate(card).body

    def _generate_with_llm(self, llm: LLMClient, card: RequirementCard) -> DraftGenerationResult:
        unresolved = self._unspecified_fields(card)
        response = llm.chat(
            [
                ChatMessage(role="system", content=SECTION_RULES),
                ChatMessage(
                    role="user",
                    content=json.dumps(
                        {
                            "requirement_card": card.model_dump(),
                            "unresolved_fields": unresolved,
                            "section_titles": list(DIMENSION_SECTION_TITLES),
                        }
                    ),
                ),
            ],
        )
        body = response.content.strip()
        if not body or self._looks_like_hallucinated(body, card, unresolved):
            return self._generate_rule_based(card)
        return DraftGenerationResult.from_parts(body=body, unresolved_fields=unresolved)

    def _generate_rule_based(self, card: RequirementCard) -> DraftGenerationResult:
        unresolved = self._unspecified_fields(card)
        body = build_harness_body(card)
        return DraftGenerationResult.from_parts(body=body, unresolved_fields=unresolved)

    def _unspecified_fields(self, card: RequirementCard) -> list[str]:
        unspecified = [
            field for field in CLARIFICATION_FIELD_PRIORITY if card.is_leaf_missing(field)
        ]
        card.mark_unresolved(*unspecified)
        prune_deferred_unresolved(card)
        return list(card.unresolved_fields)

    def _looks_like_hallucinated(
        self,
        body: str,
        card: RequirementCard,
        unresolved: list[str],
    ) -> bool:
        if "<" in body and ">" in body:
            return True
        env_path = "task_identity.environment"
        if env_path in unresolved and not card.task_identity.environment.strip():
            env_pattern = re.compile(
                r"Environment:\s*(?!unspecified\b)([\w\s.+\d/-]+)",
                re.I,
            )
            match = env_pattern.search(body)
            if match and match.group(1).strip().lower() != UNSPECIFIED:
                return True
        return False

from prompt_piper_api.domain.requirement_card import (
    RequirementCard,
)
from prompt_piper_api.llm.base import LLMClient
from prompt_piper_api.services.draft_result import DraftGenerationResult
from prompt_piper_api.services.harness_prompt_builder import build_harness_body

UNSPECIFIED = "unspecified"


class DraftGenerator:
    """Builds an auditable plain-text long-horizon agent contract from a RequirementCard."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        del llm  # Retained for call-site compatibility; contract compilation is deterministic.

    def generate(self, card: RequirementCard) -> DraftGenerationResult:
        return self._generate_rule_based(card)

    def generate_body(self, card: RequirementCard) -> str:
        """Return only the draft body for callers that do not need metadata."""
        return self.generate(card).body

    def _generate_rule_based(self, card: RequirementCard) -> DraftGenerationResult:
        unresolved = self._unspecified_fields(card)
        body = build_harness_body(card)
        return DraftGenerationResult.from_parts(body=body, unresolved_fields=unresolved)

    def _unspecified_fields(self, card: RequirementCard) -> list[str]:
        from prompt_piper_api.services.contract_resolver import resolve_contract

        return resolve_contract(card).unresolved_fields

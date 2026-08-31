from __future__ import annotations

from prompt_piper_api.domain.optimization import ConstraintGraph
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.harness_prompt_builder import build_harness_body


class RewriteCompressionPass:
    """Pass 2: rebuild as an explicit long-horizon task contract (clarity over compression)."""

    def run(
        self,
        body: str,
        card: RequirementCard,
        graph: ConstraintGraph,
    ) -> tuple[str, list[str]]:
        del body, graph
        notes: list[str] = [
            "Rebuilt prompt as a long-horizon task contract. Clarity of operational "
            "rules takes priority over token reduction."
        ]
        contract = build_harness_body(card)
        preamble = (
            "Long-Horizon Coding Agent Contract\n"
            "----------------------------------\n"
            "Follow every section. Prefer explicit operational rules over brevity. "
            "Long-horizon prompts may be resource-intensive; do not drop required "
            "policies to save tokens."
        )
        if "Long-Horizon Coding Agent Contract" not in contract:
            contract = f"{preamble}\n\n{contract}"
            notes.append("Added a clarity-first operating preamble.")
        return contract, notes


class ClarityExpansionPass(RewriteCompressionPass):
    """Alias used by the clarity-first optimizer."""

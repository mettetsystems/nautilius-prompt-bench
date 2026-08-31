"""Optional DSPy-style extraction program.

When the ``dspy`` package is installed, this module can wrap RequirementCard
extraction as an optimizable Signature. Without DSPy, callers use the standard
RequirementCardExtractor behind with_llm_fallback — no hard dependency.
"""

from __future__ import annotations

from typing import Any

from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.base import LLMClient
from prompt_piper_api.services.requirement_card_extractor import RequirementCardExtractor


def dspy_available() -> bool:
    try:
        import dspy  # noqa: F401
    except ImportError:
        return False
    return True


class OptionalDspyRequirementExtractor:
    """Thin adapter: prefer a compiled DSPy program if present, else extractor."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        compiled_program: Any | None = None,
    ) -> None:
        self._fallback = RequirementCardExtractor(llm)
        self._compiled = compiled_program

    def extract(self, initial_request: str) -> RequirementCard:
        if self._compiled is not None and dspy_available():
            prediction = self._compiled(initial_request=initial_request)
            payload = getattr(prediction, "requirement_card", None)
            if isinstance(payload, dict):
                return RequirementCard.model_validate(payload)
            if isinstance(payload, RequirementCard):
                return payload
        return self._fallback.extract(initial_request)


def build_dspy_extraction_module() -> Any | None:
    """Return a DSPy Module for extraction when dspy is installed; else None."""
    if not dspy_available():
        return None
    import dspy

    class ExtractRequirementCard(dspy.Signature):
        """Extract a coding RequirementCard JSON from a free-text request.

        Never invent unspecified leaves; leave them empty for honesty.
        """

        initial_request: str = dspy.InputField()
        requirement_card: dict = dspy.OutputField(
            desc="Nested RequirementCard fields as JSON-compatible dict"
        )

    class ExtractionProgram(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.predict = dspy.Predict(ExtractRequirementCard)

        def forward(self, initial_request: str):
            return self.predict(initial_request=initial_request)

    return ExtractionProgram()

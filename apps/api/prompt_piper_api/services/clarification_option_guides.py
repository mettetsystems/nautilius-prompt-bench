"""Beginner-friendly guides for clarification quick-reply options."""

from __future__ import annotations

from pydantic import BaseModel, Field

from prompt_piper_api.domain.agent_contract import (
    CONTRACT_FIELD_NAMES,
    beginner_option_text,
    quick_reply_labels,
)


class QuickReplyGuide(BaseModel):
    """Plain-language guide for one default quick-reply option."""

    option: str
    explanation: str = Field(description="What this option means in everyday language.")
    when_to_use: str = Field(description="When this option is usually the best fit.")


def build_quick_reply_guides(field_name: str) -> list[QuickReplyGuide]:
    """Build beginner guides aligned to the field's quick-reply options."""
    options = quick_reply_labels(field_name)
    text_by_option = beginner_option_text(field_name)
    guides: list[QuickReplyGuide] = []
    for option in options:
        pair = text_by_option.get(option)
        if pair is None:
            guides.append(
                QuickReplyGuide(
                    option=option,
                    explanation=f"Choose “{option}” when it matches your situation.",
                    when_to_use="Use when this label is the closest fit, or skip with unspecified.",
                )
            )
            continue
        explanation, when_to_use = pair
        guides.append(
            QuickReplyGuide(
                option=option,
                explanation=explanation,
                when_to_use=when_to_use,
            )
        )
    return guides


def assert_guides_cover_all_options() -> None:
    """Dev helper: every quick-reply option should have beginner text."""
    missing: list[str] = []
    for field_name in CONTRACT_FIELD_NAMES:
        text = beginner_option_text(field_name)
        for option in quick_reply_labels(field_name):
            if option not in text:
                missing.append(f"{field_name}:{option}")
    if missing:
        raise AssertionError(f"Missing beginner option guides: {missing}")

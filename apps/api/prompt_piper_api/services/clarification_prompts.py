"""Clarification question wording at beginner, standard, and advanced levels."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from prompt_piper_api.domain.agent_contract import CONTRACT_QUESTIONS


class ClarificationLevel(StrEnum):
    BEGINNER = "beginner"
    STANDARD = "standard"
    ADVANCED = "advanced"


LEVEL_LABELS: dict[ClarificationLevel, str] = {
    ClarificationLevel.BEGINNER: "Beginner",
    ClarificationLevel.STANDARD: "Standard",
    ClarificationLevel.ADVANCED: "Advanced",
}


class ClarificationVersionText(BaseModel):
    """One wording of a clarification question."""

    level: ClarificationLevel
    label: str
    prompt: str = Field(description="The question to ask the user.")
    rationale: str | None = Field(
        default=None,
        description="Why this question matters (emphasized for beginner).",
    )


STANDARD_PROMPTS: dict[str, str] = {
    question.field_name: question.standard_prompt for question in CONTRACT_QUESTIONS
}

BEGINNER_PROMPTS: dict[str, tuple[str, str]] = {
    question.field_name: (question.beginner_prompt, question.beginner_rationale)
    for question in CONTRACT_QUESTIONS
}

ADVANCED_PROMPTS: dict[str, str] = {
    question.field_name: question.advanced_prompt for question in CONTRACT_QUESTIONS
}

FOCUSED_PROMPTS = STANDARD_PROMPTS


def build_version_texts(field_name: str) -> list[ClarificationVersionText]:
    """Return beginner, standard, and advanced wording for a field."""
    standard = STANDARD_PROMPTS[field_name]
    beginner_prompt, beginner_rationale = BEGINNER_PROMPTS[field_name]
    advanced = ADVANCED_PROMPTS[field_name]
    return [
        ClarificationVersionText(
            level=ClarificationLevel.BEGINNER,
            label=LEVEL_LABELS[ClarificationLevel.BEGINNER],
            prompt=beginner_prompt,
            rationale=beginner_rationale,
        ),
        ClarificationVersionText(
            level=ClarificationLevel.STANDARD,
            label=LEVEL_LABELS[ClarificationLevel.STANDARD],
            prompt=standard,
            rationale=None,
        ),
        ClarificationVersionText(
            level=ClarificationLevel.ADVANCED,
            label=LEVEL_LABELS[ClarificationLevel.ADVANCED],
            prompt=advanced,
            rationale=None,
        ),
    ]

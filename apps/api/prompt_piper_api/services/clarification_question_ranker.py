import textwrap

from pydantic import BaseModel, Field, field_validator

from prompt_piper_api.domain.agent_contract import (
    CONTRACT_FIELD_NAMES,
    quick_reply_labels,
)
from prompt_piper_api.domain.limits import MAX_CLARIFICATION_QUESTIONS
from prompt_piper_api.domain.requirement_card import LEAF_FIELD_NAMES, RequirementCard
from prompt_piper_api.llm.base import LLMClient
from prompt_piper_api.services.clarification_option_guides import (
    QuickReplyGuide,
    build_quick_reply_guides,
)
from prompt_piper_api.services.clarification_prompts import (
    FOCUSED_PROMPTS,
    ClarificationVersionText,
    build_version_texts,
)

REQUIRED_CLARIFICATION_COUNT = MAX_CLARIFICATION_QUESTIONS

# Sixteen operational-control questions in the long-horizon contract order.
CLARIFICATION_FIELD_PRIORITY: tuple[str, ...] = CONTRACT_FIELD_NAMES

# Task identity is extracted from the initial request. Optimization targets are
# fixed to clarity-first and are not queued as questions.
DEFERRED_CLARIFICATION_FIELDS: frozenset[str] = frozenset(
    {
        "task_identity.objective",
        "task_identity.task_type",
        "task_identity.environment",
        "task_identity.additional_constraints",
        "optimization_targets",
    }
)

REFINEMENT_FIELD_PRIORITY: tuple[str, ...] = (
    "agent_contract.definition_of_done",
    "agent_contract.validation_strategy",
    "agent_contract.completion_contract",
    "agent_contract.failure_recovery",
    "agent_contract.resource_budget",
    "agent_contract.persistent_memory",
)

QUICK_REPLY_OPTIONS: dict[str, tuple[str, ...]] = {
    field_name: quick_reply_labels(field_name) for field_name in CONTRACT_FIELD_NAMES
}

UNSPECIFIED_ANSWERS = frozenset({"unspecified", "skip", "unknown", "not sure", "n/a"})


def clarification_field_priority(card: RequirementCard) -> tuple[str, ...]:
    """Field order for clarification (16-question agent contract)."""
    del card  # Priority is fixed for the coding workbench.
    return CLARIFICATION_FIELD_PRIORITY


def prune_deferred_unresolved(card: RequirementCard) -> None:
    """Drop empty presentation leaves from unresolved so they stay out of banners."""
    if not card.unresolved_fields:
        return
    card.unresolved_fields = [
        field_name
        for field_name in card.unresolved_fields
        if field_name not in DEFERRED_CLARIFICATION_FIELDS
    ]


class ClarificationQuestion(BaseModel):
    field_name: str
    question_number: int = Field(ge=1, description="Current quick question index.")
    total_questions: int = Field(default=MAX_CLARIFICATION_QUESTIONS, ge=1)
    prompt: str = Field(description="Standard focused question without numbering prefix.")
    versions: list[ClarificationVersionText] = Field(
        default_factory=list,
        description="Beginner, standard, and advanced wording for this field.",
    )
    quick_reply_options: list[str] = Field(
        min_length=4,
        description="Quick-reply choices including a final unspecified option.",
    )
    quick_reply_guides: list[QuickReplyGuide] = Field(
        default_factory=list,
        description="Beginner explanations for each default quick-reply option.",
    )
    question: str = Field(description="Full formatted standard question (legacy display).")
    rank: int = Field(ge=1, description="Expected clarification value rank for this field.")
    allows_free_text: bool = Field(
        default=True,
        description="User may answer in their own words instead of choosing a quick reply.",
    )

    @field_validator("quick_reply_options")
    @classmethod
    def validate_quick_replies(cls, options: list[str]) -> list[str]:
        if len(options) < 4 or len(options) > 6:
            msg = "Quick reply options must include 3 to 5 choices plus unspecified."
            raise ValueError(msg)
        if options[-1].strip().lower() != "unspecified":
            msg = "Quick reply options must end with unspecified."
            raise ValueError(msg)
        return options


class ClarificationQuestionRanker:
    """Ranks missing coding-dimension leaves and builds one quick question at a time."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def missing_fields(self, card: RequirementCard) -> list[str]:
        priority = clarification_field_priority(card)
        missing = [field for field in priority if card.is_leaf_missing(field)]
        card.mark_unresolved(*missing)
        prune_deferred_unresolved(card)
        return list(card.unresolved_fields)

    def rank(self, card: RequirementCard) -> list[ClarificationQuestion]:
        ordered_fields = self.missing_fields(card)
        return [
            self.build_question(
                field_name,
                question_number=index,
                total_questions=MAX_CLARIFICATION_QUESTIONS,
                card=card,
            )
            for index, field_name in enumerate(ordered_fields, start=1)
        ]

    def top_question(
        self,
        card: RequirementCard,
        *,
        question_number: int,
        total_questions: int = MAX_CLARIFICATION_QUESTIONS,
        exclude: frozenset[str] = frozenset(),
        last_answer: str | None = None,
    ) -> ClarificationQuestion | None:
        ranked = [question for question in self.rank(card) if question.field_name not in exclude]
        if ranked:
            field_name = ranked[0].field_name
            return self.build_question(
                field_name,
                question_number=question_number,
                total_questions=total_questions,
                rank=ranked[0].rank,
                card=card,
                last_answer=last_answer,
            )

        for index, field_name in enumerate(REFINEMENT_FIELD_PRIORITY, start=1):
            if field_name in exclude:
                continue
            return self.build_question(
                field_name,
                question_number=question_number,
                total_questions=total_questions,
                rank=index,
                card=card,
                last_answer=last_answer,
            )
        return None

    def build_question(
        self,
        field_name: str,
        *,
        question_number: int,
        total_questions: int = MAX_CLARIFICATION_QUESTIONS,
        rank: int | None = None,
        card: RequirementCard | None = None,
        last_answer: str | None = None,
    ) -> ClarificationQuestion:
        del card, last_answer
        prompt = FOCUSED_PROMPTS[field_name]
        versions = build_version_texts(field_name)
        quick_reply_options = list(QUICK_REPLY_OPTIONS[field_name])
        quick_reply_guides = build_quick_reply_guides(field_name)
        question = format_clarification_question(
            question_number=question_number,
            total_questions=total_questions,
            prompt=prompt,
            quick_reply_options=quick_reply_options,
        )
        return ClarificationQuestion(
            field_name=field_name,
            question_number=question_number,
            total_questions=total_questions,
            prompt=prompt,
            versions=versions,
            quick_reply_options=quick_reply_options,
            quick_reply_guides=quick_reply_guides,
            question=question,
            rank=rank or question_number,
        )

    def _is_missing(self, card: RequirementCard, field_name: str) -> bool:
        if field_name not in LEAF_FIELD_NAMES:
            return False
        return card.is_leaf_missing(field_name)


def format_clarification_question(
    *,
    question_number: int,
    total_questions: int,
    prompt: str,
    quick_reply_options: list[str],
) -> str:
    header = f"Quick question {question_number} of {total_questions}: {prompt}"
    choices = "\n".join(f"- {option}" for option in quick_reply_options)
    body = f"{header}\nChoose one or more options and/or answer in your own words:\n{choices}"
    return textwrap.dedent(body).strip()


def is_unspecified_answer(answer: str) -> bool:
    return answer.strip().lower() in UNSPECIFIED_ANSWERS

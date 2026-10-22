import json
import textwrap
from collections.abc import Callable

from pydantic import BaseModel, Field, field_validator

from prompt_piper_api.domain.agent_contract import (
    CONTRACT_FIELD_NAMES,
    quick_reply_labels,
)
from prompt_piper_api.domain.application_requirements import (
    APPLICATION_QUESTIONS,
)
from prompt_piper_api.domain.consultation import (
    CONSULTANT_PERSONA,
    CONSULTATION_TOPICS,
    SPECIAL_REPLIES,
    consultation_fields,
    reconcile_unresolved,
)
from prompt_piper_api.domain.limits import MAX_CLARIFICATION_QUESTIONS
from prompt_piper_api.domain.requirement_card import LEAF_FIELD_NAMES, RequirementCard
from prompt_piper_api.llm.base import ChatMessage, LLMClient
from prompt_piper_api.llm.fallback import with_llm_fallback
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


CLARIFICATION_FIELD_PRIORITY: tuple[str, ...] = tuple(CONSULTATION_TOPICS)

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
    field_name: (
        *quick_reply_labels(field_name)[:-1],
        "Unsure",
        "Not applicable",
        "Recommend an option",
        "unspecified",
    )
    for field_name in CONTRACT_FIELD_NAMES
}

QUICK_REPLY_OPTIONS.update(
    {q.field_name: tuple(o.label for o in q.options) for q in APPLICATION_QUESTIONS}
)

QUICK_REPLY_OPTIONS.update(
    {
        field_name: (*topic.choices, *SPECIAL_REPLIES)
        for field_name, topic in CONSULTATION_TOPICS.items()
    }
)

UNSPECIFIED_ANSWERS = frozenset({"unspecified", "skip", "unknown", "not sure", "n/a"})


def clarification_field_priority(card: RequirementCard) -> tuple[str, ...]:
    """Architectural decisions only; execution policies are resolved separately."""
    return consultation_fields(card)


def prune_deferred_unresolved(card: RequirementCard) -> None:
    reconcile_unresolved(card)


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
        if len(options) < 4:
            msg = "Quick reply options must include at least three choices plus unspecified."
            raise ValueError(msg)
        if options[-1].strip().lower() != "unspecified":
            msg = "Quick reply options must end with unspecified."
            raise ValueError(msg)
        return options


class ClarificationQuestionRanker:
    """Ranks missing coding-dimension leaves and builds one quick question at a time."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        llm_factory: Callable[[], LLMClient | None] | None = None,
    ) -> None:
        self._llm = llm
        self._llm_factory = llm_factory

    def missing_fields(self, card: RequirementCard) -> list[str]:
        reconcile_unresolved(card)
        return list(card.unresolved_fields)

    def rank(self, card: RequirementCard) -> list[ClarificationQuestion]:
        ordered_fields = self.missing_fields(card)
        return [
            self.build_question(
                field_name,
                question_number=index,
                total_questions=len(clarification_field_priority(card)),
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
        initial_request: str = "",
        tailor: bool = True,
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
                initial_request=initial_request,
                tailor=tailor,
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
        initial_request: str = "",
        tailor: bool = False,
    ) -> ClarificationQuestion:
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
        result = ClarificationQuestion(
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
        if tailor and card is not None:
            try:
                client = self._llm_factory() if self._llm_factory else self._llm
            except Exception:
                return result
            return with_llm_fallback(
                client,
                lambda llm: self._tailor(llm, result, card, initial_request, last_answer),
                lambda: result,
            )
        return result

    def _tailor(
        self,
        llm: LLMClient,
        question: ClarificationQuestion,
        card: RequirementCard,
        initial_request: str,
        last_answer: str | None,
    ) -> ClarificationQuestion:
        context = {
            "initial_request": initial_request,
            "accepted_requirements": card.coding_spec_dict(),
            "field_name": question.field_name,
            "base_prompt": question.prompt,
            "last_answer": last_answer,
            "default_options": question.quick_reply_options,
        }
        response = llm.chat(
            [
                ChatMessage(
                    role="system",
                    content=CONSULTANT_PERSONA
                    + "Tailor only the selected field; do not change the topic or answer it. "
                    "Return JSON with prompt, beginner_prompt, advanced_prompt, rationale "
                    "(nonempty "
                    "strings), and suggested_answers (an array of concise alternative answers, "
                    "not accepted facts). All prompts must ask the same architectural question. "
                    "Use supplied facts to focus on remaining gaps; do not add speculative scope.",
                ),
                ChatMessage(role="user", content=json.dumps(context)),
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.content)
        if not isinstance(payload, dict):
            raise ValueError("Expected tailored question object")
        for key in ("prompt", "beginner_prompt", "advanced_prompt", "rationale"):
            if not isinstance(payload.get(key), str) or not 1 <= len(payload[key].strip()) <= 1600:
                raise ValueError("Invalid tailored question text")
        answers = payload.get("suggested_answers", [])
        if (
            not isinstance(answers, list)
            or len(answers) > 5
            or any(not isinstance(a, str) or not 1 <= len(a.strip()) <= 400 for a in answers)
        ):
            raise ValueError("Invalid tailored question options")
        result = question.model_copy(deep=True)
        result.prompt = payload["prompt"].strip()
        for version, key in zip(
            result.versions, ("beginner_prompt", "prompt", "advanced_prompt"), strict=True
        ):
            version.prompt = payload[key].strip()
            if version.level == "beginner":
                version.rationale = payload["rationale"].strip()
        # Context choices drive applicability; keep their stable labels.
        if answers and question.field_name != "application_requirements.project_context":
            options = [
                a.strip()
                for a in answers
                if a.strip().casefold() not in {x.casefold() for x in SPECIAL_REPLIES}
            ]
            result.quick_reply_options = list(dict.fromkeys([*options, *SPECIAL_REPLIES]))
            result.quick_reply_guides = [
                QuickReplyGuide(
                    option=option,
                    explanation=payload["rationale"].strip(),
                    when_to_use=(
                        "Choose only if this matches your requirements; proposals are not "
                        "accepted until submitted."
                    ),
                )
                for option in result.quick_reply_options
            ]
        result.question = format_clarification_question(
            question_number=result.question_number,
            total_questions=result.total_questions,
            prompt=result.prompt,
            quick_reply_options=result.quick_reply_options,
        )
        return ClarificationQuestion.model_validate(result.model_dump())

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

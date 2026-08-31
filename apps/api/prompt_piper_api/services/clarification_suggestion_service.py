from __future__ import annotations

import json

from pydantic import BaseModel, Field

from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.base import ChatMessage, LLMClient
from prompt_piper_api.llm.fallback import with_llm_fallback
from prompt_piper_api.services.clarification_question_ranker import (
    FOCUSED_PROMPTS,
    QUICK_REPLY_OPTIONS,
)


class ClarificationSuggestions(BaseModel):
    field_name: str
    suggested_question: str | None = None
    suggested_answers: list[str] = Field(default_factory=list)
    model_available: bool = False
    message: str | None = None


class ClarificationSuggestionService:
    """On-demand model suggestions for a single clarification field."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def suggest(
        self,
        *,
        initial_request: str,
        card: RequirementCard,
        field_name: str,
        last_answer: str | None = None,
        asked_fields: list[str] | None = None,
    ) -> ClarificationSuggestions:
        base_prompt = FOCUSED_PROMPTS.get(field_name, "what should this field contain?")
        fallback_options = [
            option
            for option in QUICK_REPLY_OPTIONS.get(field_name, ())
            if option.lower() != "unspecified"
        ]

        def unavailable(message: str) -> ClarificationSuggestions:
            # Keep concrete template answers available offline so CPU-only flows
            # are not left with an empty suggestion panel.
            return ClarificationSuggestions(
                field_name=field_name,
                suggested_question=base_prompt,
                suggested_answers=fallback_options[:4],
                model_available=False,
                message=message,
            )

        return with_llm_fallback(
            self._llm,
            lambda client: self._suggest_with_llm(
                client,
                initial_request=initial_request,
                card=card,
                field_name=field_name,
                base_prompt=base_prompt,
                last_answer=last_answer,
                asked_fields=asked_fields or [],
                fallback_options=fallback_options,
            ),
            lambda: unavailable(
                "Model unavailable. Use quick replies or enter your own answer, then submit."
            ),
        )

    def _suggest_with_llm(
        self,
        llm: LLMClient,
        *,
        initial_request: str,
        card: RequirementCard,
        field_name: str,
        base_prompt: str,
        last_answer: str | None,
        asked_fields: list[str],
        fallback_options: list[str],
    ) -> ClarificationSuggestions:
        context = {
            "initial_request": initial_request,
            "requirement_card": card.model_dump(),
            "field_name": field_name,
            "base_prompt": base_prompt,
            "last_answer": last_answer,
            "asked_fields": asked_fields,
            "default_quick_replies": fallback_options,
        }
        response = llm.chat(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "Suggest clarification answers for one prompt requirement field. "
                        "Use the initial request and fields already captured; do not invent facts. "
                        "Return JSON with keys: "
                        'prompt (optional rephrased one-sentence question ending with ?), '
                        "suggested_answers (3 to 5 concise options tailored to context). "
                        "Do not include 'unspecified' in suggested_answers."
                    ),
                ),
                ChatMessage(role="user", content=json.dumps(context)),
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.content)
        suggested_question = str(payload.get("prompt", base_prompt)).strip() or base_prompt
        raw_answers = payload.get("suggested_answers", [])
        suggested_answers = [
            str(item).strip()
            for item in raw_answers
            if str(item).strip() and str(item).strip().lower() != "unspecified"
        ][:5]
        if not suggested_answers:
            suggested_answers = fallback_options[:4]

        return ClarificationSuggestions(
            field_name=field_name,
            suggested_question=suggested_question,
            suggested_answers=suggested_answers,
            model_available=True,
            message="Model suggestions are ready. Select any that fit, then submit.",
        )

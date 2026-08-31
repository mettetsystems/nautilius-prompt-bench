"""Ask The Locals — contextual recommendations for the current clarification question."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from prompt_piper_api.domain.requirement_card import LEAF_FIELD_NAMES, RequirementCard
from prompt_piper_api.llm.base import ChatMessage, LLMClient, LLMError
from prompt_piper_api.services.clarification_option_guides import build_quick_reply_guides
from prompt_piper_api.services.clarification_prompts import STANDARD_PROMPTS

# Keep payloads small for tiny local models (e.g. qwen3-0.6b).
_MAX_INITIAL_REQUEST_CHARS = 400
_MAX_OPTION_GUIDES = 5
# One-word to one-sentence JSON answer; keep decode budget tiny.
_SHORT_ANSWER_MAX_TOKENS = 64


def _first_sentence(text: str) -> str:
    """Clamp model output to at most one sentence (or a short phrase)."""
    cleaned = " ".join(text.split()).strip().strip("\"'`")
    if not cleaned:
        return ""
    for separator in (". ", "! ", "? ", "\n"):
        if separator in cleaned:
            head, _sep, _rest = cleaned.partition(separator)
            end = separator.strip()
            return f"{head}{end}" if end in ".!?" else head
    return cleaned


class AskTheLocalsInsight(BaseModel):
    field_name: str
    insight: str = ""
    recommended_answer: str = ""
    previous_answers_used: list[str] = Field(default_factory=list)
    model_available: bool = False
    model_source: str | None = None
    message: str | None = None


def collect_previous_answers(
    card: RequirementCard,
    *,
    exclude_field: str | None = None,
) -> dict[str, Any]:
    """Return non-empty requirement-card answers, excluding the active field."""
    answers: dict[str, Any] = {}
    for field_name in sorted(LEAF_FIELD_NAMES):
        if field_name == exclude_field:
            continue
        if card.is_leaf_missing(field_name):
            continue
        value = card.get_leaf(field_name)
        if field_name == "optimization_targets":
            dumped = value.model_dump() if hasattr(value, "model_dump") else value
            filled = {key: item for key, item in dumped.items() if item}
            if filled:
                answers[field_name] = filled
            continue
        answers[field_name] = value
    return answers


class AskTheLocalsService:
    """On-demand contextual recommendations for the active clarification question."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def ask(
        self,
        *,
        initial_request: str,
        card: RequirementCard,
        field_name: str,
        last_answer: str | None = None,
        asked_fields: list[str] | None = None,
        model_source: str | None = None,
    ) -> AskTheLocalsInsight:
        del asked_fields  # Kept for call-site compatibility; not needed for short answers.
        standard_prompt = STANDARD_PROMPTS.get(field_name, "What should this field contain?")
        option_guides = [
            guide.model_dump()
            for guide in build_quick_reply_guides(field_name)[:_MAX_OPTION_GUIDES]
        ]
        previous_answers = collect_previous_answers(card, exclude_field=field_name)

        def unavailable(message: str) -> AskTheLocalsInsight:
            return AskTheLocalsInsight(
                field_name=field_name,
                insight="",
                recommended_answer="",
                previous_answers_used=list(previous_answers.keys()),
                model_available=False,
                model_source=model_source,
                message=message,
            )

        if self._llm is None:
            return unavailable(
                "Ask The Locals is unavailable. Configure the current AI tooling model "
                "or an Ask The Locals API in Settings."
            )

        try:
            health = self._llm.health_check()
        except Exception as exc:  # noqa: BLE001 — surface probe failures to the UI
            return unavailable(
                f"Ask The Locals could not reach the model endpoint: {exc}"
            )
        if not health.ok:
            return unavailable(
                "Ask The Locals could not reach the model endpoint "
                f"({health.message}). Check Settings / the local server, then retry."
            )

        try:
            return self._ask_with_llm(
                self._llm,
                initial_request=initial_request,
                field_name=field_name,
                standard_prompt=standard_prompt,
                option_guides=option_guides,
                previous_answers=previous_answers,
                last_answer=last_answer,
                model_source=model_source,
            )
        except (LLMError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
            detail = str(exc).strip() or exc.__class__.__name__
            return unavailable(
                "Ask The Locals reached the model but the response failed "
                f"({detail[:240]}). Tiny models like qwen3-0.6b often need a shorter "
                "prompt or a larger max_tokens; retry or use a larger preset."
            )
        except Exception as exc:  # noqa: BLE001
            detail = str(exc).strip() or exc.__class__.__name__
            return unavailable(
                f"Ask The Locals failed unexpectedly ({detail[:240]})."
            )

    def _ask_with_llm(
        self,
        llm: LLMClient,
        *,
        initial_request: str,
        field_name: str,
        standard_prompt: str,
        option_guides: list[dict[str, str]],
        previous_answers: dict[str, Any],
        last_answer: str | None,
        model_source: str | None,
    ) -> AskTheLocalsInsight:
        # Slim context: full requirement_card dumps routinely blow tiny-model budgets.
        context = {
            "initial_request": initial_request.strip()[:_MAX_INITIAL_REQUEST_CHARS],
            "previous_answers": previous_answers,
            "field_name": field_name,
            "question": standard_prompt,
            "option_labels": [guide.get("option", "") for guide in option_guides],
            "last_answer": last_answer,
        }
        response = llm.chat(
            [
                ChatMessage(
                    role="system",
                    content=(
                        "Answer one clarification field for a coding prompt. "
                        "Stay consistent with previous_answers. Do not invent project facts. "
                        "Return JSON only with key recommended_answer. "
                        "recommended_answer must be between 1 word and 1 sentence "
                        "(paste-ready; no quotes, no explanation, no markdown)."
                    ),
                ),
                ChatMessage(role="user", content=json.dumps(context)),
            ],
            response_format={"type": "json_object"},
            max_tokens=_SHORT_ANSWER_MAX_TOKENS,
        )
        payload = json.loads(response.content)
        recommended_answer = _first_sentence(
            str(
                payload.get("recommended_answer")
                or payload.get("recommendation")
                or payload.get("insight")
                or ""
            )
        )
        if not recommended_answer and option_guides:
            recommended_answer = str(option_guides[0].get("option", "")).strip()

        return AskTheLocalsInsight(
            field_name=field_name,
            insight="",
            recommended_answer=recommended_answer,
            previous_answers_used=list(previous_answers.keys()),
            model_available=True,
            model_source=model_source,
            message=(
                "Short recommendation ready."
                if previous_answers
                else "Local recommendation ready."
            ),
        )

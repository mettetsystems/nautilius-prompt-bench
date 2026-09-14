from __future__ import annotations

import json

from fastapi.testclient import TestClient

from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.domain.user_settings import ClarificationVersionsAvailable
from prompt_piper_api.llm.base import ChatMessage, LLMError
from prompt_piper_api.llm.mock import MockLLMClient
from prompt_piper_api.llm.local_openai import extract_json_object
from prompt_piper_api.services.ask_the_locals_service import (
    AskTheLocalsService,
    _SHORT_ANSWER_MAX_TOKENS,
    collect_previous_answers,
)
from prompt_piper_api.services.clarification_option_guides import (
    assert_guides_cover_all_options,
    build_quick_reply_guides,
)
from prompt_piper_api.services.clarification_prompts import (
    ADVANCED_PROMPTS,
    BEGINNER_PROMPTS,
    ClarificationLevel,
    STANDARD_PROMPTS,
    build_version_texts,
)
from prompt_piper_api.services.clarification_question_ranker import ClarificationQuestionRanker


def test_prompt_maps_cover_same_fields() -> None:
    assert set(STANDARD_PROMPTS) == set(BEGINNER_PROMPTS) == set(ADVANCED_PROMPTS)


def test_build_version_texts_includes_beginner_rationale() -> None:
    versions = build_version_texts("agent_contract.definition_of_done")
    assert [item.level for item in versions] == [
        ClarificationLevel.BEGINNER,
        ClarificationLevel.STANDARD,
        ClarificationLevel.ADVANCED,
    ]
    beginner = versions[0]
    assert beginner.rationale is not None
    assert "finish" in beginner.rationale.lower() or "honest" in beginner.rationale.lower()
    assert versions[1].prompt == STANDARD_PROMPTS["agent_contract.definition_of_done"]
    assert versions[2].prompt == ADVANCED_PROMPTS["agent_contract.definition_of_done"]
    assert versions[1].rationale is None


def test_ranker_attaches_all_versions() -> None:
    question = ClarificationQuestionRanker().build_question(
        "agent_contract.definition_of_done",
        question_number=1,
        total_questions=16,
    )
    assert len(question.versions) == 3
    assert question.versions[1].level is ClarificationLevel.STANDARD
    assert question.prompt == STANDARD_PROMPTS["agent_contract.definition_of_done"]


def test_clarification_versions_available_defaults_and_fallback() -> None:
    defaults = ClarificationVersionsAvailable()
    assert defaults.enabled_levels() == ["beginner", "standard", "advanced"]
    none_enabled = ClarificationVersionsAvailable(
        beginner=False,
        standard=False,
        advanced=False,
    )
    assert none_enabled.enabled_levels() == ["standard"]


def test_context_compaction_prompts_treat_100k_as_large_for_local_2026() -> None:
    versions = build_version_texts("agent_contract.context_compaction")
    blob = " ".join(item.prompt for item in versions)
    blob += " " + (versions[0].rationale or "")
    assert "100,000" in blob
    assert "2026" in blob
    assert "local" in blob.lower()


def test_beginner_option_guides_cover_every_quick_reply() -> None:
    assert_guides_cover_all_options()
    guides = build_quick_reply_guides("agent_contract.definition_of_done")
    assert len(guides) == 7
    assert {"Unsure", "Not applicable", "Recommend an option"} <= {g.option for g in guides}
    assert "COMPLETE" in guides[0].option


def test_ask_the_locals_falls_back_without_model() -> None:
    result = AskTheLocalsService(llm=None).ask(
        initial_request="Write a FastAPI signup endpoint",
        card=RequirementCard(),
        field_name="agent_contract.definition_of_done",
    )
    assert result.model_available is False
    assert result.insight == ""
    assert result.recommended_answer == ""
    assert result.message is not None
    assert "unavailable" in result.message.lower()


def test_ask_the_locals_reports_chat_failure_instead_of_generic_unavailable() -> None:
    class BrokenClient(MockLLMClient):
        def chat(
            self,
            messages: list[ChatMessage],
            *,
            response_format: dict | None = None,
            max_tokens: int | None = None,
        ):
            del messages, response_format, max_tokens
            raise LLMError("HTTP 404: model 'qwen3-0.6b' not found")

    result = AskTheLocalsService(BrokenClient()).ask(
        initial_request="Write a FastAPI signup endpoint",
        card=RequirementCard(task_identity={"environment": "FastAPI", "objective": "Add signup"}),
        field_name="agent_contract.change_scope",
        model_source="Current AI tooling (qwen3-0.6b)",
    )
    assert result.model_available is False
    assert result.model_source == "Current AI tooling (qwen3-0.6b)"
    assert "reached the model" in (result.message or "").lower()
    assert "404" in (result.message or "")


def test_extract_json_object_strips_qwen_think_tags() -> None:
    payload = extract_json_object(
        '<think>planning...</think>\n{"insight": "ok", "recommended_answer": "FastAPI"}'
    )
    assert payload["insight"] == "ok"
    assert payload["recommended_answer"] == "FastAPI"


def test_ask_the_locals_slims_context_without_full_card_dump() -> None:
    captured: dict[str, object] = {}

    def responder(messages: list[ChatMessage]) -> str:
        captured["user"] = messages[-1].content
        return json.dumps({"recommended_answer": "JSON body with email and full_name"})

    card = RequirementCard(
        task_identity={
            "environment": "Python 3.12 with FastAPI",
            "objective": "Add a user signup endpoint",
        },
    )
    result = AskTheLocalsService(MockLLMClient(chat_responder=responder)).ask(
        initial_request="Write a FastAPI signup endpoint",
        card=card,
        field_name="agent_contract.change_scope",
        model_source="ai-tooling",
    )
    assert result.model_available is True
    assert result.insight == ""
    user_payload = json.loads(str(captured["user"]))
    assert "requirement_card" not in user_payload
    assert "previous_answers" in user_payload
    assert "option_labels" in user_payload


def test_ask_the_locals_clamps_verbose_recommendation_to_one_sentence() -> None:
    def responder(_messages: list[ChatMessage]) -> str:
        return json.dumps(
            {
                "recommended_answer": (
                    "Use FastAPI with Pydantic. Also rewrite the whole auth stack. "
                    "And add OpenTelemetry."
                )
            }
        )

    result = AskTheLocalsService(MockLLMClient(chat_responder=responder)).ask(
        initial_request="Write a FastAPI signup endpoint",
        card=RequirementCard(),
        field_name="agent_contract.definition_of_done",
    )
    assert result.recommended_answer == "Use FastAPI with Pydantic."


def test_ask_the_locals_requests_short_max_tokens() -> None:
    mock = MockLLMClient(
        chat_responder=lambda _messages: json.dumps(
            {"recommended_answer": "Python 3.12 with FastAPI"}
        )
    )
    result = AskTheLocalsService(mock).ask(
        initial_request="Write a FastAPI signup endpoint",
        card=RequirementCard(),
        field_name="agent_contract.definition_of_done",
    )
    assert result.model_available is True
    assert result.insight == ""
    assert mock.last_chat_max_tokens == _SHORT_ANSWER_MAX_TOKENS
    assert _SHORT_ANSWER_MAX_TOKENS <= 64


def test_ask_the_locals_uses_previous_answers_for_recommendation() -> None:
    captured: dict[str, object] = {}

    def responder(messages: list[ChatMessage]) -> str:
        captured["user"] = messages[-1].content
        return json.dumps(
            {
                "recommended_answer": "Use Pydantic v2 request models matching the existing signup schema.",
            }
        )

    card = RequirementCard(
        task_identity={
            "environment": "Python 3.12 with FastAPI",
            "objective": "Add a user signup endpoint",
        },
    )
    result = AskTheLocalsService(MockLLMClient(chat_responder=responder)).ask(
        initial_request="Write a FastAPI signup endpoint",
        card=card,
        field_name="agent_contract.change_scope",
        last_answer="Python 3.12 with FastAPI",
        asked_fields=["agent_contract.definition_of_done"],
        model_source="ai-tooling",
    )

    assert result.model_available is True
    assert result.insight == ""
    assert result.recommended_answer.startswith("Use Pydantic")
    assert "task_identity.objective" in result.previous_answers_used
    assert "agent_contract.change_scope" not in result.previous_answers_used
    user_payload = json.loads(str(captured["user"]))
    assert user_payload["previous_answers"]["task_identity.objective"] == (
        "Add a user signup endpoint"
    )
    assert "Short recommendation" in (result.message or "")


def test_collect_previous_answers_skips_empty_and_active_field() -> None:
    card = RequirementCard(
        task_identity={"environment": "Python 3.12", "objective": "Build signup"},
    )
    answers = collect_previous_answers(card, exclude_field="agent_contract.definition_of_done")
    assert "agent_contract.definition_of_done" not in answers
    assert answers["task_identity.objective"] == "Build signup"


def test_ask_the_locals_api_route(client: TestClient) -> None:
    create = client.post(
        "/sessions",
        json={"initial_request": "Write a FastAPI endpoint for user signup"},
    )
    assert create.status_code == 201
    session_id = create.json()["session"]["id"]
    response = client.post(f"/sessions/{session_id}/clarify/locals")
    assert response.status_code == 200
    payload = response.json()
    assert payload["field_name"]
    assert payload["model_available"] is False
    message = (payload["message"] or "").lower()
    assert "ask the locals" in message
    assert "unavailable" in message or "could not reach" in message or "failed" in message


def test_session_api_returns_clarification_versions(client: TestClient) -> None:
    create = client.post(
        "/sessions",
        json={"initial_request": "Write a FastAPI endpoint for user signup"},
    )
    assert create.status_code == 201
    payload = create.json()
    versions = payload["clarification_versions"]
    assert len(versions) == 3
    assert [item["level"] for item in versions] == ["beginner", "standard", "advanced"]
    assert versions[0]["rationale"]
    assert versions[1]["prompt"]


def test_user_settings_api_clarification_versions(client: TestClient) -> None:
    current = client.get("/settings/user")
    assert current.status_code == 200
    body = current.json()
    assert body["clarification_versions"] == {
        "beginner": True,
        "standard": True,
        "advanced": True,
    }
    assert body["ask_the_locals_api_override"]["configured"] is False
    update = {
        "llm_enabled": body["llm_enabled"],
        "precision_warning_threshold": body["precision_warning_threshold"],
        "similarity_time_scope_index": body["similarity_time_scope_index"],
        "clarification_versions": {
            "beginner": True,
            "standard": False,
            "advanced": True,
        },
        "default_api_endpoint_id": body["default_api_endpoint_id"],
        "api_endpoints": [
            {
                "id": endpoint["id"],
                "label": endpoint["label"],
                "base_url": endpoint["base_url"],
                "chat_model": endpoint["chat_model"],
            }
            for endpoint in body["api_endpoints"]
        ],
        "ai_tooling_api_override": {
            "label": body["ai_tooling_api_override"]["label"],
            "base_url": body["ai_tooling_api_override"]["base_url"],
            "chat_model": body["ai_tooling_api_override"]["chat_model"],
        },
        "ask_the_locals_api_override": {
            "label": "Locals",
            "base_url": "https://locals.example/v1",
            "chat_model": "locals-model",
        },
    }
    saved = client.put("/settings/user", json=update)
    assert saved.status_code == 200
    assert saved.json()["clarification_versions"] == {
        "beginner": True,
        "standard": False,
        "advanced": True,
    }
    assert saved.json()["ask_the_locals_override_active"] is True
    assert saved.json()["ask_the_locals_api_override"]["chat_model"] == "locals-model"

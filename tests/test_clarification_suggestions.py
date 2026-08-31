import json

import pytest
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.llm.base import ChatMessage, ChatResponse, EmbedResponse, HealthCheckResult
from prompt_piper_api.llm.enums import ModelProvider
from prompt_piper_api.services.clarification_suggestion_service import ClarificationSuggestionService
from prompt_piper_api.services.exceptions import StateTransitionError
from prompt_piper_api.services.session_service import SessionService


class StubLLMClient:
    def __init__(self, content: str) -> None:
        self._content = content

    @property
    def provider(self) -> ModelProvider:
        return ModelProvider.LOCAL_OPENAI_COMPATIBLE

    def health_check(self) -> HealthCheckResult:
        return HealthCheckResult(
            ok=True,
            provider=ModelProvider.LOCAL_OPENAI_COMPATIBLE,
            message="ok",
        )

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        response_format: dict[str, str] | None = None,
    ) -> ChatResponse:
        del messages, response_format
        return ChatResponse(
            content=self._content,
            model="stub",
            provider=ModelProvider.LOCAL_OPENAI_COMPATIBLE,
        )

    def embed(self, texts: list[str]) -> EmbedResponse:
        return EmbedResponse(vectors=[[0.1] * 8 for _ in texts], model="stub")


def test_suggestion_service_returns_model_answers_when_llm_available() -> None:
    payload = json.dumps(
        {
            "prompt": "What is the precise stack for this coding prompt?",
            "suggested_answers": [
                "Python with FastAPI and Pydantic",
                "TypeScript / React",
                "stdlib only",
            ],
        }
    )
    service = ClarificationSuggestionService(
        StubLLMClient(payload),
    )
    card = RequirementCard(
        task_identity={"objective": "Add FastAPI user create endpoint"}
    )

    result = service.suggest(
        initial_request="Add a FastAPI endpoint that creates users",
        card=card,
        field_name="agent_contract.definition_of_done",
    )

    assert result.model_available is True
    assert result.field_name == "agent_contract.definition_of_done"
    assert len(result.suggested_answers) == 3
    assert "Python with FastAPI and Pydantic" in result.suggested_answers or any(
        "COMPLETE" in item for item in result.suggested_answers
    )


def test_suggestion_service_reports_unavailable_without_llm() -> None:
    service = ClarificationSuggestionService(None)
    card = RequirementCard(task_identity={"objective": "Draft a release note generator"})

    result = service.suggest(
        initial_request="Draft a release note generator",
        card=card,
        field_name="agent_contract.definition_of_done",
    )

    assert result.model_available is False
    assert len(result.suggested_answers) >= 3
    assert any("COMPLETE" in item for item in result.suggested_answers)
    assert result.message is not None
    assert result.suggested_question is not None


def test_session_service_suggest_clarification_uses_pending_field() -> None:
    payload = json.dumps(
        {
            "prompt": "What output format fits best?",
            "suggested_answers": ["JSON schema", "markdown report"],
        }
    )
    service = SessionService(llm=StubLLMClient(payload))
    created = service.create_session(initial_request="Summarize customer interview notes")
    session_id = created.record.session.id

    suggestions = service.suggest_clarification(session_id)

    assert suggestions.field_name == created.clarification_field
    assert suggestions.model_available is True
    assert len(suggestions.suggested_answers) >= 2


def test_session_service_suggest_requires_clarifying_state() -> None:
    service = SessionService(llm=None)
    created = service.create_session(initial_request="Draft a release note prompt")
    session_id = created.record.session.id
    record = service.get_session(session_id)
    record.session.state = SessionState.APPROVAL
    service._save(record)

    with pytest.raises(StateTransitionError):
        service.suggest_clarification(session_id)


def test_clarification_advances_without_model_query() -> None:
    service = SessionService(llm=None)
    created = service.create_session(initial_request="Write a weekly status update prompt")
    session_id = created.record.session.id
    first_field = created.clarification_field

    result = service.answer_clarification(session_id, "new feature logic")

    assert result.clarification_field != first_field
    assert result.record.session.state is SessionState.CLARIFYING

from collections.abc import Callable
from typing import Any

from prompt_piper_api.llm.base import (
    ChatMessage,
    ChatResponse,
    EmbedResponse,
    HealthCheckResult,
    LLMClient,
)
from prompt_piper_api.llm.enums import ModelProvider
from prompt_piper_api.llm.settings import ModelSettings


class MockLLMClient:
    """Deterministic LLM client for tests and offline development."""

    def __init__(
        self,
        *,
        settings: ModelSettings | None = None,
        chat_responder: Callable[[list[ChatMessage]], str] | None = None,
        embed_responder: Callable[[list[str]], list[list[float]]] | None = None,
        healthy: bool = True,
    ) -> None:
        self._settings = settings or ModelSettings(
            provider=ModelProvider.LOCAL_OPENAI_COMPATIBLE,
            base_url="mock://local",
            model_name="mock-chat",
            enabled=True,
        )
        self._chat_responder = chat_responder or self._default_chat_response
        self._embed_responder = embed_responder or self._default_embed_response
        self._healthy = healthy
        self.chat_calls: list[list[ChatMessage]] = []
        self.embed_calls: list[list[str]] = []
        self.last_chat_max_tokens: int | None = None
        self.last_chat_response_format: dict[str, Any] | None = None

    @property
    def provider(self) -> ModelProvider:
        return self._settings.provider

    @property
    def settings(self) -> ModelSettings:
        return self._settings

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        self.chat_calls.append(messages)
        self.last_chat_max_tokens = max_tokens
        self.last_chat_response_format = response_format
        content = self._chat_responder(messages)
        return ChatResponse(
            content=content, model=self._settings.model_name, provider=self.provider
        )

    def embed(self, texts: list[str]) -> EmbedResponse:
        self.embed_calls.append(texts)
        vectors = self._embed_responder(texts)
        return EmbedResponse(
            vectors=vectors, model=self._settings.model_name, provider=self.provider
        )

    def health_check(self) -> HealthCheckResult:
        if self._healthy:
            return HealthCheckResult(
                ok=True,
                provider=self.provider,
                message="Mock LLM client is healthy.",
                model_name=self._settings.model_name,
            )
        return HealthCheckResult(
            ok=False,
            provider=self.provider,
            message="Mock LLM client configured as unhealthy.",
            model_name=self._settings.model_name,
        )

    @staticmethod
    def _default_chat_response(messages: list[ChatMessage]) -> str:
        user_text = " ".join(message.content for message in messages if message.role == "user")
        return f"mock-response:{user_text[:120]}"

    @staticmethod
    def _default_embed_response(texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]


def as_llm_client(client: MockLLMClient) -> LLMClient:
    return client

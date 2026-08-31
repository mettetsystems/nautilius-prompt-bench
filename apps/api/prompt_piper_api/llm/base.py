from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel

from prompt_piper_api.llm.enums import ModelProvider


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatResponse(BaseModel):
    content: str
    model: str | None = None
    provider: ModelProvider | None = None


class EmbedResponse(BaseModel):
    vectors: list[list[float]]
    model: str | None = None
    provider: ModelProvider | None = None


class HealthCheckResult(BaseModel):
    ok: bool
    provider: ModelProvider
    message: str
    model_name: str | None = None


class LLMError(Exception):
    """Raised when an LLM request fails."""


@runtime_checkable
class LLMClient(Protocol):
    """OpenAI-compatible local or external inference client."""

    @property
    def provider(self) -> ModelProvider:
        """Which provider this client represents."""

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Run a chat completion.

        ``max_tokens`` overrides the client default when set (used for short
        Ask The Locals answers).
        """

    def embed(self, texts: list[str]) -> EmbedResponse:
        """Generate embeddings for one or more texts."""

    def health_check(self) -> HealthCheckResult:
        """Check whether the configured endpoint is reachable."""

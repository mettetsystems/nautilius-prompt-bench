from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from prompt_piper_api.llm.base import (
    ChatMessage,
    ChatResponse,
    EmbedResponse,
    HealthCheckResult,
    LLMError,
)
from prompt_piper_api.llm.enums import ModelProvider
from prompt_piper_api.llm.settings import ModelSettings

_JSON_INSTRUCTION = (
    "Respond with a single valid JSON object only. "
    "Do not wrap the JSON in markdown fences or add commentary."
)

_UNSUPPORTED_JSON_MODE_MARKERS = (
    "response_format",
    "json_object",
    "json mode",
    "json_schema",
    "not supported",
    "unsupported",
    "unknown field",
    "invalid request",
)

# Avoid a second GET /models on every Ask The Locals click when health was just ok.
_HEALTH_CACHE_TTL_SECONDS = 10.0
_health_cache: dict[object, tuple[float, HealthCheckResult]] = {}


def clear_health_cache() -> None:
    """Reset cached health probes (tests / after settings change)."""
    _health_cache.clear()


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from model output, tolerating markdown fences and think tags."""
    cleaned = text.strip()
    if not cleaned:
        raise LLMError("Empty model response; expected a JSON object")

    # Qwen3 and similar reasoning models often emit <think>…</think> before JSON.
    cleaned = re.sub(
        r"<think>[\s\S]*?</think>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    cleaned = re.sub(
        r"<reasoning>[\s\S]*?</reasoning>",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("Model response did not contain a JSON object") from None
        try:
            payload = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("Failed to parse JSON from model response") from exc

    if not isinstance(payload, dict):
        raise LLMError("Expected a JSON object from model response")
    return payload


class LocalOpenAICompatibleClient:
    """OpenAI-compatible client for local servers such as llama.cpp."""

    def __init__(
        self,
        settings: ModelSettings,
        *,
        embed_model_name: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._settings = settings
        self._embed_model_name = embed_model_name or settings.model_name
        self._timeout = timeout
        self._base_url = settings.base_url.rstrip("/")
        self._json_mode_unsupported = False

    @property
    def provider(self) -> ModelProvider:
        return self._settings.provider

    @property
    def settings(self) -> ModelSettings:
        return self._settings

    @property
    def embed_model_name(self) -> str:
        return self._embed_model_name

    @property
    def timeout(self) -> float:
        return self._timeout

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        token_limit = max_tokens if max_tokens is not None else self._settings.max_tokens
        wants_json = response_format is not None and response_format.get("type") == "json_object"
        if wants_json and self._json_mode_unsupported:
            return self._chat_with_instruction_json(messages, max_tokens=token_limit)

        payload: dict[str, Any] = {
            "model": self._settings.model_name,
            "messages": [message.model_dump() for message in messages],
            "temperature": self._settings.temperature,
            "max_tokens": token_limit,
        }
        if wants_json:
            payload["response_format"] = response_format

        try:
            data = self._post("/chat/completions", payload)
        except LLMError as exc:
            if not (wants_json and self._looks_like_unsupported_json_mode(exc)):
                raise
            self._json_mode_unsupported = True
            return self._chat_with_instruction_json(messages, max_tokens=token_limit)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Unexpected chat completion response shape") from exc

        if wants_json:
            # Normalize fenced / noisy JSON into a clean object string for callers.
            parsed = extract_json_object(content if isinstance(content, str) else str(content))
            content = json.dumps(parsed)

        return ChatResponse(
            content=content,
            model=data.get("model", self._settings.model_name),
            provider=self.provider,
        )

    def embed(self, texts: list[str]) -> EmbedResponse:
        if not texts:
            return EmbedResponse(vectors=[], model=self._embed_model_name, provider=self.provider)

        payload = {"model": self._embed_model_name, "input": texts}
        data = self._post("/embeddings", payload)
        try:
            vectors = [item["embedding"] for item in data["data"]]
        except (KeyError, TypeError) as exc:
            raise LLMError("Unexpected embeddings response shape") from exc

        return EmbedResponse(
            vectors=vectors,
            model=data.get("model", self._embed_model_name),
            provider=self.provider,
        )

    def health_check(self) -> HealthCheckResult:
        cache_key = self._base_url
        cached = _health_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None:
            expires_at, result = cached
            if now < expires_at:
                return result

        headers = self._headers()
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.get(f"{self._base_url}/models", headers=headers)
            if response.status_code == 200:
                result = HealthCheckResult(
                    ok=True,
                    provider=self.provider,
                    message="Local OpenAI-compatible endpoint is reachable.",
                    model_name=self._settings.model_name,
                )
            else:
                result = HealthCheckResult(
                    ok=False,
                    provider=self.provider,
                    message=f"Local endpoint returned HTTP {response.status_code}.",
                    model_name=self._settings.model_name,
                )
        except httpx.HTTPError as exc:
            result = HealthCheckResult(
                ok=False,
                provider=self.provider,
                message=f"Local endpoint unreachable: {exc}",
                model_name=self._settings.model_name,
            )

        # Cache successes longer; still cache failures briefly to avoid hammering.
        ttl = _HEALTH_CACHE_TTL_SECONDS if result.ok else 2.0
        _health_cache[cache_key] = (now + ttl, result)
        return result

    def readiness_check(self) -> HealthCheckResult:
        from prompt_piper.setup.readiness import probe_inference
        # Include model and credentials: changing either requires a fresh probe.
        cache_key = (self._base_url, self._settings.model_name, self._settings.api_key, "inference")
        cached = _health_cache.get(cache_key)
        if cached and time.monotonic() < cached[0]:
            return cached[1]
        ok, message = probe_inference(self._base_url, self._settings.model_name,
                                      self._settings.api_key, timeout=self._timeout)
        result = HealthCheckResult(ok=ok, provider=self.provider, message=message,
                                   model_name=self._settings.model_name)
        _health_cache[cache_key] = (time.monotonic() + (60 if ok else 2), result)
        return result

    def _chat_with_instruction_json(
        self,
        messages: list[ChatMessage],
        *,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        token_limit = max_tokens if max_tokens is not None else self._settings.max_tokens
        augmented = list(messages)
        augmented.append(ChatMessage(role="system", content=_JSON_INSTRUCTION))
        payload: dict[str, Any] = {
            "model": self._settings.model_name,
            "messages": [message.model_dump() for message in augmented],
            "temperature": self._settings.temperature,
            "max_tokens": token_limit,
        }
        data = self._post("/chat/completions", payload)
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Unexpected chat completion response shape") from exc

        parsed = extract_json_object(content if isinstance(content, str) else str(content))
        return ChatResponse(
            content=json.dumps(parsed),
            model=data.get("model", self._settings.model_name),
            provider=self.provider,
        )

    @staticmethod
    def _looks_like_unsupported_json_mode(exc: LLMError) -> bool:
        text = str(exc).lower()
        if any(marker in text for marker in _UNSUPPORTED_JSON_MODE_MARKERS):
            return True
        # Many local servers return an opaque 400/422 when json_object is rejected.
        return "http 400" in text or "http 422" in text

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = self._headers()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._base_url}{path}",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text.strip()
            message = f"HTTP {exc.response.status_code}"
            if detail:
                message = f"{message}: {detail[:500]}"
            raise LLMError(message) from exc
        except httpx.HTTPError as exc:
            raise LLMError(str(exc)) from exc

        data = response.json()
        if not isinstance(data, dict):
            raise LLMError("Expected JSON object response from LLM endpoint")
        return data

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        return headers

"""Inference readiness shared by setup and API health checks."""
from __future__ import annotations

import time

import httpx


def probe_inference(base_url: str, model: str, api_key: str | None = None, *, timeout: float = 120, wait_seconds: float = 0) -> tuple[bool, str]:
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    deadline = time.monotonic() + wait_seconds
    while True:
        ok, message, transient = _probe_once(base_url, model, headers, timeout)
        if ok or not transient or time.monotonic() >= deadline:
            return ok, message
        time.sleep(min(2, max(0, deadline - time.monotonic())))


def _probe_once(base_url, model, headers, timeout):
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role": "user", "content": "Reply with the word ready. /no_think"}],
                      "max_tokens": 512, "temperature": 0, "stream": False, "chat_template_kwargs": {"enable_thinking": False}},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                return False, "Model returned an empty completion. Check its chat template and token budget.", False
        return True, "Model inference verified; ready for prompting.", False
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 503:
            return False, "Model is still loading, warming up, or busy (HTTP 503). Check the server log and retry.", True
        return False, f"Model inference failed (HTTP {exc.response.status_code}). Check the configured model ID and endpoint credentials.", False
    except httpx.HTTPError:
        return False, "Model inference timed out or endpoint is unreachable. Check the model server and available memory.", True
    except (ValueError, KeyError, IndexError, TypeError):
        return False, "Endpoint returned an invalid chat completion. An OpenAI-compatible chat model is required.", False

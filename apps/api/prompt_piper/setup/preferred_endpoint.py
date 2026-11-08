"""Select an already-running Maya-compatible endpoint before application startup."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from prompt_piper.setup.endpoint_discovery import (
    normalize_base_url,
    port_is_listening,
    probe_endpoint,
)

MAYA_BASE_URL = "http://127.0.0.1:8080/v1"


class PreferredEndpointUnavailable(RuntimeError):
    """A service is present but cannot safely be selected for inference."""


@dataclass(frozen=True)
class PreferredEndpoint:
    base_url: str
    model: str
    api_key: str | None = field(default=None, repr=False)

    @property
    def message(self) -> str:
        return f"Using preferred Maya-compatible endpoint {self.base_url}, model {self.model!r}."

    def environment(self) -> dict[str, str]:
        """Runtime overrides only; never rewrite the user's saved fallback configuration."""
        return {
            "PROMPT_PIPER_LOCAL_BASE_URL": self.base_url,
            "PROMPT_PIPER_LOCAL_CHAT_MODEL": self.model,
            "PROMPT_PIPER_LOCAL_EMBED_MODEL": self.model,
            "PROMPT_PIPER_LOCAL_API_KEY": self.api_key or "",
            "PROMPT_PIPER_LOCAL_MODEL_PRESET": "custom",
            "PROMPT_PIPER_DEPLOYMENT_PROFILE": "manual",
            "PROMPT_PIPER_AUTO_START_LLM": "false",
        }


def select_preferred_endpoint(env: Mapping[str, str]) -> PreferredEndpoint | None:
    """Prefer the running server using metadata only, leaving absent servers alone.

    The protocol is OpenAI-compatible: a process name or open TCP port alone does
    not establish model readiness. Authentication/busy/invalid listeners must not
    cause another model to be loaded as an automatic fallback.
    """
    enabled = env.get("PROMPT_PIPER_LLM_ENABLED", "true").strip().lower()
    prefer = env.get("PROMPT_PIPER_PREFER_MAYA", "true").strip().lower()
    if (
        enabled not in {"1", "true", "yes", "on"}
        or prefer not in {"1", "true", "yes", "on"}
        or env.get("PROMPT_PIPER_LOCAL_MODEL_PRESET") == "cpu-only"
    ):
        return None

    try:
        base_url = normalize_base_url(env.get("PROMPT_PIPER_MAYA_BASE_URL") or MAYA_BASE_URL)
    except ValueError as exc:
        raise PreferredEndpointUnavailable(
            "Invalid PROMPT_PIPER_MAYA_BASE_URL. Use an http(s) API base URL "
            "without embedded credentials, a query, or a fragment."
        ) from exc
    key = env.get("PROMPT_PIPER_MAYA_API_KEY")
    if key is None:
        # A saved credential for another endpoint must never be sent to Maya.
        try:
            configured = normalize_base_url(env.get("PROMPT_PIPER_LOCAL_BASE_URL") or MAYA_BASE_URL)
        except ValueError:
            configured = ""
        if configured == base_url:
            key = env.get("PROMPT_PIPER_LOCAL_API_KEY")

    endpoint = probe_endpoint(base_url, key)
    if endpoint is None and not port_is_listening(base_url):
        return None
    if endpoint is None or not endpoint.models:
        status = endpoint.status if endpoint else "no valid model-list response"
        raise PreferredEndpointUnavailable(
            f"A service is present at the preferred Maya endpoint {base_url}, but {status}. "
            "Check that Maya has finished loading and PROMPT_PIPER_MAYA_API_KEY is correct, "
            "then retry. To use your saved endpoint instead, set PROMPT_PIPER_PREFER_MAYA=false. "
            "No model was started or stopped."
        )

    # Preserve an explicit model choice if Maya advertises it; otherwise use its
    # first advertised model instead of a stale preset name such as 'llama'.
    configured_model = env.get("PROMPT_PIPER_LOCAL_CHAT_MODEL")
    model = (
        configured_model
        if configured_model and configured_model in endpoint.models
        else endpoint.models[0]
    )
    return PreferredEndpoint(endpoint.base_url, model, key)

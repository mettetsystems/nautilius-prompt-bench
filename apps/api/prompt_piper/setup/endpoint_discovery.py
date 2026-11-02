"""Discover existing servers without loading a model or generating a completion."""

from __future__ import annotations

import os
import socket
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

import httpx

# Maya / llama.cpp, vLLM, dedicated clarification, LM Studio, Ollama, and other
# common OpenAI-compatible listeners. Nonstandard URLs can be configured below.
DEFAULT_PORTS = (8080, 8000, 8081, 1234, 11434, 5000, 1337, 9931)
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "host.containers.internal", "host.docker.internal"}


@dataclass(frozen=True)
class ModelEndpoint:
    base_url: str
    models: tuple[str, ...] = ()
    status: str = "available"
    api_key: str | None = field(default=None, repr=False)


def normalize_base_url(value: str) -> str:
    """Accept a server root or API prefix, preserving reverse-proxy prefixes."""
    value = value.strip()
    address = urlsplit(value)
    if (
        address.scheme not in {"http", "https"}
        or not address.hostname
        or address.username is not None
        or address.password is not None
        or address.query
        or address.fragment
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise ValueError("Use an http(s) base URL without credentials, query, or fragment.")
    # Accessing .port validates the port number, including malformed IPv6 URLs.
    if address.port == 0:
        raise ValueError("Endpoint port must be between 1 and 65535.")
    path = address.path.rstrip("/") or "/v1"
    return urlunsplit((address.scheme, address.netloc, path, "", ""))


def is_local_endpoint(base_url: str) -> bool:
    return urlsplit(base_url).hostname in LOCAL_HOSTS


def probe_endpoint(
    base_url: str, api_key: str | None = None, *, timeout: float = 1.0
) -> ModelEndpoint | None:
    base_url = normalize_base_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        # Never forward saved credentials through redirects or environment proxies.
        with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False) as client:
            response = client.get(f"{base_url}/models", headers=headers)
        if response.status_code in {401, 403}:
            return ModelEndpoint(
                base_url, status="credentials required (unverified)", api_key=api_key
            )
        if response.status_code == 503:
            return ModelEndpoint(base_url, status="loading or busy (unverified)", api_key=api_key)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            return None
        models = tuple(
            dict.fromkeys(
                item["id"]
                for item in body["data"]
                if isinstance(item, dict)
                and isinstance(item.get("id"), str)
                and item["id"].strip()
                and all(ord(char) >= 32 for char in item["id"])
            )
        )
        if body["data"] and not models:
            return None
        return ModelEndpoint(
            base_url, models, "available" if models else "no models listed", api_key
        )
    except (httpx.HTTPError, ValueError):
        return None


def discover_endpoints(env: dict[str, str]) -> list[ModelEndpoint]:
    """Probe configured URLs and a small loopback-only port list concurrently.

    Credentials belong only to their configured URL, never to other candidates.
    Configuration-file values take precedence, including explicitly empty keys.
    """
    settings = {**os.environ, **env}
    candidates: dict[str, str | None] = {}

    def add(url: str, key: str | None = None) -> None:
        # A stale URL must not prevent checking the remaining candidates.
        with suppress(ValueError):
            candidates.setdefault(normalize_base_url(url), key or None)

    for prefix in ("PROMPT_PIPER_LOCAL", "PROMPT_PIPER_CLARIFICATION"):
        if url := settings.get(f"{prefix}_BASE_URL"):
            add(url, settings.get(f"{prefix}_API_KEY"))
    for url in settings.get("PROMPT_PIPER_DISCOVERY_URLS", "").split(","):
        if url.strip():
            add(url)
    for host in ("127.0.0.1", "[::1]"):
        for port in DEFAULT_PORTS:
            add(f"http://{host}:{port}/v1")

    def probe(item: tuple[str, str | None]) -> ModelEndpoint | None:
        return probe_endpoint(*item)

    with ThreadPoolExecutor(max_workers=8) as pool:
        return [
            endpoint for endpoint in pool.map(probe, candidates.items()) if endpoint is not None
        ]


def port_is_listening(base_url: str) -> bool:
    """An occupied launch port is unsafe even if model discovery failed."""
    address = urlsplit(base_url)
    try:
        with socket.create_connection(
            (
                address.hostname or "localhost",
                address.port or (443 if address.scheme == "https" else 80),
            ),
            timeout=0.5,
        ):
            return True
    except OSError:
        return False


def local_endpoint_conflict(endpoints: list[ModelEndpoint]) -> str | None:
    local = [endpoint for endpoint in endpoints if is_local_endpoint(endpoint.base_url)]
    if not local:
        return None
    urls = ", ".join(endpoint.base_url for endpoint in local)
    return (
        f"Existing or possibly busy model server detected at {urls}. "
        "Starting another local model could exhaust RAM/VRAM. "
        "Run make setup to reuse an endpoint, choose rule-based/remote mode, "
        "or stop the other server yourself before retrying. No model was started or stopped."
    )

from unittest.mock import Mock

import httpx
import pytest
from prompt_piper.setup import endpoint_discovery as discovery


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("http://localhost:8000/", "http://localhost:8000/v1"),
        ("http://127.0.0.1:8080/v1/", "http://127.0.0.1:8080/v1"),
        ("https://models.test/proxy/v1/", "https://models.test/proxy/v1"),
        ("http://[::1]:8080", "http://[::1]:8080/v1"),
    ],
)
def test_normalize_endpoint(raw, expected):
    assert discovery.normalize_base_url(raw) == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///models",
        "localhost:8080",
        "http://",
        "http://localhost:70000",
        "http://localhost:0",
        "http://name:secret@localhost/v1",
        "http://localhost/v1?key=secret",
        "http://localhost/v1#fragment",
        "http://bad host/v1",
    ],
)
def test_invalid_endpoint_is_rejected(url):
    with pytest.raises(ValueError):
        discovery.normalize_base_url(url)


@pytest.mark.parametrize(
    "payload,models",
    [
        ({"data": [{"id": "maya-model"}]}, ("maya-model",)),
        (
            {"data": [{"id": "org/vllm-model"}, {"id": "org/second"}]},
            ("org/vllm-model", "org/second"),
        ),
        (
            {"data": [{"id": "/models/model.gguf"}, {"id": "/models/model.gguf"}]},
            ("/models/model.gguf",),
        ),
        ({"data": []}, ()),
    ],
)
def test_generic_model_discovery_is_metadata_only(monkeypatch, payload, models):
    calls = []
    client_class = httpx.Client

    def handle(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.path == "/proxy/v1/models"
        assert request.headers["Authorization"] == "Bearer private-key"
        return httpx.Response(200, json=payload)

    def client(**kwargs):
        assert kwargs == {"timeout": 1.0, "follow_redirects": False, "trust_env": False}
        return client_class(transport=httpx.MockTransport(handle), **kwargs)

    monkeypatch.setattr(discovery.httpx, "Client", client)
    result = discovery.probe_endpoint("https://models.test/proxy/v1/", "private-key")
    assert result.models == models
    assert len(calls) == 1
    assert "private-key" not in repr(result)


@pytest.mark.parametrize(
    "status,payload,expected",
    [
        (200, {"status": "ok"}, None),
        (200, [], None),
        (200, {"data": [None, {"id": 42}, {"id": "\x1b[31m"}]}, None),
        (200, {"data": "not-a-list"}, None),
        (404, {}, None),
        (302, {}, None),
        (401, {}, "credentials required"),
        (403, {}, "credentials required"),
        (503, {}, "loading or busy"),
    ],
)
def test_unrelated_and_protected_services(monkeypatch, status, payload, expected):
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **k: httpx.Response(
            status, json=payload, request=httpx.Request("GET", url)
        ),
    )
    result = discovery.probe_endpoint("http://127.0.0.1:8080/v1")
    if expected:
        assert result.status.startswith(expected)
        assert result.models == ()
    else:
        assert result is None


@pytest.mark.parametrize(
    "failure", [httpx.ConnectError("offline"), httpx.ReadTimeout("slow")]
)
def test_unreachable_servers_do_not_break_discovery(monkeypatch, failure):
    monkeypatch.setattr(httpx.Client, "get", Mock(side_effect=failure))
    assert discovery.probe_endpoint("http://127.0.0.1:8080/v1") is None


def test_non_json_service_is_ignored(monkeypatch):
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **k: httpx.Response(
            200, text="<html>Other app</html>", request=httpx.Request("GET", url)
        ),
    )
    assert discovery.probe_endpoint("http://127.0.0.1:8080/v1") is None


def test_discovery_includes_custom_urls_deduplicates_and_scopes_credentials(
    monkeypatch,
):
    monkeypatch.setenv("PROMPT_PIPER_LOCAL_API_KEY", "stale-shell-secret")
    calls = {}

    def probe(url, api_key):
        assert url not in calls
        calls[url] = api_key
        return discovery.ModelEndpoint(url, ("model",), api_key=api_key)

    monkeypatch.setattr(discovery, "probe_endpoint", probe)
    result = discovery.discover_endpoints(
        {
            "PROMPT_PIPER_LOCAL_BASE_URL": "https://models.test/proxy/v1/",
            "PROMPT_PIPER_LOCAL_API_KEY": "primary-secret",
            "PROMPT_PIPER_CLARIFICATION_BASE_URL": "http://127.0.0.1:9000/v1",
            "PROMPT_PIPER_CLARIFICATION_API_KEY": "clarification-secret",
            "PROMPT_PIPER_DISCOVERY_URLS": "http://127.0.0.1:7777,invalid,http://127.0.0.1:8080/v1/",
        }
    )
    assert len(result) == len(discovery.DEFAULT_PORTS) * 2 + 3
    assert calls.pop("https://models.test/proxy/v1") == "primary-secret"
    assert calls.pop("http://127.0.0.1:9000/v1") == "clarification-secret"
    assert "http://127.0.0.1:7777/v1" in calls
    assert "http://[::1]:8000/v1" in calls
    assert all(key is None for key in calls.values())


def test_empty_configured_key_does_not_inherit_shell_secret(monkeypatch):
    monkeypatch.setenv("PROMPT_PIPER_LOCAL_API_KEY", "stale-secret")
    probe = Mock(return_value=None)
    monkeypatch.setattr(discovery, "probe_endpoint", probe)
    discovery.discover_endpoints(
        {
            "PROMPT_PIPER_LOCAL_BASE_URL": "http://127.0.0.1:8080/v1",
            "PROMPT_PIPER_LOCAL_API_KEY": "",
        }
    )
    probe.assert_any_call("http://127.0.0.1:8080/v1", None)


def test_remote_service_does_not_block_local_launch():
    assert (
        discovery.local_endpoint_conflict(
            [discovery.ModelEndpoint("https://models.test/v1", ("remote",))]
        )
        is None
    )
    assert "RAM/VRAM" in discovery.local_endpoint_conflict(
        [discovery.ModelEndpoint("http://127.0.0.1:8000/v1", ("local",))]
    )

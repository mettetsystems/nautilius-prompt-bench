from unittest.mock import Mock

import httpx
import pytest
from prompt_piper.setup import endpoint_discovery, ensure_llm, wizard
from prompt_piper.setup.endpoint_discovery import ModelEndpoint
from prompt_piper.setup.env_writer import load_env


@pytest.fixture
def detected(monkeypatch):
    endpoints = [ModelEndpoint("http://127.0.0.1:8080/v1", ("maya-model",))]
    monkeypatch.setattr(wizard, "discover_endpoints", lambda _: endpoints)
    return endpoints


def run_wizard(env, answers):
    replies = iter(answers)
    return wizard.run_setup_wizard(
        env_path=env, input_fn=lambda _: next(replies), print_fn=lambda _: None
    )


def test_accept_existing_server_skips_hardware_and_download_choices(
    tmp_path, monkeypatch, detected
):
    hardware = Mock(side_effect=AssertionError("must not plan another model"))
    source = Mock(side_effect=AssertionError("must not offer a download"))
    monkeypatch.setattr(wizard, "_run_interactive", hardware)
    monkeypatch.setattr(wizard, "_choose_model_source", source)
    env = tmp_path / ".env"
    env.write_text(
        "CUSTOM_VALUE=keep\nPROMPT_PIPER_LOCAL_API_KEY=old-secret\n"
        "PROMPT_PIPER_LOCAL_MODEL_PATH=old.gguf\n"
        "PROMPT_PIPER_LOCAL_MODEL_GGUF_REPO=old/repo\n"
        "PROMPT_PIPER_LOCAL_MODEL_SOURCE_PATH=/old/model.gguf\n"
        "PROMPT_PIPER_DEPLOYMENT_PROFILE=specification\n"
    )
    result = run_wizard(env, ["", "", ""])
    saved = load_env(env)
    assert result.preset_id == "custom"
    assert saved["PROMPT_PIPER_LOCAL_CHAT_MODEL"] == "maya-model"
    assert saved["PROMPT_PIPER_LOCAL_BASE_URL"] == detected[0].base_url
    assert saved["PROMPT_PIPER_AUTO_START_LLM"] == "false"
    assert saved["PROMPT_PIPER_DEPLOYMENT_PROFILE"] == "manual"
    assert saved["PROMPT_PIPER_LOCAL_API_KEY"] == ""
    assert saved["CUSTOM_VALUE"] == "keep"
    assert "PROMPT_PIPER_LOCAL_MODEL_PATH" not in saved
    assert "PROMPT_PIPER_LOCAL_MODEL_GGUF_REPO" not in saved
    assert "PROMPT_PIPER_LOCAL_MODEL_SOURCE_PATH" not in saved
    assert env.stat().st_mode & 0o777 == 0o600


def test_multiple_endpoints_and_models_with_container_mapping(tmp_path, detected):
    detected.append(
        ModelEndpoint("http://127.0.0.1:8000/proxy/v1", ("first", "second"))
    )
    result = run_wizard(tmp_path / ".env", ["y", "2", "", "2", "2"])
    assert result.chat_model == "second"
    assert result.base_url == "http://host.containers.internal:8000/proxy/v1"


def test_existing_saved_key_is_preserved_without_reprompt(tmp_path, detected):
    detected[0] = ModelEndpoint(
        "https://models.test/v1", ("existing",), api_key="saved-secret"
    )
    env = tmp_path / ".env"
    result = run_wizard(env, ["yes"])
    assert result.api_key == "saved-secret"
    assert load_env(env)["PROMPT_PIPER_LOCAL_API_KEY"] == "saved-secret"


def test_public_models_can_save_a_chat_api_key(tmp_path, detected):
    result = run_wizard(tmp_path / ".env", ["yes", "chat-secret", "1"])
    assert result.api_key == "chat-secret"


@pytest.mark.parametrize("status", ["loading or busy (unverified)", "no models listed"])
def test_busy_or_empty_server_accepts_explicit_model_id(tmp_path, detected, status):
    detected[0] = ModelEndpoint(detected[0].base_url, status=status)
    result = run_wizard(tmp_path / ".env", ["y", "", "resident-model", "1"])
    assert result.preset_id == "custom"
    assert result.chat_model == "resident-model"


def test_discovery_to_saved_configuration_with_mock_http_server(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "PROMPT_PIPER_LOCAL_BASE_URL=http://127.0.0.1:9001/proxy/v1\n"
        "PROMPT_PIPER_LOCAL_API_KEY=saved-key\n"
    )
    requests = []
    client_class = httpx.Client

    def handle(request):
        requests.append(request)
        assert request.method == "GET"
        if request.url.port == 9001:
            assert request.url.path == "/proxy/v1/models"
            assert request.headers["Authorization"] == "Bearer saved-key"
            return httpx.Response(200, json={"data": [{"id": "Resident-Model"}]})
        assert "Authorization" not in request.headers
        raise httpx.ConnectError("No listener", request=request)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handle), **kwargs),
    )
    monkeypatch.setattr(
        wizard, "discover_endpoints", endpoint_discovery.discover_endpoints
    )
    result = run_wizard(env, ["y", "1"])
    assert requests
    assert result.chat_model == "Resident-Model"
    saved = load_env(env)
    assert saved["PROMPT_PIPER_AUTO_START_LLM"] == "false"
    assert saved["PROMPT_PIPER_LOCAL_API_KEY"] == "saved-key"
    assert saved["PROMPT_PIPER_LOCAL_BASE_URL"] == "http://127.0.0.1:9001/proxy/v1"


def test_protected_server_prompts_for_key_before_model_selection(
    tmp_path, monkeypatch, detected
):
    detected[0] = ModelEndpoint(
        detected[0].base_url, status="credentials required (unverified)"
    )
    probe = Mock(
        return_value=ModelEndpoint(
            detected[0].base_url, ("protected",), api_key="new-key"
        )
    )
    monkeypatch.setattr(wizard, "probe_endpoint", probe)
    result = run_wizard(tmp_path / ".env", ["y", "new-key", "1"])
    probe.assert_called_once_with(detected[0].base_url, "new-key")
    assert result.api_key == "new-key"
    assert result.chat_model == "protected"


def test_bad_credentials_leave_configuration_untouched(tmp_path, monkeypatch, detected):
    detected[0] = ModelEndpoint(
        detected[0].base_url, status="credentials required (unverified)"
    )
    monkeypatch.setattr(wizard, "probe_endpoint", lambda *a: detected[0])
    env = tmp_path / ".env"
    env.write_text("CUSTOM_VALUE=keep\n")
    with pytest.raises(ValueError, match="API key"):
        run_wizard(env, ["y", "bad-key"])
    assert env.read_text() == "CUSTOM_VALUE=keep\n"


def test_declining_reuse_can_choose_rule_based_mode(tmp_path, detected):
    result = run_wizard(tmp_path / ".env", ["n", "0"])
    assert result.cpu_only


def test_declining_reuse_cannot_launch_another_local_model(
    tmp_path, monkeypatch, detected
):
    monkeypatch.setattr(
        wizard,
        "_run_interactive",
        lambda *a: wizard._resolve_non_interactive("gemma3-1b"),
    )
    monkeypatch.setattr(
        wizard, "_choose_model_source", Mock(side_effect=AssertionError("download"))
    )
    env = tmp_path / ".env"
    env.write_text("CUSTOM_VALUE=keep\n")
    with pytest.raises(ValueError, match="Starting another local model"):
        run_wizard(env, ["n"])
    assert env.read_text() == "CUSTOM_VALUE=keep\n"


def test_non_interactive_setup_fails_before_changing_existing_configuration(
    tmp_path, detected
):
    env = tmp_path / ".env"
    env.write_text("CUSTOM_VALUE=keep\n")
    with pytest.raises(ValueError, match="reuse an endpoint"):
        wizard.run_setup_wizard(
            env_path=env, non_interactive="gemma3-1b", print_fn=lambda _: None
        )
    assert env.read_text() == "CUSTOM_VALUE=keep\n"


def test_custom_nonstandard_url_uses_discovered_model(tmp_path, monkeypatch):
    monkeypatch.setattr(
        wizard, "probe_endpoint", lambda url, key: ModelEndpoint(url, ("custom",))
    )
    result = run_wizard(tmp_path / ".env", ["4", "http://127.0.0.1:7777", ""])
    assert result.base_url == "http://127.0.0.1:7777/v1"
    assert result.chat_model == "custom"


@pytest.mark.parametrize(
    "status",
    ["available", "credentials required (unverified)", "loading or busy (unverified)"],
)
def test_startup_blocks_other_servers_without_starting_or_stopping_anything(
    tmp_path, monkeypatch, status
):
    env = tmp_path / ".env"
    env.write_text("PROMPT_PIPER_LLM_ENABLED=true\nPROMPT_PIPER_AUTO_START_LLM=true\n")
    monkeypatch.setattr(ensure_llm, "is_server_healthy", lambda *a: False)
    monkeypatch.setattr(
        ensure_llm,
        "discover_endpoints",
        lambda _: [ModelEndpoint("http://127.0.0.1:8000/v1", status=status)],
    )
    for name in ("start_server", "stop_managed_server", "probe_inference"):
        monkeypatch.setattr(ensure_llm, name, Mock(side_effect=AssertionError(name)))
    assert ensure_llm.main(["--env-file", str(env), "--strict"]) == 1
    assert ensure_llm.ensure_local_llm(env).mode == "blocked"


def test_startup_blocks_an_occupied_unrecognized_launch_port(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("PROMPT_PIPER_AUTO_START_LLM=true\n")
    monkeypatch.setattr(ensure_llm, "is_server_healthy", lambda *a: False)
    monkeypatch.setattr(ensure_llm, "port_is_listening", lambda _: True)
    monkeypatch.setattr(
        ensure_llm, "start_server", Mock(side_effect=AssertionError("start"))
    )
    result = ensure_llm.ensure_local_llm(env)
    assert result.mode == "blocked"
    assert "already occupied" in result.message


@pytest.mark.parametrize("ok", [True, False])
def test_custom_endpoint_never_launches_even_when_unavailable(
    tmp_path, monkeypatch, ok
):
    env = tmp_path / ".env"
    env.write_text(
        "PROMPT_PIPER_LLM_ENABLED=true\nPROMPT_PIPER_LOCAL_MODEL_PRESET=custom\n"
        "PROMPT_PIPER_AUTO_START_LLM=true\nPROMPT_PIPER_LOCAL_API_KEY=''\n"
    )
    monkeypatch.setenv("PROMPT_PIPER_LOCAL_API_KEY", "stale-secret")
    probe = Mock(return_value=(ok, "ready" if ok else "offline"))
    monkeypatch.setattr(ensure_llm, "probe_inference", probe)
    monkeypatch.setattr(
        ensure_llm, "start_server", Mock(side_effect=AssertionError("start"))
    )
    result = ensure_llm.ensure_local_llm(env)
    assert result.llm_enabled is ok
    assert probe.call_args.args[2] == ""


def test_auth_or_loading_at_target_is_verified_without_a_second_launch(
    tmp_path, monkeypatch
):
    env = tmp_path / ".env"
    env.write_text("PROMPT_PIPER_AUTO_START_LLM=true\n")
    monkeypatch.setattr(ensure_llm, "is_server_healthy", lambda *a: False)
    monkeypatch.setattr(
        ensure_llm,
        "discover_endpoints",
        lambda _: [
            ModelEndpoint(
                "http://127.0.0.1:8080/v1", status="credentials required (unverified)"
            )
        ],
    )
    monkeypatch.setattr(
        ensure_llm, "probe_inference", lambda *a, **k: (False, "needs credentials")
    )
    monkeypatch.setattr(
        ensure_llm, "start_server", Mock(side_effect=AssertionError("start"))
    )
    result = ensure_llm.ensure_local_llm(env)
    assert not result.llm_enabled
    assert result.message == "needs credentials"

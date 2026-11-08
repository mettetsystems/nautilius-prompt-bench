import os
import shlex
import subprocess
from unittest.mock import Mock

import pytest
from prompt_piper.setup import ensure_llm, preferred_endpoint
from prompt_piper.setup.endpoint_discovery import ModelEndpoint
from prompt_piper.setup.preferred_endpoint import (
    MAYA_BASE_URL,
    PreferredEndpointUnavailable,
    select_preferred_endpoint,
)
from prompt_piper_api.config import Settings, get_settings


@pytest.fixture
def maya(monkeypatch):
    probe = Mock(return_value=ModelEndpoint(MAYA_BASE_URL, ("maya-resident-model",)))
    monkeypatch.setattr(preferred_endpoint, "probe_endpoint", probe)
    return probe


def test_default_probe_uses_maya_and_advertised_model(maya):
    selected = select_preferred_endpoint(
        {"PROMPT_PIPER_LOCAL_CHAT_MODEL": "stale-llama"}
    )
    maya.assert_called_once_with(MAYA_BASE_URL, None)
    assert selected.base_url == MAYA_BASE_URL
    assert selected.model == "maya-resident-model"
    assert selected.environment()["PROMPT_PIPER_AUTO_START_LLM"] == "false"
    assert selected.environment()["PROMPT_PIPER_LOCAL_MODEL_PRESET"] == "custom"
    assert selected.environment()["PROMPT_PIPER_DEPLOYMENT_PROFILE"] == "manual"


@pytest.mark.parametrize(
    "config",
    [
        {"PROMPT_PIPER_LLM_ENABLED": "false"},
        {"PROMPT_PIPER_LOCAL_MODEL_PRESET": "cpu-only"},
        {"PROMPT_PIPER_PREFER_MAYA": "false"},
    ],
)
def test_explicit_disable_or_opt_out_skips_probe(maya, config):
    assert select_preferred_endpoint(config) is None
    maya.assert_not_called()


def test_absent_maya_leaves_saved_configuration_alone(maya):
    maya.return_value = None
    assert select_preferred_endpoint({}) is None


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        ModelEndpoint(MAYA_BASE_URL, status="credentials required (unverified)"),
        ModelEndpoint(MAYA_BASE_URL, status="loading or busy (unverified)"),
        ModelEndpoint(MAYA_BASE_URL, status="no models listed"),
    ],
)
def test_occupied_unready_service_blocks_automatic_fallback(
    monkeypatch, maya, endpoint
):
    maya.return_value = endpoint
    monkeypatch.setattr(preferred_endpoint, "port_is_listening", lambda _: True)
    with pytest.raises(
        PreferredEndpointUnavailable, match="No model was started or stopped"
    ):
        select_preferred_endpoint({})


@pytest.mark.parametrize(
    "configured,expected", [("second", "second"), ("stale", "first")]
)
def test_multiple_models_preserve_a_valid_choice_otherwise_use_first(
    maya, configured, expected
):
    maya.return_value = ModelEndpoint(MAYA_BASE_URL, ("first", "second"))
    assert (
        select_preferred_endpoint({"PROMPT_PIPER_LOCAL_CHAT_MODEL": configured}).model
        == expected
    )


@pytest.mark.parametrize(
    "base_url,expected_key",
    [
        (MAYA_BASE_URL, "saved-secret"),
        (MAYA_BASE_URL + "/", "saved-secret"),
        ("https://other-provider.test/v1", None),
        ("http://127.0.0.1:9000/v1", None),
    ],
)
def test_saved_credentials_are_scoped_to_their_endpoint(maya, base_url, expected_key):
    selected = select_preferred_endpoint(
        {
            "PROMPT_PIPER_LOCAL_BASE_URL": base_url,
            "PROMPT_PIPER_LOCAL_API_KEY": "saved-secret",
        }
    )
    maya.assert_called_once_with(MAYA_BASE_URL, expected_key)
    assert selected.api_key == expected_key
    assert "saved-secret" not in repr(selected)


def test_dedicated_maya_credentials_and_container_address(maya):
    base_url = "http://host.containers.internal:8080/v1"
    maya.return_value = ModelEndpoint(base_url, ("resident",))
    selected = select_preferred_endpoint(
        {
            "PROMPT_PIPER_MAYA_BASE_URL": base_url,
            "PROMPT_PIPER_MAYA_API_KEY": "maya-secret",
            "PROMPT_PIPER_LOCAL_BASE_URL": "https://other-provider.test/v1",
            "PROMPT_PIPER_LOCAL_API_KEY": "other-secret",
        }
    )
    maya.assert_called_once_with(base_url, "maya-secret")
    assert selected.environment()["PROMPT_PIPER_LOCAL_API_KEY"] == "maya-secret"


def test_explicit_empty_maya_key_disables_saved_credential_fallback(maya):
    selected = select_preferred_endpoint(
        {
            "PROMPT_PIPER_MAYA_API_KEY": "",
            "PROMPT_PIPER_LOCAL_API_KEY": "saved-secret",
            "PROMPT_PIPER_LOCAL_BASE_URL": MAYA_BASE_URL,
        }
    )
    maya.assert_called_once_with(MAYA_BASE_URL, "")
    assert selected.environment()["PROMPT_PIPER_LOCAL_API_KEY"] == ""


def test_invalid_preferred_url_is_actionable_and_never_probed(maya):
    with pytest.raises(
        PreferredEndpointUnavailable, match="Invalid PROMPT_PIPER_MAYA_BASE_URL"
    ):
        select_preferred_endpoint({"PROMPT_PIPER_MAYA_BASE_URL": "file:///models"})
    maya.assert_not_called()


def test_ensure_selects_maya_before_gpu_checks_and_preserves_env_file(
    tmp_path, monkeypatch, maya
):
    env = tmp_path / ".env"
    original = (
        "PROMPT_PIPER_LLM_ENABLED=true\nPROMPT_PIPER_LOCAL_CHAT_MODEL=old-model\n"
        "PROMPT_PIPER_LOCAL_MODEL_PRESET=qwen3-14b\n"
        "PROMPT_PIPER_DEPLOYMENT_PROFILE=specification\n"
        "PROMPT_PIPER_LOCAL_BASE_URL=https://saved-provider.test/v1\n"
        "PROMPT_PIPER_LOCAL_API_KEY=saved-provider-key\nPROMPT_PIPER_AUTO_START_LLM=true\n"
    )
    env.write_text(original)
    for name in (
        "detect_gpu",
        "start_server",
        "stop_managed_server",
        "probe_specification_context",
    ):
        monkeypatch.setattr(ensure_llm, name, Mock(side_effect=AssertionError(name)))
    inference = Mock(return_value=(True, "ready"))
    monkeypatch.setattr(ensure_llm, "probe_inference", inference)
    result = ensure_llm.ensure_local_llm(env)
    inference.assert_called_once_with(
        MAYA_BASE_URL, "maya-resident-model", None, wait_seconds=300
    )
    assert result.mode == "already_running"
    assert result.llm_enabled
    assert "preferred Maya-compatible" in result.message
    assert env.read_text() == original
    assert os.environ["PROMPT_PIPER_LOCAL_CHAT_MODEL"] == "maya-resident-model"
    assert os.environ["PROMPT_PIPER_LOCAL_API_KEY"] == ""


def test_maya_inference_failure_is_fatal_without_launching_replacement(
    tmp_path, monkeypatch, maya
):
    env = tmp_path / ".env"
    env.write_text("PROMPT_PIPER_LLM_ENABLED=true\n")
    monkeypatch.setattr(
        ensure_llm, "probe_inference", lambda *a, **k: (False, "unavailable")
    )
    monkeypatch.setattr(
        ensure_llm, "start_server", Mock(side_effect=AssertionError("launch"))
    )
    assert ensure_llm.main(["--env-file", str(env), "--strict", "--shell"]) == 1


def test_auth_error_stops_strict_startup_before_inference(tmp_path, monkeypatch, maya):
    maya.return_value = ModelEndpoint(
        MAYA_BASE_URL, status="credentials required (unverified)"
    )
    env = tmp_path / ".env"
    env.write_text("PROMPT_PIPER_LLM_ENABLED=true\n")
    for name in ("probe_inference", "start_server", "stop_managed_server"):
        monkeypatch.setattr(ensure_llm, name, Mock(side_effect=AssertionError(name)))
    assert ensure_llm.main(["--env-file", str(env), "--strict"]) == 1


def test_shell_exports_preserve_model_and_key_as_literal_data(tmp_path):
    marker = tmp_path / "must-not-be-created"
    model = f"model $(touch {shlex.quote(str(marker))}) `echo unsafe` 'name'"
    selected = preferred_endpoint.PreferredEndpoint(
        MAYA_BASE_URL, model, "key'$;literal"
    )
    result = ensure_llm.EnsureLlmResult(
        "already_running", True, "ready", selected.environment()
    )
    script = (
        ensure_llm.shell_export(result)
        + '\nprintf "%s\\n%s\\n%s\\n" "$PROMPT_PIPER_LOCAL_CHAT_MODEL" "$PROMPT_PIPER_LOCAL_API_KEY" "$PROMPT_PIPER_AUTO_START_LLM"'
    )
    completed = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=True
    )
    assert completed.stdout.splitlines() == [model, "key'$;literal", "false"]
    assert not marker.exists()


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "PROMPT_PIPER_LLM_ENABLED=true\nPROMPT_PIPER_LOCAL_CHAT_MODEL=old-model\n"
        "PROMPT_PIPER_LOCAL_BASE_URL=http://127.0.0.1:9000/v1\n"
        "PROMPT_PIPER_LOCAL_API_KEY=old-secret\n"
        "PROMPT_PIPER_LOCAL_MODEL_PRESET=qwen3-14b\n"
        "PROMPT_PIPER_DEPLOYMENT_PROFILE=specification\n"
    )
    monkeypatch.setitem(Settings.model_config, "env_file", env)
    get_settings.cache_clear()
    return env


@pytest.mark.asyncio
async def test_api_lifespan_applies_maya_before_serving_and_clears_cached_client(
    isolated_settings, monkeypatch, maya
):
    from prompt_piper_api import main
    from prompt_piper_api.llm.factory import (
        clear_llm_client_cache,
        get_default_llm_client,
        load_local_chat_settings,
    )

    original = isolated_settings.read_text()
    clear_llm_client_cache()
    old_client = get_default_llm_client()
    assert load_local_chat_settings().model_name == "old-model"
    monkeypatch.setattr(main, "init_db", lambda: None)
    async with main.lifespan(main.app):
        effective = load_local_chat_settings()
        assert effective.base_url == MAYA_BASE_URL
        assert effective.model_name == "maya-resident-model"
        assert not effective.api_key
        assert get_default_llm_client() is not old_client
        assert get_settings().prompt_piper_local_model_preset == "custom"
        assert get_settings().prompt_piper_deployment_profile == "manual"
    assert isolated_settings.read_text() == original
    clear_llm_client_cache()


def test_direct_api_startup_falls_back_when_maya_is_absent(isolated_settings):
    from prompt_piper_api.services.model_startup import configure_preferred_endpoint

    configure_preferred_endpoint()
    assert get_settings().prompt_piper_local_chat_model == "old-model"
    assert get_settings().prompt_piper_local_base_url == "http://127.0.0.1:9000/v1"


def test_direct_api_respects_opt_out(isolated_settings, monkeypatch, maya):
    from prompt_piper_api.services.model_startup import configure_preferred_endpoint

    monkeypatch.setenv("PROMPT_PIPER_PREFER_MAYA", "false")
    get_settings.cache_clear()
    configure_preferred_endpoint()
    maya.assert_not_called()
    assert get_settings().prompt_piper_local_chat_model == "old-model"


def test_explicit_ui_endpoint_still_overrides_the_default(isolated_settings, maya):
    from prompt_piper_api.domain.user_settings import AiToolingApiOverride, UserSettings
    from prompt_piper_api.llm.factory import load_local_chat_settings
    from prompt_piper_api.services.model_startup import configure_preferred_endpoint
    from prompt_piper_api.services.user_settings_service import (
        get_user_settings_service,
    )

    get_user_settings_service().save(
        UserSettings(
            ai_tooling_api_override=AiToolingApiOverride(
                enabled=True,
                base_url="https://chosen-provider.test/v1",
                chat_model="chosen-model",
            )
        )
    )
    configure_preferred_endpoint()
    assert get_settings().prompt_piper_local_chat_model == "maya-resident-model"
    assert load_local_chat_settings().model_name == "chosen-model"

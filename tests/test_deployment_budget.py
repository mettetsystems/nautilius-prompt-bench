from pathlib import Path
from unittest.mock import patch

import pytest
from prompt_piper.setup.catalog import ALL_PRESETS
from prompt_piper.setup.deployment_budget import SPECIFICATION, Workload, memory_plan
from prompt_piper.setup.gpu_detect import GpuInfo
from prompt_piper.setup.hardware import recommendations
from prompt_piper.setup.llama_launcher import build_server_config, llama_command


def test_weights_that_fit_do_not_imply_a_specification_fit():
    gpu = GpuInfo("nvidia", "32 GiB", 32768, 32000)
    report = recommendations([gpu], gpu, 48000)
    high = report["local_options"][2]
    assert high["memory_plan"]["weights_mb"] < gpu.free_vram_mb
    assert high["memory_plan"]["required_vram_mb"] > gpu.free_vram_mb
    assert high["status"] == "unavailable"
    assert report["recommended"] == "mid"
    assert report["local_options"][1]["preset"] == "qwen3-14b"
    assert report["workload"]["input_tokens"] == 24576
    assert report["workload"]["output_tokens"] == 8192


def test_cache_uses_architecture_and_total_context_once():
    assert memory_plan("qwen3-14b")["kv_cache_mb"] == 5120
    assert memory_plan("deepseek-r1-32b")["kv_cache_mb"] == 8192
    two = memory_plan("qwen3-14b", workload=Workload(parallel_requests=2))
    assert two["kv_cache_mb"] == 10240
    assert two["runtime_mb"] == 2048
    assert two["weights_mb"] == memory_plan("qwen3-14b")["weights_mb"]
    assert not memory_plan("qwen3-14b", workload=Workload(context_tokens=65536))[
        "context_supported"
    ]


@pytest.mark.parametrize(
    "workload", [{"output_tokens": 32768}, {"parallel_requests": 0}]
)
def test_invalid_workload_rejected(workload):
    with pytest.raises(ValueError):
        Workload(**workload)


def test_free_memory_and_ram_both_constrain_selection():
    gpu = GpuInfo("nvidia", "32 GiB", 32768, 16000)
    report = recommendations([gpu], gpu, 48000)
    assert report["local_options"][1]["preset"] == "qwen3-8b"
    assert report["local_options"][1]["memory_plan"]["reserve_mb"] == 4916
    assert recommendations([gpu], gpu, 4000)["recommended"] == "remote"
    gpu = GpuInfo("nvidia", "48 GiB", 49152, 48000)
    assert recommendations([gpu], gpu, 48000)["recommended"] == "high"


@pytest.fixture
def model(tmp_path, monkeypatch):
    for key in (
        "PROMPT_PIPER_LLAMA_N_CTX",
        "PROMPT_PIPER_LLAMA_CONTEXT_SIZE",
        "PROMPT_PIPER_LLAMA_GPU_LAYERS",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        "prompt_piper.setup.hardware.system_memory", lambda: (48000, 64000)
    )
    path = tmp_path / ALL_PRESETS["qwen3-14b"].suggested_gguf_filename
    path.write_bytes(b"GGUF")
    return path


def config(model, free=30000, **kwargs):
    return build_server_config(
        model_path=model,
        binary=Path("/llama-server"),
        gpu=GpuInfo("nvidia", "32 GiB", 32768, free),
        deployment_profile="specification",
        preset_id="qwen3-14b",
        **kwargs,
    )


def test_launcher_keeps_planned_context_and_one_slot(model):
    settings = config(model)
    assert settings.context_size == SPECIFICATION.context_tokens
    assert settings.gpu_layers == 999
    command = llama_command(settings)
    for flag, value in [
        ("--parallel", "1"),
        ("--cache-type-k", "f16"),
        ("--cache-type-v", "f16"),
        ("--n-predict", "8192"),
    ]:
        assert command[command.index(flag) + 1] == value
    assert "--no-context-shift" in command


@pytest.mark.parametrize("free", [None, 10000, 18000])
def test_launcher_rejects_insufficient_or_unknown_free_vram(model, free):
    with pytest.raises(ValueError, match="will not be reduced"):
        config(model, free=free)


def test_launcher_does_not_silently_override_conflicting_tuning(model):
    with pytest.raises(ValueError, match="32768"):
        config(model, context_size=4096)
    with pytest.raises(ValueError, match="full offload"):
        config(model, gpu_layers=20)


def test_actual_model_size_is_checked(model):
    with model.open("wb") as stream:
        stream.truncate(25 * 1024**3)
    with pytest.raises(ValueError, match="free VRAM"):
        config(model)


def test_custom_gguf_cannot_inherit_unrelated_architecture(model):
    different = model.with_name("custom.gguf")
    model.rename(different)
    with pytest.raises(ValueError, match="catalog GGUF"):
        config(different)


def test_cpu_path_preserves_context_and_checks_available_ram(model, monkeypatch):
    settings = config(model, free=1000, cpu_only=True)
    assert settings.context_size == 32768
    assert settings.gpu_layers == 0
    monkeypatch.setattr(
        "prompt_piper.setup.hardware.system_memory", lambda: (8000, 64000)
    )
    with pytest.raises(ValueError, match="available RAM"):
        config(model, cpu_only=True)


def test_local_client_uses_output_reserve_without_changing_manual_defaults(tmp_path):
    from prompt_piper_api.config import Settings
    from prompt_piper_api.llm.factory import load_local_chat_settings
    from prompt_piper_api.services.user_settings_service import UserSettingsService

    service = UserSettingsService(tmp_path / "settings.json")
    with patch(
        "prompt_piper_api.services.user_settings_service.get_user_settings_service",
        return_value=service,
    ):
        settings = Settings(
            _env_file=None, prompt_piper_deployment_profile="specification"
        )
        assert load_local_chat_settings(settings).max_tokens == 8192
        settings = Settings(_env_file=None, prompt_piper_deployment_profile="manual")
        assert load_local_chat_settings(settings).max_tokens < 8192


@pytest.mark.parametrize(
    "ctx,slots,expected", [(32768, 1, True), (4096, 1, False), (32768, 4, False)]
)
def test_readiness_checks_served_context(monkeypatch, ctx, slots, expected):
    import httpx
    from prompt_piper.setup.readiness import probe_specification_context

    def get(self, url, **kwargs):
        assert url == "http://localhost:8080/props"
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"default_generation_settings": {"n_ctx": ctx}, "total_slots": slots},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.Client, "get", get)
    assert (
        probe_specification_context("http://localhost:8080/v1", "test-key")[0]
        is expected
    )


def test_ensure_reads_profile_from_env_file_and_blocks_stale_server(
    tmp_path, monkeypatch
):
    from prompt_piper.setup import ensure_llm

    env = tmp_path / ".env"
    env.write_text(
        "PROMPT_PIPER_DEPLOYMENT_PROFILE=specification\nPROMPT_PIPER_LLM_ENABLED=true\n"
    )
    monkeypatch.setattr(ensure_llm, "is_server_healthy", lambda *a, **k: True)
    monkeypatch.setattr(ensure_llm, "probe_inference", lambda *a, **k: (True, "ready"))
    monkeypatch.setattr(
        ensure_llm,
        "probe_specification_context",
        lambda *a, **k: (False, "short context"),
    )
    with patch.object(ensure_llm, "start_server") as start:
        result = ensure_llm.ensure_local_llm(env)
    assert not result.llm_enabled
    assert result.message == "short context"
    start.assert_not_called()


def test_ensure_checks_budget_before_starting_or_stopping_a_model(
    model, tmp_path, monkeypatch
):
    from prompt_piper.setup import ensure_llm

    env = tmp_path / ".env"
    env.write_text(
        "PROMPT_PIPER_DEPLOYMENT_PROFILE=specification\n"
        "PROMPT_PIPER_LLM_ENABLED=true\nPROMPT_PIPER_AUTO_START_LLM=true\n"
        "PROMPT_PIPER_LOCAL_MODEL_PRESET=qwen3-14b\n"
        "PROMPT_PIPER_LOCAL_BASE_URL=http://localhost:8080/v1\n"
    )
    monkeypatch.setattr(ensure_llm, "is_server_healthy", lambda *a, **k: False)
    monkeypatch.setattr(
        ensure_llm, "detect_gpu", lambda: GpuInfo("nvidia", "test", 32768, 12000)
    )
    monkeypatch.setattr(ensure_llm, "resolve_model_path", lambda **k: model)
    monkeypatch.setattr(ensure_llm, "find_llama_server", lambda: Path("/llama-server"))
    monkeypatch.setattr(
        "prompt_piper.setup.llama_launcher.supports_gpu", lambda *a: True
    )
    with (
        patch.object(ensure_llm, "start_server") as start,
        patch.object(ensure_llm, "stop_managed_server") as stop,
    ):
        result = ensure_llm.ensure_local_llm(env)
    assert not result.llm_enabled
    assert "32K specification context needs" in result.message
    start.assert_not_called()
    stop.assert_not_called()


def test_setup_replaces_stale_tuning_without_duplicate_keys(tmp_path):
    from prompt_piper.setup.wizard import SetupResult, _apply_result

    env = tmp_path / ".env"
    env.write_text("PROMPT_PIPER_LLAMA_N_CTX=4096\nPROMPT_PIPER_LLAMA_GPU_LAYERS=20\n")
    _apply_result(
        env,
        SetupResult(
            False,
            "qwen3-14b",
            "http://localhost:8080/v1",
            "qwen3-14b",
            None,
            env,
            deployment_profile="specification",
        ),
    )
    text = env.read_text()
    assert text.count("PROMPT_PIPER_LLAMA_N_CTX=") == 1
    assert "PROMPT_PIPER_LLAMA_N_CTX=32768" in text
    assert "PROMPT_PIPER_LLAMA_GPU_LAYERS=999" in text

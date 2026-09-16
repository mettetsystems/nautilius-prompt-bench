from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from prompt_piper.setup.ensure_llm import (
    EnsureLlmResult,
    ensure_local_llm,
    shell_export,
)
from prompt_piper.setup.llama_launcher import (
    pid_file_path,
    resolve_model_path,
    stop_managed_server,
)


def test_resolve_model_path_prefers_existing_gguf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models = tmp_path / "data" / "models"
    models.mkdir(parents=True)
    model = models / "google_gemma-3-1b-it-Q4_K_M.gguf"
    model.write_bytes(b"gguf")

    monkeypatch.setattr("prompt_piper.setup.llama_launcher.repo_root", lambda: tmp_path)

    resolved = resolve_model_path(
        configured_path="./data/models/missing.gguf",
        preset_id="gemma3-1b",
    )
    assert resolved == model.resolve()


def test_ensure_local_llm_cpu_only_without_gpu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PROMPT_PIPER_LLM_ENABLED=true\n"
        "PROMPT_PIPER_LOCAL_MODEL_PRESET=gemma3-1b\n"
        "PROMPT_PIPER_LOCAL_BASE_URL=http://127.0.0.1:8080/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.repo_root", lambda: tmp_path)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.detect_gpu", lambda: None)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.is_server_healthy", lambda *_args, **_kwargs: False)

    result = ensure_local_llm(env_path)
    assert result.mode == "cpu_only"
    assert result.llm_enabled is False
    assert "No compatible GPU" in result.message
    assert "PROMPT_PIPER_ALLOW_CPU_LLM=true" in result.message


def test_ensure_local_llm_skips_cpu_only_preset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("PROMPT_PIPER_LOCAL_MODEL_PRESET=cpu-only\n", encoding="utf-8")
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.repo_root", lambda: tmp_path)

    result = ensure_local_llm(env_path)
    assert result.mode == "skipped"
    assert result.llm_enabled is False


def test_ensure_local_llm_uses_running_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PROMPT_PIPER_LLM_ENABLED=true\n"
        "PROMPT_PIPER_LOCAL_MODEL_PRESET=gemma3-1b\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.repo_root", lambda: tmp_path)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.is_server_healthy", lambda *_args, **_kwargs: True)

    monkeypatch.setattr("prompt_piper.setup.ensure_llm.probe_inference", lambda *_a, **_k: (True, "ready"))
    result = ensure_local_llm(env_path)
    assert result.mode == "already_running"
    assert result.llm_enabled is True


def test_shell_export() -> None:
    enabled = shell_export(EnsureLlmResult(mode="gpu", llm_enabled=True, message="ok"))
    disabled = shell_export(EnsureLlmResult(mode="cpu_only", llm_enabled=False, message="ok"))
    assert enabled == "export PROMPT_PIPER_LLM_ENABLED=true"
    assert disabled == "export PROMPT_PIPER_LLM_ENABLED=false"


def test_detect_gpu_returns_none_without_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_piper.setup.gpu_detect import detect_gpu

    monkeypatch.setattr("prompt_piper.setup.gpu_detect.shutil.which", lambda _name: None)
    monkeypatch.setattr("prompt_piper.setup.gpu_detect._amd_devices_present", lambda: False)
    assert detect_gpu() is None


def test_detect_gpu_nvidia(monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_piper.setup.gpu_detect import detect_gpu

    monkeypatch.setattr(
        "prompt_piper.setup.gpu_detect.shutil.which",
        lambda name: "/usr/bin/nvidia-smi" if name == "nvidia-smi" else None,
    )

    class Completed:
        stdout = "NVIDIA GeForce RTX 4090, 24564, 22000\n"

        returncode = 0

    monkeypatch.setattr("prompt_piper.setup.gpu_detect.subprocess.run", lambda *args, **kwargs: Completed())
    gpu = detect_gpu()
    assert gpu is not None
    assert gpu.vendor == "nvidia"
    assert gpu.vram_mb == 24564
    assert gpu.free_vram_mb == 22000


def test_tune_llama_resources_respects_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_piper.setup.llama_launcher import tune_llama_resources

    monkeypatch.setenv("PROMPT_PIPER_LLAMA_N_CTX", "1536")
    monkeypatch.setenv("PROMPT_PIPER_LLAMA_GPU_LAYERS", "12")
    ctx, ngl = tune_llama_resources(vram_mb=8192, free_vram_mb=7000)
    assert ctx == 1536
    assert ngl == 12


def test_tune_llama_resources_cpu_only_forces_zero_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_piper.setup.llama_launcher import tune_llama_resources

    monkeypatch.delenv("PROMPT_PIPER_LLAMA_GPU_LAYERS", raising=False)
    monkeypatch.delenv("PROMPT_PIPER_LLAMA_N_CTX", raising=False)
    ctx, ngl = tune_llama_resources(vram_mb=None, cpu_only=True)
    assert ctx == 2048
    assert ngl == 0


def test_tune_llama_resources_shrinks_ctx_on_tiny_vram(monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_piper.setup.llama_launcher import tune_llama_resources

    monkeypatch.delenv("PROMPT_PIPER_LLAMA_GPU_LAYERS", raising=False)
    monkeypatch.delenv("PROMPT_PIPER_LLAMA_N_CTX", raising=False)
    ctx, ngl = tune_llama_resources(vram_mb=2048, free_vram_mb=1800)
    assert ctx == 2048
    assert ngl == 999


def test_ensure_local_llm_cpu_path_when_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PROMPT_PIPER_LLM_ENABLED=true\n"
        "PROMPT_PIPER_ALLOW_CPU_LLM=true\n"
        "PROMPT_PIPER_LOCAL_MODEL_PRESET=qwen3-0.6b\n"
        "PROMPT_PIPER_LOCAL_BASE_URL=http://127.0.0.1:8080/v1\n",
        encoding="utf-8",
    )
    models = tmp_path / "data" / "models"
    models.mkdir(parents=True)
    model = models / "Qwen3-0.6B-Q8_0.gguf"
    model.write_bytes(b"gguf")
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    monkeypatch.setattr("prompt_piper.setup.ensure_llm.repo_root", lambda: tmp_path)
    monkeypatch.setattr("prompt_piper.setup.llama_launcher.repo_root", lambda: tmp_path)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.detect_gpu", lambda: None)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.is_server_healthy", lambda *_a, **_k: False)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.find_llama_server", lambda: binary)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.read_managed_pid", lambda: None)

    class FakeProcess:
        def poll(self) -> None:
            return None

    started: dict[str, object] = {}

    def fake_start(config, *, log_path=None):  # type: ignore[no-untyped-def]
        started["config"] = config
        return FakeProcess()

    monkeypatch.setattr("prompt_piper.setup.ensure_llm.start_server", fake_start)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.wait_for_server", lambda *_a, **_k: True)

    monkeypatch.setattr("prompt_piper.setup.ensure_llm.probe_inference", lambda *_a, **_k: (True, "ready"))
    result = ensure_local_llm(env_path)
    assert result.mode == "cpu"
    assert result.llm_enabled is True
    assert started["config"].gpu_layers == 0  # type: ignore[attr-defined]
    assert "CPU" in result.message


def test_stop_managed_server_terminates_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("prompt_piper.setup.llama_launcher.repo_root", lambda: tmp_path)
    (tmp_path / "data").mkdir()
    process = subprocess.Popen(["sleep", "60"], start_new_session=True)
    pid_file_path().write_text(str(process.pid), encoding="utf-8")

    assert stop_managed_server() is True
    process.wait(timeout=5)

    assert process.poll() is not None
    assert not pid_file_path().is_file()


def test_repo_root_honors_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from prompt_piper.setup.llama_launcher import repo_root

    monkeypatch.setenv("PROMPT_PIPER_REPO_ROOT", str(tmp_path))
    assert repo_root() == tmp_path.resolve()

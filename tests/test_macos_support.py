"""Apple hardware/backend regressions, runnable without macOS hardware."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from prompt_piper.setup import gpu_detect, llama_launcher


def test_apple_unified_memory_is_not_reported_as_free_vram(monkeypatch):
    monkeypatch.setattr(gpu_detect.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(gpu_detect.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(
        gpu_detect,
        "_run",
        lambda cmd: str(16 * 1024**3) if cmd[-1] == "hw.memsize" else "Apple M3",
    )
    gpu = gpu_detect.detect_gpu()
    assert gpu.vendor == "apple"
    assert gpu.name == "Apple M3"
    assert gpu.vram_mb == 16384
    assert gpu.free_vram_mb is None
    assert gpu.memory_budget_mb == 8192


def test_apple_unknown_memory_uses_small_budget(monkeypatch):
    monkeypatch.setattr(gpu_detect.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(gpu_detect.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(gpu_detect, "_run", lambda cmd: "")
    assert gpu_detect.detect_gpu().memory_budget_mb == 2048


@pytest.mark.parametrize(
    ("vendor", "output", "code", "expected"),
    [
        ("apple", "Metal: Apple M3", 0, True),
        ("apple", "CPU", 0, False),
        ("apple", "Metal: Apple M3", 1, False),
        ("nvidia", "CUDA0: NVIDIA", 0, True),
        ("amd", "ROCm0: AMD", 0, True),
        ("unknown", "Metal", 0, False),
    ],
)
def test_backend_is_verified(monkeypatch, vendor, output, code, expected):
    monkeypatch.setattr(
        llama_launcher.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(stdout=output, returncode=code),
    )
    assert llama_launcher.supports_gpu(Path("/llama-server"), vendor) is expected


def test_apple_tuning_uses_reserved_budget(tmp_path, monkeypatch):
    for key in (
        "PROMPT_PIPER_LLAMA_N_CTX",
        "PROMPT_PIPER_LLAMA_CONTEXT_SIZE",
        "PROMPT_PIPER_LLAMA_GPU_LAYERS",
    ):
        monkeypatch.delenv(key, raising=False)
    model = tmp_path / "large.gguf"
    # Sparse file: demonstrate that total system RAM isn't used as GPU allowance.
    with model.open("wb") as stream:
        stream.truncate(12 * 1024**3)
    gpu = gpu_detect.GpuInfo("apple", "Apple M3", 16384, memory_budget_mb=8192)
    config = llama_launcher.build_server_config(
        model_path=model, binary=Path("/llama-server"), gpu=gpu
    )
    assert 0 < config.gpu_layers < 999
    assert config.vendor == "apple"

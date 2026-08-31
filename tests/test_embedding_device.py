from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from prompt_piper.setup.embedding_device import EmbeddingDeviceDecision, resolve_embedding_device
from prompt_piper.setup.env_writer import upsert_lexicon_env_section
from prompt_piper.setup.gpu_detect import GpuInfo


def test_resolve_embedding_device_without_gpu() -> None:
    with patch("prompt_piper.setup.embedding_device.detect_gpu", return_value=None):
        decision = resolve_embedding_device()
    assert decision.device == "cpu"
    assert "No GPU" in decision.reason


def test_resolve_embedding_device_low_vram_uses_cpu() -> None:
    gpu = GpuInfo(vendor="nvidia", name="NVIDIA GeForce GTX 1050", vram_mb=2048)
    decision = resolve_embedding_device(gpu)
    assert decision.device == "cpu"
    assert "2048MB VRAM" in decision.reason


def test_resolve_embedding_device_uses_pytorch_probe_when_vram_sufficient() -> None:
    gpu = GpuInfo(vendor="nvidia", name="NVIDIA GeForce RTX 4090", vram_mb=24564)
    probe = EmbeddingDeviceDecision("cuda", "RTX 4090 passed PyTorch CUDA embedding probe")
    with patch("prompt_piper.setup.embedding_device._probe_pytorch_cuda", return_value=probe):
        decision = resolve_embedding_device(gpu)
    assert decision.device == "cuda"


def test_resolve_embedding_device_non_nvidia_uses_cpu() -> None:
    gpu = GpuInfo(vendor="amd", name="AMD Radeon RX 7900")
    decision = resolve_embedding_device(gpu)
    assert decision.device == "cpu"
    assert "non-NVIDIA" in decision.reason


def test_upsert_lexicon_env_section_writes_managed_block(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("API_PORT=8000\nPROMPT_PIPER_EMBEDDING_DEVICE=cuda\n", encoding="utf-8")

    upsert_lexicon_env_section(
        env_path,
        {"PROMPT_PIPER_EMBEDDING_DEVICE": "cpu"},
        preamble=("# GTX 1050 uses CPU embeddings",),
    )

    text = env_path.read_text(encoding="utf-8")
    assert "API_PORT=8000" in text
    assert "PROMPT_PIPER_EMBEDDING_DEVICE=cpu" in text
    assert "GTX 1050 uses CPU embeddings" in text
    assert text.count("# --- Precision lexicon (Nautilius Prompting Workbench setup) ---") == 1

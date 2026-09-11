from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

OFFICIAL_HF_PUBLISHERS: frozenset[str] = frozenset({"google", "Qwen"})

# Backward-compatible preset ids from earlier setup wizard releases.
PRESET_ALIASES: dict[str, str] = {
    "qwen3-1.5b": "qwen3-1.7b",
    "qwen3-3b": "qwen3-4b",
    "gemma3-3b": "gemma3-4b",
}


class ModelFamily(StrEnum):
    GEMMA3 = "gemma3"
    GEMMA3N = "gemma3n"
    QWEN3 = "qwen3"
    CUSTOM = "custom"


class ModelTier(StrEnum):
    """VRAM-oriented preset groups shown in the setup wizard."""

    COMPACT = "compact"
    STANDARD = "standard"
    PROSUMER = "prosumer"


@dataclass(frozen=True)
class ModelPreset:
    """Recommended small-language-model preset for llama.cpp or compatible servers."""

    id: str
    family: ModelFamily
    label: str
    size_label: str
    chat_model_name: str
    suggested_gguf_filename: str
    huggingface_gguf_repo: str
    huggingface_gguf_file: str
    publisher: str
    notes: str
    tier: ModelTier = ModelTier.COMPACT
    min_vram_mb: int = 2048
    requires_hf_license: bool = False
    community_gguf: bool = False
    weights_repo: str | None = None


def is_official_hf_repo(repo: str) -> bool:
    """Return True when the repo is published by an official model vendor on Hugging Face."""
    if "/" not in repo:
        return False
    publisher, _ = repo.split("/", 1)
    return publisher in OFFICIAL_HF_PUBLISHERS


def resolve_preset_id(preset_id: str) -> str:
    return PRESET_ALIASES.get(preset_id, preset_id)


def preset_fits_vram(preset: ModelPreset, vram_mb: int | None) -> bool:
    if vram_mb is None:
        return True
    return vram_mb >= preset.min_vram_mb


GEMMA3_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        id="gemma3-1b",
        family=ModelFamily.GEMMA3,
        label="Gemma 3 1B",
        size_label="1B",
        chat_model_name="gemma-3-1b-it-qat-q4_0-gguf",
        suggested_gguf_filename="gemma-3-1b-it-q4_0.gguf",
        huggingface_gguf_repo="google/gemma-3-1b-it-qat-q4_0-gguf",
        huggingface_gguf_file="gemma-3-1b-it-q4_0.gguf",
        publisher="google",
        requires_hf_license=True,
        tier=ModelTier.COMPACT,
        min_vram_mb=2048,
        notes="Official Google QAT GGUF; balanced quality and speed (~2GB VRAM).",
    ),
    ModelPreset(
        id="gemma3-4b",
        family=ModelFamily.GEMMA3,
        label="Gemma 3 4B",
        size_label="4B",
        chat_model_name="gemma-3-4b-it-qat-q4_0-gguf",
        suggested_gguf_filename="gemma-3-4b-it-q4_0.gguf",
        huggingface_gguf_repo="google/gemma-3-4b-it-qat-q4_0-gguf",
        huggingface_gguf_file="gemma-3-4b-it-q4_0.gguf",
        publisher="google",
        requires_hf_license=True,
        tier=ModelTier.STANDARD,
        min_vram_mb=8192,
        notes="Official Google QAT GGUF; ~3–4B class (~8GB+ VRAM recommended).",
    ),
    ModelPreset(
        id="gemma3-12b",
        family=ModelFamily.GEMMA3,
        label="Gemma 3 12B",
        size_label="12B",
        chat_model_name="gemma-3-12b-it-qat-q4_0-gguf",
        suggested_gguf_filename="gemma-3-12b-it-q4_0.gguf",
        huggingface_gguf_repo="google/gemma-3-12b-it-qat-q4_0-gguf",
        huggingface_gguf_file="gemma-3-12b-it-q4_0.gguf",
        publisher="google",
        requires_hf_license=True,
        tier=ModelTier.PROSUMER,
        min_vram_mb=16384,
        notes=(
            "Official Google QAT GGUF; prosumer GPUs (RTX 4090/5080/5090 class, ~16GB+ VRAM). "
            "Google has no official 8B Gemma 3 release — 12B Q4 is the closest prosumer tier."
        ),
    ),
)

GEMMA3N_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        id="gemma3n-e4b",
        family=ModelFamily.GEMMA3N,
        label="Gemma 3n E4B",
        size_label="E4B",
        chat_model_name="google_gemma-3n-E4B-it",
        suggested_gguf_filename="google_gemma-3n-E4B-it-Q4_K_M.gguf",
        huggingface_gguf_repo="bartowski/google_gemma-3n-E4B-it-GGUF",
        huggingface_gguf_file="google_gemma-3n-E4B-it-Q4_K_M.gguf",
        publisher="google",
        requires_hf_license=True,
        tier=ModelTier.STANDARD,
        min_vram_mb=8192,
        community_gguf=True,
        weights_repo="google/gemma-3n-E4B-it",
        notes=(
            "Gemma 3n efficient ~4B-class model; community GGUF from official google/gemma-3n-E4B-it "
            "weights (~8GB+ VRAM). Google QAT GGUF not published yet."
        ),
    ),
)

QWEN3_PRESETS: tuple[ModelPreset, ...] = (
    ModelPreset(
        id="qwen3-0.6b",
        family=ModelFamily.QWEN3,
        label="Qwen3 0.6B",
        size_label="0.6B",
        chat_model_name="qwen3-0.6b",
        suggested_gguf_filename="Qwen3-0.6B-Q8_0.gguf",
        huggingface_gguf_repo="Qwen/Qwen3-0.6B-GGUF",
        huggingface_gguf_file="Qwen3-0.6B-Q8_0.gguf",
        publisher="Qwen",
        tier=ModelTier.COMPACT,
        min_vram_mb=2048,
        notes="Official Qwen GGUF; smallest preset (~640MB), good for 2GB VRAM or CPU.",
    ),
    ModelPreset(
        id="qwen3-1.7b",
        family=ModelFamily.QWEN3,
        label="Qwen3 1.7B",
        size_label="1.7B",
        chat_model_name="qwen3-1.7b",
        suggested_gguf_filename="Qwen3-1.7B-Q8_0.gguf",
        huggingface_gguf_repo="Qwen/Qwen3-1.7B-GGUF",
        huggingface_gguf_file="Qwen3-1.7B-Q8_0.gguf",
        publisher="Qwen",
        tier=ModelTier.COMPACT,
        min_vram_mb=4096,
        notes="Official Qwen GGUF release (closest official size to 1.5B).",
    ),
    ModelPreset(
        id="qwen3-4b",
        family=ModelFamily.QWEN3,
        label="Qwen3 4B",
        size_label="4B",
        chat_model_name="qwen3-4b",
        suggested_gguf_filename="Qwen3-4B-Q4_K_M.gguf",
        huggingface_gguf_repo="Qwen/Qwen3-4B-GGUF",
        huggingface_gguf_file="Qwen3-4B-Q4_K_M.gguf",
        publisher="Qwen",
        tier=ModelTier.STANDARD,
        min_vram_mb=8192,
        notes="Official Qwen GGUF; ~3–4B class (~8GB+ VRAM). Closest official size to 3B.",
    ),
    ModelPreset(
        id="qwen3-8b",
        family=ModelFamily.QWEN3,
        label="Qwen3 8B",
        size_label="8B",
        chat_model_name="qwen3-8b",
        suggested_gguf_filename="Qwen3-8B-Q4_K_M.gguf",
        huggingface_gguf_repo="Qwen/Qwen3-8B-GGUF",
        huggingface_gguf_file="Qwen3-8B-Q4_K_M.gguf",
        publisher="Qwen",
        tier=ModelTier.PROSUMER,
        min_vram_mb=16384,
        notes="Official Qwen GGUF; prosumer GPUs (RTX 4090/5080/5090 class, ~16GB+ VRAM).",
    ),
    ModelPreset(
        id="qwen3-14b",
        family=ModelFamily.QWEN3,
        label="Qwen3 14B — code prompt assistant (RTX 5090)",
        size_label="14B",
        chat_model_name="qwen3-14b",
        suggested_gguf_filename="Qwen3-14B-Q4_K_M.gguf",
        huggingface_gguf_repo="Qwen/Qwen3-14B-GGUF",
        huggingface_gguf_file="Qwen3-14B-Q4_K_M.gguf",
        publisher="Qwen",
        tier=ModelTier.PROSUMER,
        min_vram_mb=16384,
        notes="Larger code prompt assistant; ~9GB download, 16GB+ free VRAM recommended. RTX 5090 suitable; context and other GPU workloads affect memory use.",
    ),
)

ALL_PRESETS: dict[str, ModelPreset] = {
    preset.id: preset for preset in (*GEMMA3_PRESETS, *GEMMA3N_PRESETS, *QWEN3_PRESETS)
}
for alias, target in PRESET_ALIASES.items():
    ALL_PRESETS[alias] = ALL_PRESETS[target]

NATIVE_BASE_URL = "http://127.0.0.1:8080/v1"
PODMAN_BASE_URL = "http://host.containers.internal:8080/v1"

TIER_LABELS: dict[ModelTier, str] = {
    ModelTier.COMPACT: "Compact (0.6B–1.7B; ~2–4GB VRAM)",
    ModelTier.STANDARD: "Standard (~3–4B class; ~8GB+ VRAM)",
    ModelTier.PROSUMER: "Prosumer (~8B+; RTX 4090/5080/5090 class, ~16GB+ VRAM)",
}

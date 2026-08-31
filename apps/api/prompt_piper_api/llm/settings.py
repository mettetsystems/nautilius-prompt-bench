from __future__ import annotations

import re

from pydantic import BaseModel, Field

from prompt_piper_api.llm.enums import ModelProfile, ModelProvider, ModelSizeClass

# Preset id / size_label → size class (catalog-aligned).
_PRESET_SIZE_HINTS: dict[str, ModelSizeClass] = {
    "qwen3-0.6b": ModelSizeClass.TINY,
    "gemma3-1b": ModelSizeClass.SMALL,
    "qwen3-1.7b": ModelSizeClass.SMALL,
    "qwen3-1.5b": ModelSizeClass.SMALL,
    "gemma3-4b": ModelSizeClass.MEDIUM,
    "gemma3-3b": ModelSizeClass.MEDIUM,
    "gemma3n-e4b": ModelSizeClass.MEDIUM,
    "qwen3-4b": ModelSizeClass.MEDIUM,
    "qwen3-3b": ModelSizeClass.MEDIUM,
    "qwen3-8b": ModelSizeClass.LARGE,
    "gemma3-12b": ModelSizeClass.LARGE,
}

_SIZE_TOKEN_RE = re.compile(
    r"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>[bm])\b",
    re.IGNORECASE,
)


class ModelSettings(BaseModel):
    provider: ModelProvider
    base_url: str = Field(description="OpenAI-compatible API base URL, typically ending in /v1.")
    model_name: str
    api_key: str | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)
    enabled: bool = True
    profile: ModelProfile = ModelProfile.COMPATIBILITY
    size_class: ModelSizeClass = ModelSizeClass.MEDIUM


def infer_model_size_class(
    *,
    model_name: str | None = None,
    preset_id: str | None = None,
    size_label: str | None = None,
) -> ModelSizeClass:
    """Infer a size class from preset id, size label, or model name heuristics."""
    if preset_id:
        hinted = _PRESET_SIZE_HINTS.get(preset_id.strip().lower())
        if hinted is not None:
            return hinted
        from prompt_piper.setup.catalog import ALL_PRESETS, resolve_preset_id

        preset = ALL_PRESETS.get(resolve_preset_id(preset_id))
        if preset is not None:
            from_label = _size_class_from_text(preset.size_label)
            if from_label is not None:
                return from_label

    for candidate in (size_label, model_name):
        if not candidate:
            continue
        from_text = _size_class_from_text(candidate)
        if from_text is not None:
            return from_text
    return ModelSizeClass.MEDIUM


def _size_class_from_text(text: str) -> ModelSizeClass | None:
    lowered = text.strip().lower().replace("_", "-")
    match = _SIZE_TOKEN_RE.search(lowered)
    if match is None:
        return None
    value = float(match.group("num"))
    unit = match.group("unit").lower()
    params_b = value if unit == "b" else value / 1000.0
    if params_b <= 0.75:
        return ModelSizeClass.TINY
    if params_b <= 2.0:
        return ModelSizeClass.SMALL
    if params_b <= 6.0:
        return ModelSizeClass.MEDIUM
    return ModelSizeClass.LARGE


def profile_defaults(
    profile: ModelProfile,
    *,
    size_class: ModelSizeClass | None = None,
) -> tuple[float, int]:
    """Return ``(temperature, max_tokens)`` for a profile and optional model size."""
    resolved = size_class or ModelSizeClass.MEDIUM
    if profile is ModelProfile.QUALITY:
        temperature = 0.4
        by_size = {
            ModelSizeClass.TINY: 768,
            ModelSizeClass.SMALL: 1024,
            ModelSizeClass.MEDIUM: 2048,
            ModelSizeClass.LARGE: 3072,
        }
    else:
        temperature = 0.2
        by_size = {
            ModelSizeClass.TINY: 1024,
            ModelSizeClass.SMALL: 1024,
            ModelSizeClass.MEDIUM: 1024,
            ModelSizeClass.LARGE: 1536,
        }
    return temperature, by_size[resolved]

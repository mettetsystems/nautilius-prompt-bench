from enum import StrEnum


class ModelProvider(StrEnum):
    LOCAL_OPENAI_COMPATIBLE = "local_openai_compatible"
    EXTERNAL_OPENAI_COMPATIBLE = "external_openai_compatible"


class ModelProfile(StrEnum):
    COMPATIBILITY = "compatibility"
    QUALITY = "quality"


class ModelSizeClass(StrEnum):
    """Coarse parameter-count bucket used for max_tokens defaults."""

    TINY = "tiny"  # ~0.6B and below
    SMALL = "small"  # ~1B–2B
    MEDIUM = "medium"  # ~3B–4B
    LARGE = "large"  # ~8B+

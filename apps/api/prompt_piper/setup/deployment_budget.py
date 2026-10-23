"""Conservative, single-device budgets for software-specification workloads.

Architecture dimensions come from the upstream model configs linked in
docs/hardware-setup.md. Weight allowances are rounded-up GGUF download sizes,
not measurements of inference allocations. All sizes below are MiB.
"""

from dataclasses import asdict, dataclass
from math import ceil
from pathlib import Path

from prompt_piper.setup.catalog import ALL_PRESETS


@dataclass(frozen=True)
class Workload:
    context_tokens: int = 32768
    output_tokens: int = 8192
    parallel_requests: int = 1

    def __post_init__(self):
        if not 0 < self.output_tokens < self.context_tokens or self.parallel_requests < 1:
            raise ValueError("Output must fit inside context; parallel requests must be positive")

    @property
    def input_tokens(self) -> int:
        return self.context_tokens - self.output_tokens


SPECIFICATION = Workload()


@dataclass(frozen=True)
class ModelMemory:
    weights_mb: int
    layers: int
    kv_heads: int
    head_dim: int
    max_context: int
    min_ram_mb: int


# F16 K and V cache; Q4 weights do not imply a Q4 cache.
MODEL_MEMORY = {
    "qwen3-1.7b": ModelMemory(1800, 28, 8, 128, 32768, 8192),
    "qwen3-8b": ModelMemory(4900, 36, 8, 128, 32768, 12288),
    "qwen3-14b": ModelMemory(8700, 40, 8, 128, 32768, 16384),
    "deepseek-r1-32b": ModelMemory(19000, 64, 8, 128, 131072, 32768),
}


def memory_plan(
    preset_id: str,
    *,
    total_vram_mb: int | None = None,
    weights_mb: int | None = None,
    workload: Workload = SPECIFICATION,
) -> dict:
    model = MODEL_MEMORY[preset_id]
    weights = max(model.weights_mb, weights_mb or 0)
    kv = ceil(
        2
        * model.layers
        * model.kv_heads
        * model.head_dim
        * 2
        * workload.context_tokens
        * workload.parallel_requests
        / 1048576
    )
    runtime = 1024 * workload.parallel_requests
    # Reserve for display, allocator variation and other workloads. Already-used
    # memory is separately excluded by comparing the result with *free* VRAM.
    reserve = max(2048, ceil((total_vram_mb or 0) * 0.15))
    return dict(
        weights_mb=weights,
        kv_cache_mb=kv,
        runtime_mb=runtime,
        reserve_mb=reserve,
        required_vram_mb=weights + kv + runtime + reserve,
        required_ram_mb=max(model.min_ram_mb, weights + kv + runtime + 2048),
        context_supported=workload.context_tokens <= model.max_context,
        cache_type="f16",
    )


def workload_report(workload: Workload = SPECIFICATION) -> dict:
    return dict(
        **asdict(workload),
        input_tokens=workload.input_tokens,
        label="Software specification",
        cache_type="f16",
    )


def plan_model_file(model_path: Path, preset_id: str | None, total_vram_mb=None) -> dict:
    """Plan a catalog artifact, using its actual size if larger than the allowance.

    Arbitrary imports need architecture metadata and must use manual deployment;
    never borrow the selected preset's KV geometry for a different GGUF.
    """
    candidates = [preset_id] if preset_id else MODEL_MEMORY
    for candidate in candidates:
        if candidate in MODEL_MEMORY:
            preset = ALL_PRESETS[candidate]
            if model_path.name == preset.suggested_gguf_filename:
                return memory_plan(
                    candidate,
                    total_vram_mb=total_vram_mb,
                    weights_mb=ceil(model_path.stat().st_size / 1048576),
                )
    raise ValueError(
        "The specification budget supports the listed catalog GGUF filenames only. "
        "Use the matching catalog artifact or Advanced manual deployment for a custom GGUF."
    )

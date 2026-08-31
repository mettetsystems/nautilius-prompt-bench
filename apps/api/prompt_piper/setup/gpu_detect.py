from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class GpuInfo:
    vendor: str
    name: str
    vram_mb: int | None = None
    free_vram_mb: int | None = None


def detect_gpu() -> GpuInfo | None:
    """Return GPU info when a CUDA or ROCm device appears usable."""
    nvidia = _detect_nvidia()
    if nvidia is not None:
        return nvidia
    return _detect_amd_rocm()


def _detect_nvidia() -> GpuInfo | None:
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not line:
        return None
    parts = [part.strip() for part in line.split(",")]
    name = parts[0]
    vram_mb = int(float(parts[1])) if len(parts) > 1 and parts[1] else None
    free_vram_mb = int(float(parts[2])) if len(parts) > 2 and parts[2] else None
    return GpuInfo(vendor="nvidia", name=name, vram_mb=vram_mb, free_vram_mb=free_vram_mb)


def _detect_amd_rocm() -> GpuInfo | None:
    if shutil.which("rocm-smi") is not None:
        try:
            result = subprocess.run(
                ["rocm-smi", "--showproductname"],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
            )
            for raw_line in result.stdout.splitlines():
                line = raw_line.strip()
                if line and "GPU" in line:
                    return GpuInfo(vendor="amd", name=line)
        except (OSError, subprocess.SubprocessError):
            pass
    if not _amd_devices_present():
        return None
    return GpuInfo(vendor="amd", name="AMD GPU (ROCm device nodes present)")


def _amd_devices_present() -> bool:
    from pathlib import Path

    return Path("/dev/kfd").exists() and any(Path("/dev/dri").glob("renderD*"))


def recommended_tier(vram_mb: int | None) -> ModelTier:
    """Pick the highest preset tier likely to fit detected VRAM."""
    from prompt_piper.setup.catalog import ModelTier

    if vram_mb is None:
        return ModelTier.STANDARD
    if vram_mb >= 16384:
        return ModelTier.PROSUMER
    if vram_mb >= 8192:
        return ModelTier.STANDARD
    return ModelTier.COMPACT

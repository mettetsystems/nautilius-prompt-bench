from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prompt_piper.setup.catalog import ModelTier


@dataclass(frozen=True)
class GpuInfo:
    vendor: str
    name: str
    vram_mb: int | None = None
    free_vram_mb: int | None = None
    device_id: str | None = None


def _number(value: str) -> int | None:
    try:
        number = int(float(value))
        return number if number >= 0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def _run(command: list[str]) -> str:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def detect_gpus() -> list[GpuInfo]:
    """Inventory usable NVIDIA/ROCm devices. Unknown memory is never treated as free VRAM."""
    devices = []
    if shutil.which("nvidia-smi"):
        output = _run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,uuid",
                "--format=csv,noheader,nounits",
            ]
        )
        visible = os.getenv("CUDA_VISIBLE_DEVICES")
        for index, row in enumerate(csv.reader(output.splitlines())):
            if len(row) < 3:
                continue
            name, total, free = (part.strip() for part in row[:3])
            device_id = row[3].strip() if len(row) > 3 else None
            if (
                visible is not None
                and str(index) not in visible.split(",")
                and device_id not in visible.split(",")
            ):
                continue
            total_mb, free_mb = _number(total), _number(free)
            if free_mb is not None and total_mb is not None:
                free_mb = min(free_mb, total_mb)
            devices.append(GpuInfo("nvidia", name, total_mb, free_mb, device_id))
    if shutil.which("rocm-smi"):
        output = _run(["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--json"])
        try:
            cards = json.loads(output)
        except (ValueError, TypeError):
            cards = {}
        if isinstance(cards, dict):
            for key, card in cards.items():
                if not isinstance(card, dict):
                    continue
                total = _number(card.get("VRAM Total Memory (B)"))
                used = _number(card.get("VRAM Total Used Memory (B)"))
                name = card.get("Card Series") or card.get("Card model") or key
                devices.append(
                    GpuInfo(
                        "amd",
                        str(name),
                        None if total is None else total // 1048576,
                        None if total is None or used is None else max(0, total - used) // 1048576,
                        key.removeprefix("card") if key.startswith("card") else None,
                    )
                )
    if not devices and _amd_devices_present():
        devices.append(GpuInfo("amd", "AMD device nodes present; driver/memory unverified"))
    return devices


def select_gpu(devices: list[GpuInfo]) -> GpuInfo | None:
    return max(
        devices,
        key=lambda gpu: (
            gpu.free_vram_mb if gpu.free_vram_mb is not None else -1,
            gpu.vram_mb or 0,
        ),
        default=None,
    )


def detect_gpu() -> GpuInfo | None:
    """Select the single device with the most verified available memory."""
    return select_gpu(detect_gpus())


def _amd_devices_present() -> bool:
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

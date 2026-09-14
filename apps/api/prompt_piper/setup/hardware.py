"""Shared, read-only hardware recommendations for setup and the web UI."""

from dataclasses import asdict
from pathlib import Path

from prompt_piper.setup.gpu_detect import detect_gpus, select_gpu


def scan_hardware() -> dict:
    devices = detect_gpus()
    gpu = select_gpu(devices)
    memory = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable"}:
                memory[key] = int(value.split()[0]) // 1024
    except (OSError, ValueError):
        pass
    return recommendations(devices, gpu, memory.get("MemAvailable"), memory.get("MemTotal"))


def recommendations(devices, gpu, available_ram_mb, total_ram_mb=None) -> dict:
    free = gpu.free_vram_mb if gpu else None
    # Mid range adapts to 8 GiB cards rather than presenting 14B as a universal fit.
    mid_large = free is not None and free >= 16384
    entries = [
        ("low", "Low / no GPU · 1B–2B", "qwen3-1.7b", "Qwen3 1.7B Q8_0", 4096, 8192),
        (
            "mid",
            "Mid · 7B–16B",
            "qwen3-14b" if mid_large else "qwen3-8b",
            "Qwen3 14B Q4_K_M" if mid_large else "Qwen3 8B Q4_K_M",
            16384 if mid_large else 6144,
            16384 if mid_large else 12288,
        ),
        (
            "high",
            "High · 17B+",
            "deepseek-r1-32b",
            "DeepSeek-R1-Distill-Qwen-32B Q4_K_M",
            24576,
            32768,
        ),
    ]
    options = []
    for tier, label, preset, model, vram, ram in entries:
        gpu_fit = free is not None and free >= vram
        ram_fit = available_ram_mb is not None and available_ram_mb >= ram
        status = (
            "fits" if gpu_fit and ram_fit else "cpu" if tier == "low" and ram_fit else "unavailable"
        )
        if status == "fits":
            reason = (
                "Estimated fit at modest context; free memory and backend support still matter."
            )
        elif status == "cpu":
            reason = "CPU inference is available but slower; rule-based mode needs no chat model."
        else:
            reason = f"Needs verified free VRAM ≥ {vram // 1024} GiB and available RAM ≥ {ram // 1024} GiB. Use a smaller model, free memory, or choose remote."
        options.append(
            dict(
                id=tier,
                label=label,
                preset=preset,
                model=model,
                min_vram_mb=vram,
                min_ram_mb=ram,
                status=status,
                reason=reason,
            )
        )
    eligible = [o for o in options if o["status"] in {"fits", "cpu"}]
    recommended = eligible[-1]["id"] if eligible else "remote"
    return dict(
        gpus=[asdict(d) for d in devices],
        selected_gpu=asdict(gpu) if gpu else None,
        available_ram_mb=available_ram_mb,
        total_ram_mb=total_ram_mb,
        recommended=recommended,
        local_options=options,
        remote_option=dict(
            id="remote",
            label="Remote OpenAI-compatible endpoint",
            reason="No local model VRAM required. Requests leave this machine; configure URL, model ID and optional API key.",
        ),
        note="Scan reflects this process's visible hardware. Containers may need a host scan. GPU memory is not pooled; model size alone does not guarantee a fit.",
    )


def print_hardware(report: dict, write=print) -> None:
    for gpu in report["gpus"]:
        write(
            f"GPU: {gpu['name']} ({gpu['vendor']}), total {gpu['vram_mb']} MiB, free {gpu['free_vram_mb']} MiB"
        )
    if not report["gpus"]:
        write("No supported GPU detected or driver unavailable.")
    write(f"Available system RAM: {report['available_ram_mb']} MiB")
    for index, option in enumerate(report["local_options"], 1):
        write(
            f"  {index}) {option['label']}: {option['model']} [{option['status']}] — {option['reason']}"
        )
    write("  4) Remote OpenAI-compatible endpoint — no local model GPU required")
    write(f"Recommended: {report['recommended']}. {report['note']}")

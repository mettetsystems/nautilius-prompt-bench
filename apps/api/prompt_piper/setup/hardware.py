"""Shared, read-only hardware recommendations for setup and the web UI."""

from dataclasses import asdict
from pathlib import Path

from prompt_piper.setup.deployment_budget import memory_plan, workload_report
from prompt_piper.setup.gpu_detect import detect_gpus, select_gpu


def scan_hardware() -> dict:
    devices = detect_gpus()
    gpu = select_gpu(devices)
    available, total = system_memory()
    return recommendations(devices, gpu, available, total)


def system_memory() -> tuple[int | None, int | None]:
    memory = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable"}:
                memory[key] = int(value.split()[0]) // 1024
    except (OSError, ValueError):
        pass
    return memory.get("MemAvailable"), memory.get("MemTotal")


def recommendations(devices, gpu, available_ram_mb, total_ram_mb=None) -> dict:
    free = gpu.free_vram_mb if gpu else None
    total = gpu.vram_mb if gpu else None
    large_plan = memory_plan("qwen3-14b", total_vram_mb=total)
    mid_large = (
        free is not None and free >= large_plan["required_vram_mb"]
        and available_ram_mb is not None and available_ram_mb >= large_plan["required_ram_mb"]
    )
    entries = [
        ("low", "Light assistance · 1B–2B", "qwen3-1.7b", "Qwen3 1.7B Q8_0"),
        (
            "mid",
            "Mid · 7B–16B",
            "qwen3-14b" if mid_large else "qwen3-8b",
            "Qwen3 14B Q4_K_M" if mid_large else "Qwen3 8B Q4_K_M",
        ),
        (
            "high",
            "High · 17B+",
            "deepseek-r1-32b",
            "DeepSeek-R1-Distill-Qwen-32B Q4_K_M",
        ),
    ]
    options = []
    for tier, label, preset, model in entries:
        plan = memory_plan(preset, total_vram_mb=total)
        vram, ram = plan["required_vram_mb"], plan["required_ram_mb"]
        gpu_fit = free is not None and free >= vram
        ram_fit = available_ram_mb is not None and available_ram_mb >= ram
        status = (
            "fits" if gpu_fit and ram_fit else "cpu" if tier == "low" and ram_fit else "unavailable"
        )
        if status == "fits":
            reason = (
                "Estimated fit for 32K context with 8K reserved for output and one active request."
            )
        elif status == "cpu":
            reason = "32K context is estimated to fit in RAM on CPU; expect slow generation."
        else:
            reason = (
                f"32K context needs verified free VRAM ≥ {vram / 1024:.1f} GiB "
                f"and available RAM ≥ {ram / 1024:.1f} GiB, including reserves. "
                "Use a smaller model, free memory, or choose remote."
            )
        if tier == "low":
            reason += (
                " Suitable for light assistance; specification quality needs separate evaluation."
            )
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
                memory_plan=plan,
                remaining_vram_mb=free - vram if free is not None else None,
            )
        )
    eligible = [o for o in options if o["status"] == "fits" and o["id"] != "low"]
    recommended = eligible[-1]["id"] if eligible else "remote"
    return dict(
        gpus=[asdict(d) for d in devices],
        selected_gpu=asdict(gpu) if gpu else None,
        available_ram_mb=available_ram_mb,
        total_ram_mb=total_ram_mb,
        recommended=recommended,
        workload=workload_report(),
        local_options=options,
        remote_option=dict(
            id="remote",
            label="Remote OpenAI-compatible endpoint",
            reason=(
                "No local model VRAM required. Requests leave this machine; "
                "configure URL, model ID and optional API key."
            ),
        ),
        note=(
            "Planning estimates, not a measured quality or speed benchmark. Reserve: at least "
            "2 GiB or 15% of device VRAM, plus runtime buffers. GPU memory is not pooled. "
            "Run one model at a time; another resident model needs its own budget. "
            "Scan reflects this process's visible hardware; containers may need a host scan."
        ),
    )


def print_hardware(report: dict, write=print) -> None:
    for gpu in report["gpus"]:
        write(
            f"GPU: {gpu['name']} ({gpu['vendor']}), total {gpu['vram_mb']} MiB, "
            f"free {gpu['free_vram_mb']} MiB"
        )
    if not report["gpus"]:
        write("No supported GPU detected or driver unavailable.")
    write(f"Available system RAM: {report['available_ram_mb']} MiB")
    workload = report["workload"]
    write(
        f"Software specification: {workload['context_tokens']} total tokens = "
        f"{workload['input_tokens']} input + {workload['output_tokens']} output; "
        "one active request, F16 KV cache. "
        "Input includes instructions, history and source material."
    )
    for index, option in enumerate(report["local_options"], 1):
        write(
            f"  {index}) {option['label']}: {option['model']} [{option['status']}] "
            f"— {option['reason']}"
        )
        plan = option["memory_plan"]
        write(
            f"     VRAM MiB: weights {plan['weights_mb']} + KV {plan['kv_cache_mb']} "
            f"+ runtime {plan['runtime_mb']} + reserve {plan['reserve_mb']} "
            f"= {plan['required_vram_mb']}"
        )
    write("  4) Remote OpenAI-compatible endpoint — no local model GPU required")
    write(f"Recommended: {report['recommended']}. {report['note']}")

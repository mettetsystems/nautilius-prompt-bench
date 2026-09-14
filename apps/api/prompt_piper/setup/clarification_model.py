"""Configure an optional dedicated clarification endpoint without allocating GPU memory."""

import re
import shlex
from pathlib import Path

from prompt_piper.setup.gpu_detect import detect_gpu
from prompt_piper.setup.llama_launcher import repo_root

DEFAULT_MODEL = "DeepSeek-R1-Distill-Qwen-32B"


def configure_clarification_model(env_path: Path | None = None, *, read=input, write=print) -> None:
    from prompt_piper.setup.hardware import print_hardware, scan_hardware

    print_hardware(scan_hardware(), write)
    gpu = detect_gpu()
    if gpu is None:
        write("GPU resources could not be verified. No model will be downloaded or launched.")
    else:
        write(f"GPU: {gpu.name}; total VRAM {gpu.vram_mb} MiB; free {gpu.free_vram_mb} MiB.")
    write(
        "Optional dedicated clarification model: 1) "
        "DeepSeek-R1-Distill-Qwen-32B Q4_K_M (large default), 2) Qwen3-14B "
        "Q4_K_M, 3) custom endpoint, 4) lightweight only."
    )
    write(
        "32B Q4_K_M: ~19.85 GB weights; budget at least 24 GiB free VRAM and 32"
        " GiB available RAM for a modest context. Longer contexts need more. "
        "Expect tens of seconds to minutes, not instant replies. 14B Q4_K_M: ~9"
        " GB weights, budget 16 GiB free VRAM. Actual speed depends on hardware"
        " and context."
    )
    choice = read("Clarification model [1/2/3/4, default 1]: ").strip() or "1"
    if choice not in {"1", "2", "3", "4"}:
        raise ValueError("Choose clarification model 1, 2, 3, or 4")
    model = "qwen3-14b" if choice == "2" else DEFAULT_MODEL
    if choice == "3":
        model = read("Model name served by your local OpenAI-compatible endpoint: ").strip()
        if not model:
            raise ValueError("Model name is required")
    endpoint = "http://127.0.0.1:8081/v1"
    if choice != "4":
        endpoint = read(f"Dedicated endpoint [{endpoint}]: ").strip() or endpoint
        from urllib.parse import urlparse

        if urlparse(endpoint).scheme not in {"http", "https"} or not urlparse(endpoint).hostname:
            raise ValueError("Use an http(s) endpoint URL")
    values = {
        "PROMPT_PIPER_CLARIFICATION_ENABLED": "false" if choice == "4" else "true",
        "PROMPT_PIPER_CLARIFICATION_MODEL": model,
        "PROMPT_PIPER_CLARIFICATION_BASE_URL": endpoint,
        "PROMPT_PIPER_CLARIFICATION_TIMEOUT": "180",
    }
    path = env_path or repo_root() / ".env"
    existing = path.read_text() if path.exists() else ""
    lines = [
        line
        for line in existing.splitlines()
        if not any(re.match(rf"^\s*{key}\s*=", line) for key in values)
    ]
    path.write_text("\n".join([*lines, *(f"{k}={shlex.quote(v)}" for k, v in values.items()), ""]))
    write(
        "Configuration saved. Start the chosen endpoint yourself after checking"
        " free GPU memory; restart the API to apply. No model was downloaded or"
        " started."
    )

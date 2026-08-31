from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from prompt_piper.setup.gpu_detect import detect_gpu
from prompt_piper.setup.llama_launcher import (
    build_server_config,
    find_llama_server,
    is_server_healthy,
    read_managed_pid,
    repo_root,
    resolve_model_path,
    server_base_url,
    start_server,
    stop_managed_server,
    wait_for_server,
)

EnsureMode = Literal["gpu", "cpu", "cpu_only", "already_running", "skipped"]


@dataclass(frozen=True)
class EnsureLlmResult:
    mode: EnsureMode
    llm_enabled: bool
    message: str


def _truthy(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _load_env(env_path: Path) -> dict[str, str]:
    if not env_path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _parse_host_port(base_url: str) -> tuple[str, int]:
    without_scheme = base_url.removeprefix("http://").removeprefix("https://")
    host_port = without_scheme.split("/", 1)[0]
    if ":" in host_port:
        host, port_text = host_port.rsplit(":", 1)
        return host, int(port_text)
    return host_port, 8080


def _env_lookup(env: dict[str, str], key: str) -> str | None:
    return env.get(key) or os.getenv(key)


def ensure_local_llm(env_path: Path | None = None) -> EnsureLlmResult:
    root = repo_root()
    env_file = env_path or (root / ".env")
    env = _load_env(env_file)

    auto_start = _truthy(
        env.get("PROMPT_PIPER_AUTO_START_LLM"),
        default=_truthy(os.getenv("PROMPT_PIPER_AUTO_START_LLM"), default=True),
    )
    preset = _env_lookup(env, "PROMPT_PIPER_LOCAL_MODEL_PRESET")
    llm_enabled = _truthy(env.get("PROMPT_PIPER_LLM_ENABLED"), default=True)
    allow_cpu_llm = _truthy(
        env.get("PROMPT_PIPER_ALLOW_CPU_LLM"),
        default=_truthy(os.getenv("PROMPT_PIPER_ALLOW_CPU_LLM"), default=False),
    )

    if preset == "cpu-only" or not llm_enabled:
        os.environ["PROMPT_PIPER_LLM_ENABLED"] = "false"
        return EnsureLlmResult(
            mode="skipped",
            llm_enabled=False,
            message="CPU-only mode configured in .env.",
        )

    if not auto_start:
        return EnsureLlmResult(
            mode="skipped",
            llm_enabled=True,
            message="Auto-start disabled (PROMPT_PIPER_AUTO_START_LLM=false).",
        )

    base_url = env.get("PROMPT_PIPER_LOCAL_BASE_URL") or "http://127.0.0.1:8080/v1"
    host, port = _parse_host_port(base_url)
    openai_base = server_base_url(host, port)

    if is_server_healthy(openai_base):
        os.environ["PROMPT_PIPER_LLM_ENABLED"] = "true"
        return EnsureLlmResult(
            mode="already_running",
            llm_enabled=True,
            message=f"Local model server already reachable at {openai_base}.",
        )

    gpu = detect_gpu()
    cpu_only = gpu is None
    if cpu_only and not allow_cpu_llm:
        os.environ["PROMPT_PIPER_LLM_ENABLED"] = "false"
        return EnsureLlmResult(
            mode="cpu_only",
            llm_enabled=False,
            message=(
                "No compatible GPU detected (CUDA/ROCm). Using rule-based CPU mode. "
                "Install NVIDIA or AMD GPU drivers to enable the local SLM, or set "
                "PROMPT_PIPER_ALLOW_CPU_LLM=true to run llama.cpp on CPU."
            ),
        )

    model_path = resolve_model_path(
        configured_path=env.get("PROMPT_PIPER_LOCAL_MODEL_PATH"),
        preset_id=preset,
    )
    if model_path is None:
        os.environ["PROMPT_PIPER_LLM_ENABLED"] = "false"
        return EnsureLlmResult(
            mode="cpu_only",
            llm_enabled=False,
            message=(
                ("No GGUF model found under data/models/. " if cpu_only else "GPU detected but no GGUF model found under data/models/. ")
                + "Run make setup and download a model, then retry."
            ),
        )

    binary = find_llama_server()
    if binary is None:
        os.environ["PROMPT_PIPER_LLM_ENABLED"] = "false"
        return EnsureLlmResult(
            mode="cpu_only",
            llm_enabled=False,
            message=(
                ("llama-server was not found on PATH. " if cpu_only else "GPU detected but llama-server was not found on PATH. ")
                + "Install llama.cpp or set LLAMA_SERVER=/path/to/llama-server."
            ),
        )

    managed_pid = read_managed_pid()
    if managed_pid is not None:
        stop_managed_server()

    config = build_server_config(
        model_path=model_path,
        binary=binary,
        gpu=gpu,
        host=host,
        port=port,
        cpu_only=cpu_only,
    )
    log_path = root / "data" / "llama-server.log"
    process = start_server(config, log_path=log_path)
    if not wait_for_server(openai_base, process=process):
        stop_managed_server()
        os.environ["PROMPT_PIPER_LLM_ENABLED"] = "false"
        detail = ""
        if log_path.is_file():
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
            if tail:
                detail = " Last log lines: " + " | ".join(tail)
        return EnsureLlmResult(
            mode="cpu_only",
            llm_enabled=False,
            message=(
                f"Failed to start llama-server on {openai_base}.{detail} "
                f"See {log_path}. Falling back to rule-based CPU mode."
            ),
        )

    os.environ["PROMPT_PIPER_LLM_ENABLED"] = "true"
    if cpu_only:
        return EnsureLlmResult(
            mode="cpu",
            llm_enabled=True,
            message=(
                f"Started {binary.name} on CPU (-ngl {config.gpu_layers}, -c {config.context_size}) "
                f"using {model_path.name} at {openai_base}."
            ),
        )

    assert gpu is not None
    return EnsureLlmResult(
        mode="gpu",
        llm_enabled=True,
        message=(
            f"Started {binary.name} with {gpu.vendor.upper()} GPU ({gpu.name}) "
            f"(-ngl {config.gpu_layers}, -c {config.context_size}) "
            f"using {model_path.name} at {openai_base}."
        ),
    )


def shell_export(result: EnsureLlmResult) -> str:
    value = "true" if result.llm_enabled else "false"
    return f'export PROMPT_PIPER_LLM_ENABLED={value}'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect GPU, start llama-server when possible, otherwise enable CPU-only mode.",
    )
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument(
        "--shell",
        action="store_true",
        help="Print shell export statements for PROMPT_PIPER_LLM_ENABLED.",
    )
    parser.add_argument(
        "--stop",
        action="store_true",
        help="Stop a Nautilius-managed llama-server process.",
    )
    args = parser.parse_args(argv)

    if args.stop:
        stopped = stop_managed_server()
        print("Stopped managed llama-server." if stopped else "No managed llama-server running.")
        return 0

    result = ensure_local_llm(args.env_file)
    if args.shell:
        print(result.message, file=sys.stderr)
        print(shell_export(result))
    else:
        print(result.message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

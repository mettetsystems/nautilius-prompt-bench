from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from prompt_piper.setup.readiness import probe_inference
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
        import shlex
        try:
            parts = shlex.split(value.strip())
            values[key.strip()] = parts[0] if len(parts) == 1 else value.strip()
        except ValueError:
            values[key.strip()] = value.strip()
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

    base_url = _env_lookup(env, "PROMPT_PIPER_LOCAL_BASE_URL") or "http://127.0.0.1:8080/v1"
    model = _env_lookup(env, "PROMPT_PIPER_LOCAL_CHAT_MODEL") or "local-model"
    api_key = _env_lookup(env, "PROMPT_PIPER_LOCAL_API_KEY")

    def verify() -> EnsureLlmResult:
        ok, message = probe_inference(base_url, model, api_key, wait_seconds=300)
        os.environ["PROMPT_PIPER_LLM_ENABLED"] = "true" if ok else "false"
        return EnsureLlmResult("already_running", ok, message)

    if not auto_start or is_server_healthy(base_url):
        return verify()

    from urllib.parse import urlsplit
    address = urlsplit(base_url)
    if address.hostname not in {"localhost", "127.0.0.1", "::1"}:
        return verify()  # Never try to bind a server to a remote host.
    host, port = address.hostname, address.port or (443 if address.scheme == "https" else 80)
    openai_base = base_url

    gpu = detect_gpu()
    cpu_only = gpu is None
    if allow_cpu_llm and gpu is not None:
        from prompt_piper.setup.catalog import ALL_PRESETS
        selected = ALL_PRESETS.get(preset or "")
        if selected and (gpu.free_vram_mb is None or gpu.free_vram_mb < selected.min_vram_mb):
            cpu_only = True
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
    # New source-aware selections must never silently start an unrelated old GGUF.
    if env.get("PROMPT_PIPER_LOCAL_MODEL_SOURCE") and env.get("PROMPT_PIPER_LOCAL_MODEL_PATH"):
        expected = Path(env["PROMPT_PIPER_LOCAL_MODEL_PATH"]).expanduser()
        if not expected.is_absolute():
            expected = root / expected
        if model_path != expected.resolve():
            model_path = None
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

    configured_binary = _env_lookup(env, "LLAMA_SERVER")
    if configured_binary:
        os.environ["LLAMA_SERVER"] = configured_binary
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

    if not cpu_only:
        from prompt_piper.setup.llama_launcher import supports_gpu
        if not supports_gpu(binary, gpu.vendor):
            return EnsureLlmResult("cpu_only", False,
                f"{binary} cannot use the detected {gpu.vendor} GPU. Install a matching CUDA/ROCm build and runtime libraries; set LLAMA_SERVER to that binary.")

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
    if not wait_for_server(openai_base, process=process, timeout_seconds=300):
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

    readiness = verify()
    if not readiness.llm_enabled:
        stop_managed_server()
        return readiness
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
    parser.add_argument("--strict", action="store_true", help="Fail startup when a configured model cannot perform inference.")
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
    return 1 if args.strict and not result.llm_enabled and result.mode != "skipped" else 0


if __name__ == "__main__":
    raise SystemExit(main())

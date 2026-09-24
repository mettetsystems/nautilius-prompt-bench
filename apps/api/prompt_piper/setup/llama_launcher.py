from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from prompt_piper.setup.gpu_detect import GpuInfo


@dataclass(frozen=True)
class LlamaServerConfig:
    host: str
    port: int
    context_size: int
    gpu_layers: int
    model_path: Path
    binary: Path
    device_id: str | None = None
    vendor: str | None = None


def _env_int(name: str) -> int | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def estimate_model_weight_mb(model_path: Path | None) -> int | None:
    """Return on-disk GGUF size in MiB when the file exists."""
    if model_path is None or not model_path.is_file():
        return None
    return max(1, model_path.stat().st_size // (1024 * 1024))


def tune_llama_resources(
    *,
    vram_mb: int | None,
    free_vram_mb: int | None = None,
    model_path: Path | None = None,
    cpu_only: bool = False,
) -> tuple[int, int]:
    """Pick ``(n_ctx, n_gpu_layers)`` from free/detected VRAM and model weight.

    Explicit ``PROMPT_PIPER_LLAMA_N_CTX`` / ``PROMPT_PIPER_LLAMA_GPU_LAYERS`` always win.
    """
    env_ctx = _env_int("PROMPT_PIPER_LLAMA_N_CTX")
    if env_ctx is None:
        env_ctx = _env_int("PROMPT_PIPER_LLAMA_CONTEXT_SIZE")
    env_ngl = _env_int("PROMPT_PIPER_LLAMA_GPU_LAYERS")

    if cpu_only:
        return env_ctx if env_ctx is not None else 2048, 0

    budget = free_vram_mb if free_vram_mb is not None else vram_mb
    if budget is None:
        context_size = 4096
        gpu_layers = 999
    elif budget < 3072:
        context_size = 2048
        gpu_layers = 999
    elif budget < 6144:
        context_size = 4096
        gpu_layers = 999
    elif budget < 12288:
        context_size = 8192
        gpu_layers = 999
    else:
        context_size = 8192
        gpu_layers = 999

    weight_mb = estimate_model_weight_mb(model_path)
    if weight_mb is not None and budget is not None:
        # Rough KV reserve: ~128 MiB per 1k context tokens for compact SLMs.
        kv_reserve_mb = max(256, (context_size // 1024) * 128)
        available_for_weights = budget - kv_reserve_mb
        if available_for_weights <= 0:
            # Prefer a smaller context so some layers can still land on GPU.
            context_size = min(context_size, 2048)
            kv_reserve_mb = max(256, (context_size // 1024) * 128)
            available_for_weights = max(0, budget - kv_reserve_mb)
        if available_for_weights <= 0:
            gpu_layers = 0
        else:
            fraction = available_for_weights / weight_mb
            if fraction >= 0.95:
                gpu_layers = 999
            elif fraction <= 0.05:
                gpu_layers = 0
            else:
                # Approximate SLM depth (~28–40 layers); llama.cpp clamps high values.
                gpu_layers = max(1, int(40 * fraction))

    if env_ctx is not None:
        context_size = env_ctx
    if env_ngl is not None:
        gpu_layers = env_ngl
    return context_size, gpu_layers


def repo_root() -> Path:
    override = os.getenv("PROMPT_PIPER_REPO_ROOT")
    if override and override.strip():
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[4]


def pid_file_path() -> Path:
    return repo_root() / "data" / ".llama-server.pid"


def find_llama_server() -> Path | None:
    override = os.getenv("LLAMA_SERVER")
    if override:
        path = Path(override).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    discovered = shutil.which("llama-server") or shutil.which("llama-server-bin")
    if discovered:
        return Path(discovered)
    for candidate in (
        Path("/usr/bin/llama-server"),
        Path("/usr/local/bin/llama-server"),
        Path("/opt/homebrew/bin/llama-server"),
        Path.home() / ".local" / "bin" / "llama-server",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def resolve_model_path(
    *,
    configured_path: str | None,
    preset_id: str | None,
) -> Path | None:
    root = repo_root()
    if configured_path:
        path = Path(configured_path).expanduser()
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            return path.resolve()

    models_dir = root / "data" / "models"
    if not models_dir.is_dir():
        return None

    if preset_id and preset_id not in {"cpu-only", "custom"}:
        from prompt_piper.setup.catalog import ALL_PRESETS, resolve_preset_id

        preset = ALL_PRESETS.get(resolve_preset_id(preset_id))
        if preset is not None:
            candidate = models_dir / preset.suggested_gguf_filename
            if candidate.is_file():
                return candidate.resolve()

    gguf_files = sorted(
        models_dir.glob("*.gguf"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if gguf_files:
        return gguf_files[0].resolve()
    return None


def server_base_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/v1"


def is_server_healthy(base_url: str, *, timeout: float = 3.0) -> bool:
    try:
        with urlopen(f"{base_url.rstrip('/')}/models", timeout=timeout) as response:
            return response.status == 200
    except (URLError, OSError, ValueError):
        return False


def build_server_config(
    *,
    model_path: Path,
    binary: Path,
    gpu: GpuInfo | None,
    host: str = "127.0.0.1",
    port: int = 8080,
    context_size: int | None = None,
    cpu_only: bool = False,
) -> LlamaServerConfig:
    tuned_ctx, tuned_ngl = tune_llama_resources(
        vram_mb=None if gpu is None else gpu.vram_mb,
        free_vram_mb=(
            None if gpu is None else
            gpu.memory_budget_mb if gpu.memory_budget_mb is not None else gpu.free_vram_mb
        ),
        model_path=model_path,
        cpu_only=cpu_only or gpu is None,
    )
    return LlamaServerConfig(
        host=host,
        port=port,
        context_size=context_size if context_size is not None else tuned_ctx,
        gpu_layers=tuned_ngl,
        model_path=model_path,
        binary=binary,
        device_id=gpu.device_id if gpu else None,
        vendor=gpu.vendor if gpu else None,
    )


def llama_command(config: LlamaServerConfig) -> list[str]:
    return [
        str(config.binary),
        "-m",
        str(config.model_path),
        "--host",
        config.host,
        "--port",
        str(config.port),
        "-c",
        str(config.context_size),
        "-ngl",
        str(config.gpu_layers),
    ]


def read_managed_pid() -> int | None:
    path = pid_file_path()
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    if pid <= 0:
        return None
    return pid


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _send_signal(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
        return
    except ProcessLookupError:
        return
    except OSError:
        pass
    try:
        os.kill(pid, sig)
    except OSError:
        return


def stop_managed_server() -> bool:
    pid = read_managed_pid()
    if pid is None:
        return False
    if _pid_is_running(pid):
        _send_signal(pid, signal.SIGTERM)
        for _ in range(40):
            if not _pid_is_running(pid):
                break
            time.sleep(0.25)
        if _pid_is_running(pid):
            _send_signal(pid, signal.SIGKILL)
            time.sleep(0.25)
    with suppress(OSError):
        pid_file_path().unlink(missing_ok=True)
    return True


def start_server(
    config: LlamaServerConfig,
    *,
    log_path: Path | None = None,
) -> subprocess.Popen[str]:
    pid_file_path().parent.mkdir(parents=True, exist_ok=True)
    stdout = subprocess.DEVNULL
    stderr = subprocess.DEVNULL
    log_handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8")
        stdout = log_handle
        stderr = log_handle

    process_env = os.environ.copy()
    if config.device_id is not None:
        visibility = "CUDA_VISIBLE_DEVICES" if config.vendor == "nvidia" else "ROCR_VISIBLE_DEVICES"
        process_env.setdefault(visibility, config.device_id)

    process = subprocess.Popen(
        llama_command(config),
        stdout=stdout,
        stderr=stderr,
        env=process_env,
        start_new_session=True,
        text=True,
    )
    if log_handle is not None:
        log_handle.close()
    pid_file_path().write_text(str(process.pid), encoding="utf-8")
    return process


def wait_for_server(
    base_url: str,
    *,
    process: subprocess.Popen[str] | None = None,
    timeout_seconds: float = 120.0,
    poll_interval: float = 1.0,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False
        if is_server_healthy(base_url):
            return True
        time.sleep(poll_interval)
    return False


def supports_gpu(binary: Path, vendor: str) -> bool:
    """Check the actual inference backend, independently of PyTorch/driver detection."""
    try:
        result = subprocess.run([str(binary), "--list-devices"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = result.stdout.lower()
    markers = {"nvidia": ("cuda",), "amd": ("rocm", "hip"), "apple": ("metal",)}.get(vendor, ())
    return result.returncode == 0 and any(marker in output for marker in markers)

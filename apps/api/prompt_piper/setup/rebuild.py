"""Reconfigure changed hardware and rebuild without deleting user data or model weights."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from prompt_piper.setup.hardware import print_hardware, scan_hardware
from prompt_piper.setup.llama_launcher import repo_root
from prompt_piper.setup.wizard import run_setup_wizard


def reset_hardware_overrides(path: Path) -> None:
    """Remove stale tuning, keeping endpoint credentials and all application data intact."""
    keys = {
        "PROMPT_PIPER_LLAMA_N_CTX",
        "PROMPT_PIPER_LLAMA_CONTEXT_SIZE",
        "PROMPT_PIPER_LLAMA_GPU_LAYERS",
        "CUDA_VISIBLE_DEVICES",
        "ROCR_VISIBLE_DEVICES",
        "HIP_VISIBLE_DEVICES",
    }
    lines = [
        line
        for line in path.read_text().splitlines()
        if line.split("=", 1)[0].strip().removeprefix("export ") not in keys
    ]
    path.write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scan-only", action="store_true", help="Read hardware; write/build nothing."
    )
    parser.add_argument("--skip-build", action="store_true", help="Reconfigure only.")
    parser.add_argument("--non-interactive", metavar="PRESET", help="Explicit preset or cpu-only.")
    parser.add_argument(
        "--llama-source", type=Path, help="Optional existing llama.cpp source to rebuild."
    )
    parser.add_argument(
        "--containers", action="store_true", help="Build Podman images instead of native web."
    )
    args = parser.parse_args(argv)
    report = scan_hardware()
    print_hardware(report)
    if args.scan_only:
        return 0
    root = repo_root()
    env_path = root / ".env"
    if env_path.exists():
        backup = root / (".env.hardware-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".bak")
        shutil.copy2(env_path, backup)
        backup.chmod(0o600)
        print(f"Configuration backup: {backup}")
    try:
        run_setup_wizard(env_path=env_path, non_interactive=args.non_interactive)
        reset_hardware_overrides(env_path)
        from prompt_piper.setup.embedding_device import resolve_embedding_device
        from prompt_piper.setup.env_writer import upsert_lexicon_env_section

        decision = resolve_embedding_device()
        upsert_lexicon_env_section(env_path, {"PROMPT_PIPER_EMBEDDING_DEVICE": decision.device})
        print(f"Embeddings: {decision.device} — {decision.reason}")
        if not args.skip_build:
            if args.containers:
                subprocess.run(
                    ["podman", "compose", "-f", "infra/podman-compose.yml", "build"],
                    cwd=root,
                    check=True,
                )
            else:
                subprocess.run(["npm", "run", "build:web"], cwd=root, check=True)
            if args.llama_source:
                source = args.llama_source.expanduser().resolve()
                if not (source / "CMakeLists.txt").is_file():
                    raise ValueError("--llama-source must point to an existing llama.cpp checkout")
                build = source / "build-nautilius-hardware"
                gpu = report["selected_gpu"]
                vendor = gpu["vendor"] if gpu else "cpu"
                subprocess.run(
                    [
                        "cmake",
                        "--fresh",
                        "-S",
                        str(source),
                        "-B",
                        str(build),
                        "-DGGML_CUDA=" + ("ON" if vendor == "nvidia" else "OFF"),
                        "-DGGML_HIP=" + ("ON" if vendor == "amd" else "OFF"),
                        "-DCMAKE_BUILD_TYPE=Release",
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        "cmake",
                        "--build",
                        str(build),
                        "--config",
                        "Release",
                        "--target",
                        "llama-server",
                        "-j",
                        "2",
                    ],
                    check=True,
                )
                from prompt_piper.setup.env_writer import _format_assignment
                lines = [line for line in env_path.read_text().splitlines() if not line.startswith("LLAMA_SERVER=")]
                lines.append(_format_assignment("LLAMA_SERVER", str(build / "bin/llama-server")))
                env_path.write_text("\n".join(lines) + "\n")
                print(f"Rebuilt and configured llama-server: {build / 'bin/llama-server'}")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Hardware rebuild failed: {exc}. Your configuration backup and data are preserved.")
        return 1
    print(
        "Rebuild complete. No models downloaded or started; sessions, exports, weights and lexicon index preserved."
    )
    print(
        "Restart your API/web processes (or Podman stack) to apply the new configuration. Stop old model servers before loading a replacement."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

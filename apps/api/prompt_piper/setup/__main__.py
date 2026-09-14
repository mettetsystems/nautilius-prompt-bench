from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prompt_piper.setup.wizard import run_setup_wizard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nautilius Prompting Workbench interactive setup wizard (local model configuration).",
    )
    parser.add_argument(
        "--non-interactive",
        metavar="MODE",
        help=(
            "Non-interactive mode: cpu-only, PRESET, or DEPLOYMENT:PRESET "
            "(e.g. podman:gemma3-1b, native:qwen3-1.7b, custom, cpu-only). "
            "Legacy aliases: qwen3-1.5b, qwen3-3b."
        ),
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to .env file (default: repo root .env).",
    )
    parser.add_argument("--clarification-only", action="store_true", help="Configure the dedicated large clarification model without changing the lightweight model.")
    parser.add_argument("--hardware-scan", action="store_true", help="Print GPU inventory and recommendations without changing configuration.")
    args = parser.parse_args(argv)

    try:
        if args.hardware_scan:
            from prompt_piper.setup.hardware import print_hardware, scan_hardware
            print_hardware(scan_hardware())
            return 0
        from prompt_piper.setup.clarification_model import configure_clarification_model
        if args.clarification_only:
            configure_clarification_model(None if args.env_file is None else Path(args.env_file))
            return 0
        run_setup_wizard(
            env_path=None if args.env_file is None else Path(args.env_file),
            non_interactive=args.non_interactive,
        )
        if args.non_interactive is None:
            configure_clarification_model(None if args.env_file is None else Path(args.env_file))
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    args = parser.parse_args(argv)

    try:
        run_setup_wizard(
            env_path=None if args.env_file is None else Path(args.env_file),
            non_interactive=args.non_interactive,
        )
    except (KeyboardInterrupt, EOFError):
        print("\nSetup cancelled.", file=sys.stderr)
        return 130
    except ValueError as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

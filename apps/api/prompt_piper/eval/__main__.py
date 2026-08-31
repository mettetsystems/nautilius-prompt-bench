from __future__ import annotations

import argparse
from pathlib import Path

from prompt_piper.eval.runner import run_eval


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Nautilius Prompting Workbench local eval suite")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run regression cases and quality gate")
    run_parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="Path to regression_cases.yaml (defaults to tests/evals/regression_cases.yaml)",
    )

    args = parser.parse_args(argv)
    if args.command == "run":
        return run_eval(cases_path=args.cases)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

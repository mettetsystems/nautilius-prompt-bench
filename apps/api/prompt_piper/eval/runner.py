from __future__ import annotations

import sys
from pathlib import Path

from prompt_piper_api.services.quality_gate_service import QualityGateService
from prompt_piper_api.services.regression_evaluator import RegressionEvaluator


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_cases_path() -> Path:
    return _repo_root() / "tests" / "evals" / "regression_cases.yaml"


def run_eval(*, cases_path: Path | None = None) -> int:
    path = cases_path or _default_cases_path()
    if not path.is_file():
        print(f"Regression cases file not found: {path}", file=sys.stderr)
        return 1

    evaluator = RegressionEvaluator()
    gate = QualityGateService(regression_evaluator=evaluator)
    cases = evaluator.load_cases(path)
    regression = evaluator.run_cases(cases)
    if regression.aggregate_metrics is None:
        print("No regression metrics were computed.", file=sys.stderr)
        return 1

    result = gate.evaluate(
        regression.aggregate_metrics,
        safety_failures=regression.safety_failures,
        regression=regression,
    )

    print("Nautilius Prompting Workbench pre-inference eval")
    print(f"Cases run: {regression.cases_run}")
    print(f"Optimized losses: {regression.optimized_losses}")
    print(f"Regression loss rate: {regression.loss_rate:.1%}")
    print(f"Safety failures: {len(regression.safety_failures)}")
    print(f"Quality gate passed: {result.passed}")
    if result.failures:
        print("Failures:")
        for failure in result.failures:
            print(f"  - {failure}")

    failed_cases = [item for item in regression.case_results if not item.optimized_wins]
    if failed_cases:
        print("Pairwise losses:")
        for item in failed_cases:
            print(f"  - {item.case_id}")

    return 0 if result.passed else 1

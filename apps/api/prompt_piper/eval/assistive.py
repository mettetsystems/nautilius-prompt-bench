from __future__ import annotations

import sys
from pathlib import Path

import yaml
from prompt_piper_api.services.assistive_extraction_metrics import score_extraction_case
from prompt_piper_api.services.requirement_card_extractor import RequirementCardExtractor


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _default_cases_path() -> Path:
    return _repo_root() / "tests" / "evals" / "assistive" / "extraction_cases.yaml"


def run_assistive_eval(*, cases_path: Path | None = None) -> int:
    path = cases_path or _default_cases_path()
    if not path.is_file():
        print(f"Assistive cases file not found: {path}", file=sys.stderr)
        return 1

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cases = payload.get("cases") or []
    extractor = RequirementCardExtractor(llm=None)
    scores = []
    for case in cases:
        card = extractor.extract(str(case["initial_request"]))
        score = score_extraction_case(
            case_id=str(case["id"]),
            card=card,
            expected=dict(case.get("expected") or {}),
            must_remain_unspecified=list(case.get("must_remain_unspecified") or []),
        )
        scores.append(score)

    if not scores:
        print("No assistive cases found.", file=sys.stderr)
        return 1

    mean = sum(item.score for item in scores) / len(scores)
    honesty_ok = sum(1 for item in scores if item.honesty_ok)
    print("Nautilius Prompting Workbench assistive extraction eval (rule-based baseline)")
    print(f"Cases run: {len(scores)}")
    print(f"Mean score: {mean:.3f}")
    print(f"Honesty OK: {honesty_ok}/{len(scores)}")
    weak = [item for item in scores if item.score < 0.5]
    if weak:
        print("Weak cases:")
        for item in weak:
            print(
                f"  - {item.case_id}: score={item.score} "
                f"missed={item.missed_leaves} honesty={item.honesty_violations}"
            )
    # Baseline rule extractor is expected to be imperfect; gate on honesty + smoke.
    return 0 if honesty_ok == len(scores) else 1


def main() -> None:
    raise SystemExit(run_assistive_eval())


if __name__ == "__main__":
    main()

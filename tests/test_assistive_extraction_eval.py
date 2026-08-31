"""Assistive extraction eval metrics and optional DSPy adapter smoke tests."""

from pathlib import Path

import yaml
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.assistive_extraction_metrics import score_extraction_case
from prompt_piper_api.services.dspy_extraction import (
    OptionalDspyRequirementExtractor,
    build_dspy_extraction_module,
    dspy_available,
)
from prompt_piper_api.services.requirement_card_extractor import RequirementCardExtractor


def _cases_path() -> Path:
    return Path(__file__).resolve().parent / "evals" / "assistive" / "extraction_cases.yaml"


def test_extraction_cases_file_loads() -> None:
    payload = yaml.safe_load(_cases_path().read_text(encoding="utf-8"))
    assert payload["cases"]
    assert len(payload["cases"]) >= 15


def test_rule_based_extractor_honesty_on_vague_case() -> None:
    payload = yaml.safe_load(_cases_path().read_text(encoding="utf-8"))
    vague = next(case for case in payload["cases"] if case["id"] == "vague_should_stay_unspecified")
    card = RequirementCardExtractor(llm=None).extract(vague["initial_request"])
    score = score_extraction_case(
        case_id=vague["id"],
        card=card,
        expected=dict(vague.get("expected") or {}),
        must_remain_unspecified=list(vague.get("must_remain_unspecified") or []),
    )
    assert score.honesty_ok


def test_leaf_match_scores_fastapi_case() -> None:
    card = RequirementCard(
        task_identity={
            "objective": "Build POST /users endpoint",
            "task_type": "new feature logic",
            "environment": "FastAPI + Pydantic v2",
        },
    )
    score = score_extraction_case(
        case_id="manual",
        card=card,
        expected={
            "task_identity.environment": "FastAPI",
            "task_identity.objective": "POST /users",
            "task_identity.task_type": "new feature",
        },
    )
    assert score.leaf_hits == 3
    assert score.honesty_ok
    assert score.score == 1.0


def test_optional_dspy_adapter_falls_back_without_dspy() -> None:
    extractor = OptionalDspyRequirementExtractor(llm=None)
    card = extractor.extract("FastAPI POST /users with email and full_name")
    assert isinstance(card, RequirementCard)


def test_build_dspy_module_is_optional() -> None:
    module = build_dspy_extraction_module()
    if dspy_available():
        assert module is not None
    else:
        assert module is None

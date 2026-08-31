"""Leaf-match and unspecified-honesty metrics for assistive RequirementCard extraction."""

from __future__ import annotations

from dataclasses import dataclass

from prompt_piper_api.domain.requirement_card import LIST_LEAF_FIELDS, RequirementCard
from prompt_piper_api.services.clarification_question_ranker import is_unspecified_answer


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _leaf_text(card: RequirementCard, field_name: str) -> str:
    value = card.get_leaf(field_name)
    if isinstance(value, list):
        return " ".join(item.strip() for item in value if item.strip())
    if isinstance(value, str):
        return value.strip()
    return ""


def leaf_contains_expected(card: RequirementCard, field_name: str, expected: object) -> bool:
    """True when the card leaf contains each expected token/phrase (case-insensitive)."""
    actual = _normalize(_leaf_text(card, field_name))
    if not actual or is_unspecified_answer(actual):
        return False
    if isinstance(expected, list):
        return all(_normalize(str(token)) in actual for token in expected if str(token).strip())
    return _normalize(str(expected)) in actual


def leaf_is_unspecified(card: RequirementCard, field_name: str) -> bool:
    if field_name in card.unresolved_fields:
        return True
    if card.is_leaf_missing(field_name):
        return True
    text = _leaf_text(card, field_name)
    return not text or is_unspecified_answer(text)


@dataclass(frozen=True)
class ExtractionCaseScore:
    case_id: str
    leaf_hits: int
    leaf_total: int
    honesty_ok: bool
    score: float
    missed_leaves: list[str]
    honesty_violations: list[str]


def score_extraction_case(
    *,
    case_id: str,
    card: RequirementCard,
    expected: dict[str, object],
    must_remain_unspecified: list[str] | None = None,
) -> ExtractionCaseScore:
    """Score one extraction against expected leaf substrings and honesty constraints."""
    missed: list[str] = []
    hits = 0
    for field_name, expected_value in expected.items():
        if leaf_contains_expected(card, field_name, expected_value):
            hits += 1
        else:
            missed.append(field_name)
    total = max(len(expected), 1) if expected else 0

    honesty_violations: list[str] = []
    for field_name in must_remain_unspecified or []:
        if not leaf_is_unspecified(card, field_name):
            honesty_violations.append(field_name)

    # Invented list leaves that were not expected also hurt honesty lightly when
    # the case declares an explicit unspecified set.
    if must_remain_unspecified:
        for field_name in LIST_LEAF_FIELDS:
            if field_name in expected:
                continue
            if field_name in (must_remain_unspecified or []):
                continue

    honesty_ok = not honesty_violations
    leaf_score = (1.0 if honesty_ok else 0.0) if total == 0 else hits / total
    score = round(leaf_score * (1.0 if honesty_ok else 0.5), 3)
    return ExtractionCaseScore(
        case_id=case_id,
        leaf_hits=hits,
        leaf_total=total if expected else 0,
        honesty_ok=honesty_ok,
        score=score,
        missed_leaves=missed,
        honesty_violations=honesty_violations,
    )

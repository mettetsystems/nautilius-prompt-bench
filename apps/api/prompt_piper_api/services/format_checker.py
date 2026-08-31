from __future__ import annotations

import re

from prompt_piper_api.domain.harness import HARNESS_SECTION_TITLES
from prompt_piper_api.domain.requirement_card import DIMENSION_SECTION_TITLES

_PLAIN_TEXT_FORBIDDEN = (
    re.compile(r"^#{1,6}\s", re.MULTILINE),
    re.compile(r"<[^>]+>"),
    re.compile(r"\*\*[^*]+\*\*"),
    re.compile(r"```"),
)

_DRAFT_SECTIONS = tuple(title.lower() for title in DIMENSION_SECTION_TITLES)
_HARNESS_SECTIONS = tuple(title.lower() for title in HARNESS_SECTION_TITLES)


def coding_section_coverage(body: str) -> int:
    """Count long-horizon contract section titles present in the body."""
    lowered = body.lower()
    return sum(1 for section in _DRAFT_SECTIONS if section in lowered)


def harness_section_coverage(body: str) -> int:
    """Count harness/contract section titles (same contract as the draft)."""
    lowered = body.lower()
    return sum(1 for section in _HARNESS_SECTIONS if section in lowered)


def format_adherence_score(body: str) -> float:
    """Return 1.00 when the prompt follows the plain-text task-contract layout."""
    if not body.strip():
        return 0.0
    for pattern in _PLAIN_TEXT_FORBIDDEN:
        if pattern.search(body):
            return 0.0
    hits = max(coding_section_coverage(body), harness_section_coverage(body))
    required = max(6, len(_DRAFT_SECTIONS) // 2)
    if hits < required:
        return 0.0
    if not re.search(r"^[A-Za-z].+\n[-]{3,}", body, re.MULTILINE):
        return 0.0
    return 1.0

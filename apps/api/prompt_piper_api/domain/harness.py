"""Coding-assistant harness: long-horizon task contract (clarity over token count)."""

from __future__ import annotations

from prompt_piper_api.domain.agent_contract import CONTRACT_SECTION_TITLES
from prompt_piper_api.domain.requirement_card import DIMENSION_SECTION_TITLES

# Canonical section titles for drafts, optimized bodies, and API-bound exports.
HARNESS_SECTION_TITLES: tuple[str, ...] = DIMENSION_SECTION_TITLES

HARNESS_SYSTEM_PROMPT = (
    "You are a long-horizon coding agent. Follow every task-contract section exactly. "
    "Clarity of operational rules takes priority over brevity. "
    "Persist progress according to the task contract and receiving harness. Do not declare COMPLETE without evidence. "
    "Never suppress an error without understanding why it occurs. "
    "Do not invent requirements marked unspecified. "
    "Pause and persist state when budget, safety, or escalation rules require it."
)

# Maps draft titles → harness section (identity mapping; optimizer does not compress).
DRAFT_TO_HARNESS_SECTION: dict[str, str] = {
    title: title for title in (*DIMENSION_SECTION_TITLES, *CONTRACT_SECTION_TITLES)
}

API_PACK_FORMATS: tuple[str, ...] = (
    "openai_chat_completions",
    "anthropic_messages",
    "gemini_generate_content",
    "cursor_agent",
    "copilot_instructions",
    "continue_config",
)

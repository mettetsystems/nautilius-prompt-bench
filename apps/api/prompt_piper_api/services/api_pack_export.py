"""Export optimized harness prompts into top coding-assistant / provider API packs."""

from __future__ import annotations

import json
from typing import Any

from prompt_piper_api.domain.harness import API_PACK_FORMATS, HARNESS_SYSTEM_PROMPT
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.harness_prompt_builder import (
    build_harness_body,
    build_harness_spec,
    harness_markdown,
)


def _openai_chat_completions(system: str, user: str) -> dict[str, Any]:
    return {
        "model": "REPLACE_WITH_MODEL",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }


def _anthropic_messages(system: str, user: str) -> dict[str, Any]:
    return {
        "model": "REPLACE_WITH_MODEL",
        "max_tokens": 8192,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "temperature": 0.2,
    }


def _gemini_generate_content(system: str, user: str) -> dict[str, Any]:
    return {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2},
    }


def _cursor_agent(system: str, user: str) -> dict[str, Any]:
    return {
        "format": "cursor_agent",
        "description": "Paste system into Cursor rules/agent instructions; user into the chat.",
        "system": system,
        "user": user,
        "rules_markdown": (
            f"# Nautilius long-horizon coding contract\n\n{system}\n\n## Task harness\n\n{user}\n"
        ),
    }


def _copilot_instructions(system: str, user: str) -> dict[str, Any]:
    return {
        "format": "github_copilot_custom_instructions",
        "description": "Use instructions_markdown as Copilot custom instructions; chat_prompt for the ask.",
        "instructions_markdown": system + "\n\n" + user,
        "chat_prompt": user,
        "system": system,
    }


def _continue_config(system: str, user: str) -> dict[str, Any]:
    return {
        "name": "Nautilius long-horizon coding contract",
        "systemMessage": system,
        "prompt": user,
        "temperature": 0.2,
        "description": "Map systemMessage to Continue.dev config; send prompt as the user message.",
    }


_BUILDERS = {
    "openai_chat_completions": _openai_chat_completions,
    "anthropic_messages": _anthropic_messages,
    "gemini_generate_content": _gemini_generate_content,
    "cursor_agent": _cursor_agent,
    "copilot_instructions": _copilot_instructions,
    "continue_config": _continue_config,
}


def build_api_pack(
    card: RequirementCard,
    *,
    harness_body: str | None = None,
    title: str = "Coding harness prompt",
) -> dict[str, Any]:
    """Return filename → text/json payload for the hybrid six-format export pack."""
    body = harness_body or build_harness_body(card)
    system = HARNESS_SYSTEM_PROMPT
    pack: dict[str, Any] = {
        "harness_prompt.txt": body,
        "harness_prompt.md": harness_markdown(card, title=title),
        "coding_harness_spec.json": build_harness_spec(card),
        "api_pack/README.md": _pack_readme(),
    }
    for name in API_PACK_FORMATS:
        builder = _BUILDERS[name]
        payload = builder(system, body)
        pack[f"api_pack/{name}.json"] = payload
        if name == "cursor_agent":
            pack["api_pack/cursor_rules.md"] = str(payload["rules_markdown"])
        elif name == "copilot_instructions":
            pack["api_pack/copilot_instructions.md"] = str(payload["instructions_markdown"])
        elif name == "continue_config":
            pack["api_pack/continue_system.md"] = (
                f"# Continue system message\n\n{system}\n\n# User prompt\n\n{body}\n"
            )
    return pack


def dumps_pack_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _pack_readme() -> str:
    lines = [
        "# Coding assistant API pack",
        "",
        "Token-optimized harness prompt packaged for common provider APIs and coding assistants.",
        "",
        "| File | Use |",
        "|------|-----|",
        "| `openai_chat_completions.json` | OpenAI Chat Completions `messages` |",
        "| `anthropic_messages.json` | Anthropic Messages API |",
        "| `gemini_generate_content.json` | Google Gemini `generateContent` |",
        "| `cursor_agent.json` / `cursor_rules.md` | Cursor agent / rules paste |",
        "| `copilot_instructions.json` / `.md` | GitHub Copilot custom instructions |",
        "| `continue_config.json` / `continue_system.md` | Continue.dev system + prompt |",
        "",
        "Replace `REPLACE_WITH_MODEL` before calling a provider API.",
        "",
    ]
    return "\n".join(lines)

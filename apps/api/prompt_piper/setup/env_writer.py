from __future__ import annotations

import re
from pathlib import Path

_MANAGED_KEYS = frozenset(
    {
        "PROMPT_PIPER_LLM_ENABLED",
        "PROMPT_PIPER_LOCAL_BASE_URL",
        "PROMPT_PIPER_LOCAL_CHAT_MODEL",
        "PROMPT_PIPER_LOCAL_EMBED_MODEL",
        "PROMPT_PIPER_LOCAL_API_KEY",
        "PROMPT_PIPER_LOCAL_MODEL_PRESET",
        "PROMPT_PIPER_LOCAL_MODEL_PATH",
        "PROMPT_PIPER_LOCAL_MODEL_GGUF_REPO",
        "PROMPT_PIPER_LOCAL_MODEL_GGUF_FILE",
    }
)

_LEXICON_MANAGED_KEYS = frozenset(
    {
        "PROMPT_PIPER_EMBEDDING_DEVICE",
    }
)

_SECTION_BEGIN = "# --- Local LLM (Nautilius Prompting Workbench setup wizard) ---"
_SECTION_END = "# --- End local LLM setup ---"
_LEXICON_SECTION_BEGIN = "# --- Precision lexicon (Nautilius Prompting Workbench setup) ---"
_LEXICON_SECTION_END = "# --- End precision lexicon setup ---"


def upsert_env_section(
    env_path: Path,
    values: dict[str, str],
    *,
    preamble: tuple[str, ...] = (),
) -> None:
    """Merge wizard-managed keys into .env, preserving unrelated lines."""
    existing = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    stripped = _remove_managed_section(existing)
    stripped = _remove_managed_keys(stripped)

    lines = [line.rstrip() for line in stripped.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()

    assignments = [_format_assignment(key, value) for key, value in values.items()]
    block = [_SECTION_BEGIN, *preamble, *assignments, _SECTION_END]
    if lines:
        lines.append("")
    lines.extend(block)
    lines.append("")
    env_path.write_text("\n".join(lines), encoding="utf-8")


def upsert_lexicon_env_section(
    env_path: Path,
    values: dict[str, str],
    *,
    preamble: tuple[str, ...] = (),
) -> None:
    """Merge lexicon setup keys into .env, preserving unrelated lines."""
    existing = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
    stripped = _remove_lexicon_section(existing)
    stripped = _remove_keys(stripped, _LEXICON_MANAGED_KEYS)

    lines = [line.rstrip() for line in stripped.splitlines()]
    while lines and not lines[-1].strip():
        lines.pop()

    assignments = [_format_assignment(key, value) for key, value in values.items()]
    block = [_LEXICON_SECTION_BEGIN, *preamble, *assignments, _LEXICON_SECTION_END]
    if lines:
        lines.append("")
    lines.extend(block)
    lines.append("")
    env_path.write_text("\n".join(lines), encoding="utf-8")


def _format_assignment(key: str, value: str) -> str:
    if re.search(r"\s|#|\"", value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    return f"{key}={value}"


def _remove_managed_section(content: str) -> str:
    return _remove_section(content, _SECTION_BEGIN, _SECTION_END)


def _remove_lexicon_section(content: str) -> str:
    return _remove_section(content, _LEXICON_SECTION_BEGIN, _LEXICON_SECTION_END)


def _remove_section(content: str, begin: str, end: str) -> str:
    pattern = re.compile(
        rf"^\s*{re.escape(begin)}.*?^\s*{re.escape(end)}\s*$",
        re.MULTILINE | re.DOTALL,
    )
    return pattern.sub("", content)


def _remove_managed_keys(content: str) -> str:
    return _remove_keys(content, _MANAGED_KEYS)


def _remove_keys(content: str, keys: frozenset[str]) -> str:
    kept: list[str] = []
    for line in content.splitlines():
        match = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=", line)
        if match and match.group(1) in keys:
            continue
        kept.append(line)
    return "\n".join(kept)

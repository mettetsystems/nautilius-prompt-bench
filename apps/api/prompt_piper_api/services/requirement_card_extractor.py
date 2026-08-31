import json
import re

from prompt_piper_api.domain.agent_contract import expand_clarification_answer
from prompt_piper_api.domain.requirement_card import LIST_LEAF_FIELDS, RequirementCard
from prompt_piper_api.llm.base import ChatMessage, LLMClient
from prompt_piper_api.llm.fallback import with_llm_fallback
from prompt_piper_api.services.clarification_question_ranker import is_unspecified_answer

_LINE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^objective:\s*(.+)$", re.IGNORECASE), "task_identity.objective"),
    (re.compile(r"^goal:\s*(.+)$", re.IGNORECASE), "task_identity.objective"),
    (re.compile(r"^task(?:\s+type)?:\s*(.+)$", re.IGNORECASE), "task_identity.task_type"),
    (re.compile(r"^environment:\s*(.+)$", re.IGNORECASE), "task_identity.environment"),
    (re.compile(r"^stack:\s*(.+)$", re.IGNORECASE), "task_identity.environment"),
    (
        re.compile(r"^constraint:\s*(.+)$", re.IGNORECASE),
        "task_identity.additional_constraints",
    ),
    (
        re.compile(r"^constraints:\s*(.+)$", re.IGNORECASE),
        "task_identity.additional_constraints",
    ),
]

_SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")
_LLM_EXTRACT_SYSTEM = (
    "Extract the coding TASK identity into JSON matching RequirementCard "
    "task_identity {objective, task_type, environment, additional_constraints}. "
    "The request may include markdown tables; copy each table into "
    "additional_constraints as a single string (keep pipes and row breaks). "
    "Do not flatten table cells into one sentence. "
    "Leave agent_contract fields empty. Do not invent operational policies."
)


def partition_intake_tables(text: str) -> tuple[list[str], list[str]]:
    """Split request text into prose lines and markdown table blocks."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    prose: list[str] = []
    tables: list[str] = []
    index = 0
    while index < len(lines):
        markdown = _take_markdown_table(lines, index)
        if markdown is not None:
            block, next_index = markdown
            tables.append(block)
            index = next_index
            continue
        tsv = _take_tsv_table(lines, index)
        if tsv is not None:
            block, next_index = tsv
            tables.append(block)
            index = next_index
            continue
        prose.append(lines[index])
        index += 1
    return prose, tables


def _take_markdown_table(lines: list[str], start: int) -> tuple[str, int] | None:
    if start + 1 >= len(lines):
        return None
    if not _is_markdown_pipe_row(lines[start]) or not _is_markdown_separator(lines[start + 1]):
        return None
    end = start + 2
    while end < len(lines) and _is_markdown_pipe_row(lines[end]):
        end += 1
    block = "\n".join(line.rstrip() for line in lines[start:end]).strip()
    return (block, end) if block else None


def _take_tsv_table(lines: list[str], start: int) -> tuple[str, int] | None:
    if not _is_tsv_line(lines[start]):
        return None
    end = start
    rows: list[list[str]] = []
    while end < len(lines) and _is_tsv_line(lines[end]):
        rows.append([cell.strip() for cell in lines[end].split("\t")])
        end += 1
    if len(rows) < 2:
        return None
    return _rows_to_markdown(rows), end


def _is_markdown_pipe_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|") or stripped.count("|") < 2:
        return False
    return not _is_markdown_separator(stripped)


def _is_markdown_separator(line: str) -> bool:
    stripped = line.strip()
    if "|" not in stripped:
        return False
    inner = stripped[1:] if stripped.startswith("|") else stripped
    if inner.endswith("|"):
        inner = inner[:-1]
    cells = [cell.strip() for cell in inner.split("|")]
    return bool(cells) and all(_SEPARATOR_CELL.fullmatch(cell) for cell in cells)


def _is_tsv_line(line: str) -> bool:
    return "\t" in line and len(line.split("\t")) >= 2


def _rows_to_markdown(rows: list[list[str]]) -> str:
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return ""
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = padded[0]
    separator = ["---"] * width
    body = padded[1:]

    def _fmt(cells: list[str]) -> str:
        return "| " + " | ".join(cells) + " |"

    return "\n".join([_fmt(header), _fmt(separator), *(_fmt(row) for row in body)])


def _prose_text(lines: list[str]) -> str:
    return " ".join(line.strip() for line in lines if line.strip())


def _looks_like_markdown_table(value: str) -> bool:
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for index, line in enumerate(lines[:-1]):
        if _is_markdown_pipe_row(line) and _is_markdown_separator(lines[index + 1]):
            return True
    return False


def _constraint_contains_table(item: str, table: str) -> bool:
    compact_item = re.sub(r"\s+", "", item)
    compact_table = re.sub(r"\s+", "", table.removeprefix("Table:").lstrip())
    if not compact_table:
        return False
    return compact_table in compact_item or compact_item in compact_table


class RequirementCardExtractor:
    """Maps free-text requests onto task identity; contract fields are filled by clarification."""

    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm

    def extract(self, initial_request: str) -> RequirementCard:
        card = with_llm_fallback(
            self._llm,
            lambda client: self._extract_with_llm(client, initial_request),
            lambda: self._extract_rule_based(initial_request),
        )
        self._restore_full_intake_prose(card, initial_request)
        self._apply_tables_from_request(card, initial_request)
        return card

    def apply_answer(self, card: RequirementCard, field_name: str, answer: str) -> None:
        """Write a clarification answer onto the requirement card."""
        cleaned = answer.strip()
        if not cleaned:
            msg = "Clarification answer cannot be empty"
            raise ValueError(msg)

        if is_unspecified_answer(cleaned):
            self._mark_unspecified(card, field_name)
            return

        if field_name == "optimization_targets":
            card.optimization_targets.clarity = cleaned
            if field_name in card.unresolved_fields:
                card.unresolved_fields = [
                    name for name in card.unresolved_fields if name != field_name
                ]
            return

        expanded = expand_clarification_answer(field_name, cleaned)
        self._assign(card, field_name, expanded)
        if field_name in card.unresolved_fields:
            card.unresolved_fields = [name for name in card.unresolved_fields if name != field_name]

    def _mark_unspecified(self, card: RequirementCard, field_name: str) -> None:
        """Keep a field empty and explicitly unresolved rather than inventing a value."""
        card.clear_leaf(field_name)
        if field_name not in card.unresolved_fields:
            card.unresolved_fields.append(field_name)

    def _extract_with_llm(self, llm: LLMClient, initial_request: str) -> RequirementCard:
        response = llm.chat(
            [
                ChatMessage(
                    role="system",
                    content=_LLM_EXTRACT_SYSTEM,
                ),
                ChatMessage(role="user", content=initial_request),
            ],
            response_format={"type": "json_object"},
        )
        payload = json.loads(response.content)
        card = RequirementCard.model_validate(payload)
        if not card.task_identity.objective:
            prose, _tables = partition_intake_tables(initial_request)
            card.task_identity.objective = _prose_text(prose)
        self._apply_clarity_default(card)
        return card

    def _extract_rule_based(self, initial_request: str) -> RequirementCard:
        card = RequirementCard()
        objective_lines: list[str] = []
        prose_lines, _tables = partition_intake_tables(initial_request)

        for raw_line in prose_lines:
            line = raw_line.strip()
            if not line:
                continue

            matched = False
            for pattern, field_name in _LINE_PATTERNS:
                match = pattern.match(line)
                if match is None:
                    continue
                value = match.group(1).strip()
                self._assign(card, field_name, value)
                matched = True
                break

            if not matched:
                objective_lines.append(line)

        if not card.task_identity.objective and objective_lines:
            card.task_identity.objective = " ".join(objective_lines).strip()

        lowered = initial_request.lower()
        if not card.task_identity.task_type:
            if re.search(r"\b(test|pytest|unit test|coverage)\b", lowered):
                card.task_identity.task_type = "generating tests"
            elif re.search(r"\b(refactor|performance|optimize)\b", lowered):
                card.task_identity.task_type = "refactor legacy code"
            elif re.search(r"\b(debug|bug|fix|error)\b", lowered):
                card.task_identity.task_type = "debugging an issue"
            elif re.search(r"\b(feature|implement|add|endpoint|api)\b", lowered):
                card.task_identity.task_type = "new feature logic"

        if not card.task_identity.environment:
            if re.search(r"\bfastapi\b", lowered) or re.search(r"\bpydantic\b", lowered):
                card.task_identity.environment = (
                    "Python with FastAPI and Pydantic (match request details)"
                )
            elif re.search(r"\btypescript\b", lowered) or re.search(r"\breact\b", lowered):
                card.task_identity.environment = "TypeScript / React (match request details)"
            elif re.search(r"\bpython\b", lowered):
                card.task_identity.environment = "Python (match request details)"

        self._apply_clarity_default(card)
        return card

    def _restore_full_intake_prose(self, card: RequirementCard, initial_request: str) -> None:
        """Keep the full non-table request. LLM/fallback used to cap objective at 500 chars."""
        prose, _tables = partition_intake_tables(initial_request)
        full = _prose_text(prose)
        if not full:
            return
        current = card.task_identity.objective.strip()
        if not current or (full.startswith(current) and len(full) > len(current)):
            card.task_identity.objective = full

    def _apply_tables_from_request(self, card: RequirementCard, initial_request: str) -> None:
        """Keep pasted markdown/TSV tables as whole constraint items, not smashed objective text."""
        _prose, tables = partition_intake_tables(initial_request)
        if not tables:
            return

        objective_prose, tables_in_objective = partition_intake_tables(card.task_identity.objective)
        if tables_in_objective:
            card.task_identity.objective = _prose_text(objective_prose)

        constraints = list(card.task_identity.additional_constraints)
        for table in tables:
            labeled = table if table.startswith("Table:") else f"Table:\n{table}"
            if any(_constraint_contains_table(item, table) for item in constraints):
                continue
            constraints.append(labeled)
        card.task_identity.additional_constraints = constraints

    @staticmethod
    def _apply_clarity_default(card: RequirementCard) -> None:
        if card.optimization_targets.clarity is None:
            card.optimization_targets.clarity = (
                "Prefer explicit operational rules over brevity. Long-horizon prompts may be long."
            )

    def _assign(self, card: RequirementCard, field_name: str, value: str) -> None:
        if field_name in LIST_LEAF_FIELDS:
            if _looks_like_markdown_table(value):
                items = [value.strip()]
            else:
                items = [part.strip() for part in re.split(r"[;\n]|,(?!\s)", value) if part.strip()]
            current: list[str] = list(card.get_leaf(field_name))
            for item in items:
                if item not in current:
                    current.append(item)
            card.set_leaf(field_name, current)
            return

        card.set_leaf(field_name, value)

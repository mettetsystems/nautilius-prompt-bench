from __future__ import annotations

import json

from prompt_piper_api.llm.mock import MockLLMClient
from prompt_piper_api.services.harness_prompt_builder import build_harness_body
from prompt_piper_api.services.requirement_card_extractor import RequirementCardExtractor

_MARKDOWN_REQUEST = """Implement FastAPI routes from this chart.
| Endpoint | Method |
| --- | --- |
| /users | POST |
Match existing service patterns.
"""


def test_rule_based_extract_keeps_markdown_table_in_constraints() -> None:
    card = RequirementCardExtractor(llm=None).extract(_MARKDOWN_REQUEST)

    assert "Implement FastAPI routes from this chart." in card.task_identity.objective
    assert "Match existing service patterns." in card.task_identity.objective
    assert "|" not in card.task_identity.objective
    assert len(card.task_identity.additional_constraints) == 1
    table = card.task_identity.additional_constraints[0]
    assert table.startswith("Table:")
    assert "| Endpoint | Method |" in table
    assert "| /users | POST |" in table

    body = build_harness_body(card)
    assert "| /users | POST |" in body


def test_rule_based_extract_converts_tsv_table() -> None:
    request = "Add these handlers.\nPath\tVerb\n/health\tGET\n/users\tPOST\n"
    card = RequirementCardExtractor(llm=None).extract(request)

    assert card.task_identity.objective == "Add these handlers."
    assert any("| /health | GET |" in item for item in card.task_identity.additional_constraints)


def test_llm_extract_still_preserves_tables_when_model_omits_them() -> None:
    mock = MockLLMClient(
        chat_responder=lambda _messages: json.dumps(
            {
                "task_identity": {
                    "objective": "Implement FastAPI routes from this chart.",
                }
            }
        )
    )
    card = RequirementCardExtractor(mock).extract(_MARKDOWN_REQUEST)

    assert "markdown tables" in mock.chat_calls[0][0].content
    assert "|" not in card.task_identity.objective
    assert any("| /users | POST |" in item for item in card.task_identity.additional_constraints)


def test_llm_extract_does_not_duplicate_table_already_in_constraints() -> None:
    table = "| Endpoint | Method |\n| --- | --- |\n| /users | POST |"
    mock = MockLLMClient(
        chat_responder=lambda _messages: json.dumps(
            {
                "task_identity": {
                    "objective": "Implement FastAPI routes from this chart.",
                    "additional_constraints": [f"Table:\n{table}"],
                }
            }
        )
    )
    card = RequirementCardExtractor(mock).extract(_MARKDOWN_REQUEST)
    assert card.task_identity.additional_constraints == [f"Table:\n{table}"]


_FLOWBPM_REQUEST = """I would like to create a music app called FlowBPM that connects to heartbeats recording devices.
The app should have watch and phone UIs with pause, skip, and rating controls.
Each activity level has a metrics screen and up to 10 saved profiles.

Recommended activity color system

| Mode | Emotional cue | Base / Background | Primary | Secondary | Highlight |
| --- | --- | --- | --- | --- | --- |
| Sleep | safety, darkness, restoration | #090D18 | #53678F | #71658D | #A8B7D8 |
| Flow | immersion, creativity | #171429 | #7865E8 | #B15ED7 | #58C9D7 |

The person can have up to 10 saved profiles per activity level.
"""


def test_table_intake_keeps_full_objective_including_text_after_table() -> None:
    mock = MockLLMClient(
        chat_responder=lambda _messages: json.dumps(
            {
                "task_identity": {
                    "objective": "I would like to create a music app called FlowBPM that connects to heartbeats recording devices.",
                }
            }
        )
    )
    card = RequirementCardExtractor(mock).extract(_FLOWBPM_REQUEST)

    assert "10 saved profiles" in card.task_identity.objective
    assert "watch and phone UIs" in card.task_identity.objective
    assert "|" not in card.task_identity.objective
    assert any("#090D18" in item for item in card.task_identity.additional_constraints)
    assert any("| Sleep |" in item for item in card.task_identity.additional_constraints)


def test_assign_keeps_markdown_table_as_one_constraint() -> None:
    table = (
        "Table:\n"
        "| Mode | Primary |\n"
        "| --- | --- |\n"
        "| Sleep | #090D18 |\n"
        "| Flow | #7865E8 |"
    )
    card = RequirementCardExtractor(llm=None).extract("Build the theme system.")
    RequirementCardExtractor(llm=None)._assign(
        card, "task_identity.additional_constraints", table
    )
    assert card.task_identity.additional_constraints == [table]

from prompt_piper_api.domain.harness import HARNESS_SECTION_TITLES, HARNESS_SYSTEM_PROMPT
from prompt_piper_api.services.api_pack_export import build_api_pack
from prompt_piper_api.services.format_checker import format_adherence_score, harness_section_coverage
from prompt_piper_api.services.harness_prompt_builder import build_harness_body
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from tests.card_fixtures import sample_card


def _card():
    return sample_card()


def test_harness_body_covers_task_contract_sections() -> None:
    body = build_harness_body(_card())
    for title in HARNESS_SECTION_TITLES:
        assert title in body
    assert "Role: long-horizon coding agent" in body
    assert "Python 3.12" in body
    assert "Definition of Done" in body
    assert harness_section_coverage(body) == len(HARNESS_SECTION_TITLES)
    assert format_adherence_score(body) == 1.0


def test_optimizer_emits_clarity_contract_not_compressed_five_principles() -> None:
    card = _card()
    draft = build_harness_body(card)
    result = TokenOptimizationEngine().optimize(draft, card)
    body = result.optimized_body
    assert "Task Identity" in body
    assert "Definition of Done" in body
    assert "Long-Horizon Coding Agent Contract" in body
    assert "Role and Objective" not in body
    assert format_adherence_score(body) == 1.0
    assert result.metrics.targets.clarity >= 0.5


def test_api_pack_includes_hybrid_six_formats() -> None:
    pack = build_api_pack(_card())
    assert "harness_prompt.md" in pack
    assert "harness_prompt.txt" in pack
    assert "coding_harness_spec.json" in pack
    assert pack["api_pack/openai_chat_completions.json"]["messages"][0]["content"] == (
        HARNESS_SYSTEM_PROMPT
    )
    assert pack["api_pack/anthropic_messages.json"]["system"] == HARNESS_SYSTEM_PROMPT
    assert "parts" in pack["api_pack/gemini_generate_content.json"]["systemInstruction"]
    assert "rules_markdown" in pack["api_pack/cursor_agent.json"]
    assert "instructions_markdown" in pack["api_pack/copilot_instructions.json"]
    assert "systemMessage" in pack["api_pack/continue_config.json"]
    assert "api_pack/cursor_rules.md" in pack
    assert "api_pack/copilot_instructions.md" in pack
    assert "api_pack/continue_system.md" in pack

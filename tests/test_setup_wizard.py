from pathlib import Path

import pytest
from prompt_piper.setup.env_writer import upsert_env_section
from prompt_piper.setup.wizard import run_setup_wizard


def test_upsert_env_section_replaces_wizard_block(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "API_PORT=8000\n"
        "# --- Local LLM (Nautilius Prompting Workbench setup wizard) ---\n"
        "PROMPT_PIPER_LLM_ENABLED=true\n"
        "PROMPT_PIPER_LOCAL_CHAT_MODEL=old\n"
        "# --- End local LLM setup ---\n"
        "VITE_API_BASE_URL=http://127.0.0.1:8000\n",
        encoding="utf-8",
    )

    upsert_env_section(
        env_path,
        {
            "PROMPT_PIPER_LLM_ENABLED": "false",
            "PROMPT_PIPER_LOCAL_MODEL_PRESET": "cpu-only",
        },
    )

    text = env_path.read_text(encoding="utf-8")
    assert "API_PORT=8000" in text
    assert "VITE_API_BASE_URL=http://127.0.0.1:8000" in text
    assert "PROMPT_PIPER_LLM_ENABLED=false" in text
    assert "PROMPT_PIPER_LOCAL_MODEL_PRESET=cpu-only" in text
    assert "PROMPT_PIPER_LOCAL_CHAT_MODEL=old" not in text
    assert text.count("# --- Local LLM (Nautilius Prompting Workbench setup wizard) ---") == 1


def test_run_setup_wizard_cpu_only_non_interactive(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("API_PORT=8000\n", encoding="utf-8")

    result = run_setup_wizard(
        env_path=env_path,
        non_interactive="cpu-only",
        print_fn=lambda _: None,
    )

    assert result.cpu_only is True
    text = env_path.read_text(encoding="utf-8")
    assert "PROMPT_PIPER_LLM_ENABLED=false" in text
    assert "PROMPT_PIPER_LOCAL_MODEL_PRESET=cpu-only" in text


def test_run_setup_wizard_gemma_preset_non_interactive(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("API_PORT=8000\n", encoding="utf-8")

    result = run_setup_wizard(
        env_path=env_path,
        non_interactive="native:gemma3-1b",
        print_fn=lambda _: None,
    )

    assert result.cpu_only is False
    assert result.preset_id == "gemma3-1b"
    assert result.base_url == "http://127.0.0.1:8080/v1"
    text = env_path.read_text(encoding="utf-8")
    assert "PROMPT_PIPER_LLM_ENABLED=true" in text
    assert "PROMPT_PIPER_LOCAL_CHAT_MODEL=gemma-3-1b-it-qat-q4_0-gguf" in text
    assert "PROMPT_PIPER_LOCAL_MODEL_GGUF_REPO=google/gemma-3-1b-it-qat-q4_0-gguf" in text
    assert "PROMPT_PIPER_LOCAL_MODEL_GGUF_FILE=gemma-3-1b-it-q4_0.gguf" in text
    assert "huggingface_hub[cli]" in text
    assert "hf auth login" in text
    assert "hf download google/gemma-3-1b-it-qat-q4_0-gguf" in text


def test_all_catalog_presets_use_official_huggingface_publishers() -> None:
    from prompt_piper.setup.catalog import (
        GEMMA3N_PRESETS,
        GEMMA3_PRESETS,
        QWEN3_PRESETS,
        is_official_hf_repo,
    )

    for preset in (*GEMMA3_PRESETS, *QWEN3_PRESETS):
        assert is_official_hf_repo(preset.huggingface_gguf_repo)
        assert preset.publisher in {"google", "Qwen"}
        assert preset.community_gguf is False

    for preset in GEMMA3N_PRESETS:
        assert preset.community_gguf is True
        assert preset.weights_repo is not None
        assert preset.weights_repo.startswith("google/")


def test_run_setup_wizard_qwen3_8b_non_interactive(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("API_PORT=8000\n", encoding="utf-8")

    result = run_setup_wizard(
        env_path=env_path,
        non_interactive="native:qwen3-8b",
        print_fn=lambda _: None,
    )

    assert result.preset_id == "qwen3-8b"
    text = env_path.read_text(encoding="utf-8")
    assert "Qwen/Qwen3-8B-GGUF" in text
    assert "Qwen3-8B-Q4_K_M.gguf" in text


def test_run_setup_wizard_gemma3n_e4b_non_interactive(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("API_PORT=8000\n", encoding="utf-8")

    result = run_setup_wizard(
        env_path=env_path,
        non_interactive="gemma3n-e4b",
        print_fn=lambda _: None,
    )

    assert result.preset_id == "gemma3n-e4b"
    text = env_path.read_text(encoding="utf-8")
    assert "bartowski/google_gemma-3n-E4B-it-GGUF" in text
    assert "google/gemma-3n-E4B-it" in text


def test_recommended_tier_from_vram() -> None:
    from prompt_piper.setup.catalog import ModelTier
    from prompt_piper.setup.gpu_detect import recommended_tier

    assert recommended_tier(4096) == ModelTier.COMPACT
    assert recommended_tier(8192) == ModelTier.STANDARD
    assert recommended_tier(24576) == ModelTier.PROSUMER
    assert recommended_tier(None) == ModelTier.STANDARD


def test_hf_cli_install_lines_include_hf_commands() -> None:
    from prompt_piper.setup.model_deps import hf_cli_install_lines

    lines = hf_cli_install_lines()
    assert any("huggingface_hub[cli]" in line for line in lines)
    assert any("hf auth login" in line for line in lines)
    assert any("hf download" in line for line in lines)


def test_run_setup_wizard_podman_qwen_preset(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("API_PORT=8000\n", encoding="utf-8")

    result = run_setup_wizard(
        env_path=env_path,
        non_interactive="podman:qwen3-1.5b",
        print_fn=lambda _: None,
    )

    assert result.base_url == "http://host.containers.internal:8080/v1"
    assert result.chat_model == "qwen3-1.7b"


def test_run_setup_wizard_unknown_preset_raises(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    with pytest.raises(ValueError, match="Unknown preset"):
        run_setup_wizard(env_path=env_path, non_interactive="not-a-preset", print_fn=lambda _: None)


def test_qwen3_14b_setup(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    result = run_setup_wizard(env_path=env_path, non_interactive="native:qwen3-14b", print_fn=lambda _: None)
    assert result.preset_id == "qwen3-14b"
    assert "Qwen/Qwen3-14B-GGUF" in env_path.read_text()
    assert "Qwen3-14B-Q4_K_M.gguf" in env_path.read_text()

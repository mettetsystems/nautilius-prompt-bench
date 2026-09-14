from unittest.mock import patch

import pytest
from prompt_piper.setup.clarification_model import configure_clarification_model
from prompt_piper_api.config import get_settings
from prompt_piper_api.llm.factory import create_clarification_client


@pytest.mark.parametrize("answers, model, enabled", [
    (["", ""], "DeepSeek-R1-Distill-Qwen-32B", True),
    (["2", ""], "qwen3-14b", True),
    (["3", "my-model", "http://localhost:9000/v1"], "my-model", True),
    (["4"], "DeepSeek-R1-Distill-Qwen-32B", False),
])
def test_install_selection_preserves_lightweight_configuration(tmp_path, answers, model, enabled):
    path = tmp_path / ".env"
    path.write_text("PROMPT_PIPER_LOCAL_CHAT_MODEL=qwen3-0.6b\n")
    choices = iter(answers)
    with patch("prompt_piper.setup.clarification_model.detect_gpu", return_value=None):
        configure_clarification_model(path, read=lambda _: next(choices), write=lambda _: None)
    text = path.read_text()
    assert "PROMPT_PIPER_LOCAL_CHAT_MODEL=qwen3-0.6b" in text
    assert f"PROMPT_PIPER_CLARIFICATION_MODEL={model}" in text
    assert f"PROMPT_PIPER_CLARIFICATION_ENABLED={str(enabled).lower()}" in text


def test_dedicated_model_defaults_and_manual_fallback(monkeypatch):
    monkeypatch.setenv("PROMPT_PIPER_CLARIFICATION_ENABLED", "false")
    get_settings.cache_clear()
    assert create_clarification_client() is None
    monkeypatch.setenv("PROMPT_PIPER_CLARIFICATION_ENABLED", "true")
    monkeypatch.setenv("PROMPT_PIPER_CLARIFICATION_MODEL", "DeepSeek-R1-Distill-Qwen-32B")
    monkeypatch.setenv("PROMPT_PIPER_CLARIFICATION_BASE_URL", "http://127.0.0.1:8081/v1")
    get_settings.cache_clear()
    client = create_clarification_client()
    assert client.settings.model_name == "DeepSeek-R1-Distill-Qwen-32B"
    assert client.settings.base_url == "http://127.0.0.1:8081/v1"
    assert client.settings.temperature == 0.6
    assert client.timeout == 180

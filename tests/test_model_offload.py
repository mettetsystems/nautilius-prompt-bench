from unittest.mock import patch


def test_offload_rejects_unmanaged_server(client):
    with patch("prompt_piper.setup.llama_launcher.read_managed_pid", return_value=None), patch("prompt_piper.setup.llama_launcher.stop_managed_server") as stop:
        assert client.post("/health/llm/offload").status_code == 409
        stop.assert_not_called()


def test_offload_stops_server_and_disables_assistance(client, monkeypatch):
    from pathlib import Path
    from prompt_piper_api.config import get_settings
    monkeypatch.setenv("PROMPT_PIPER_LLM_ENABLED", "true")
    with patch("prompt_piper.setup.llama_launcher.read_managed_pid", return_value=123), patch("pathlib.Path.resolve", return_value=Path("/usr/bin/llama-server")), patch("prompt_piper.setup.llama_launcher.stop_managed_server", return_value=True) as stop:
        response = client.post("/health/llm/offload")
        assert response.status_code == 200
        stop.assert_called_once()
    assert not get_settings().prompt_piper_llm_enabled

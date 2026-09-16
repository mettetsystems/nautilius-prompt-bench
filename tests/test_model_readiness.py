import httpx
import pytest
from prompt_piper.setup.readiness import probe_inference


@pytest.mark.parametrize("payload,expected", [
    ({"choices": [{"message": {"content": "ready"}}]}, True),
    ({"choices": [{"message": {"content": ""}}]}, False),
    ({"data": [{"id": "model"}]}, False),
    ({"choices": []}, False),
])
def test_requires_actual_completion(monkeypatch, payload, expected):
    def post(self, url, **kwargs):
        assert kwargs["json"]["model"] == "selected-model"
        assert kwargs["headers"]["Authorization"] == "Bearer secret"
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.Client, "post", post)
    assert probe_inference("http://localhost:8080/v1", "selected-model", "secret")[0] is expected


def test_remote_failure_blocks_startup(tmp_path, monkeypatch):
    from prompt_piper.setup import ensure_llm
    monkeypatch.setenv("PROMPT_PIPER_LLM_ENABLED", "true")
    env = tmp_path / ".env"
    env.write_text("PROMPT_PIPER_LLM_ENABLED=true\nPROMPT_PIPER_AUTO_START_LLM=false\n")
    monkeypatch.setattr(ensure_llm, "probe_inference", lambda *a, **k: (False, "inference failed"))
    assert ensure_llm.main(["--env-file", str(env), "--strict"]) == 1


def test_retries_loading_503(monkeypatch):
    from prompt_piper.setup import readiness
    calls = []
    def post(self, url, **kwargs):
        calls.append(url)
        return httpx.Response(503 if len(calls) == 1 else 200,
            json={"choices": [{"message": {"content": "ready"}}]},
            request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.Client, "post", post)
    monkeypatch.setattr(readiness.time, "sleep", lambda _: None)
    assert probe_inference("http://localhost/v1", "model", wait_seconds=10)[0]
    assert len(calls) == 2


def test_no_retry_for_credentials(monkeypatch):
    def post(self, url, **kwargs):
        return httpx.Response(401, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.Client, "post", post)
    ok, message = probe_inference("http://localhost/v1", "model", wait_seconds=10)
    assert not ok and "401" in message


@pytest.mark.parametrize("output,vendor,expected", [
    ("Available devices:\n CUDA0: NVIDIA RTX 5090", "nvidia", True),
    ("Available devices:\n (none)", "nvidia", False),
    ("Available devices:\n ROCm0: AMD", "nvidia", False),
])
def test_gpu_backend_matches_hardware(monkeypatch, output, vendor, expected):
    import subprocess
    from pathlib import Path
    from prompt_piper.setup.llama_launcher import supports_gpu
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=output))
    assert supports_gpu(Path("llama-server"), vendor) is expected

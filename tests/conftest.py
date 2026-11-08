from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def isolate_model_endpoint_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setup/startup tests must never depend on or contact the developer's models."""
    monkeypatch.setattr("prompt_piper.setup.wizard.discover_endpoints", lambda _: [])
    monkeypatch.setattr("prompt_piper.setup.wizard.probe_endpoint", lambda *a, **k: None)
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.discover_endpoints", lambda _: [])
    monkeypatch.setattr("prompt_piper.setup.ensure_llm.port_is_listening", lambda _: False)
    monkeypatch.setattr("prompt_piper.setup.preferred_endpoint.probe_endpoint", lambda *a, **k: None)
    monkeypatch.setattr("prompt_piper.setup.preferred_endpoint.port_is_listening", lambda _: False)
    # ensure_llm changes process env; restore it between tests, including failure paths.
    monkeypatch.setenv("PROMPT_PIPER_LLM_ENABLED", "true")
    for key in (
        "PROMPT_PIPER_LOCAL_BASE_URL", "PROMPT_PIPER_LOCAL_CHAT_MODEL",
        "PROMPT_PIPER_LOCAL_EMBED_MODEL", "PROMPT_PIPER_LOCAL_API_KEY",
        "PROMPT_PIPER_LOCAL_MODEL_PRESET", "PROMPT_PIPER_DEPLOYMENT_PROFILE",
        "PROMPT_PIPER_AUTO_START_LLM", "PROMPT_PIPER_PREFER_MAYA",
        "PROMPT_PIPER_MAYA_BASE_URL", "PROMPT_PIPER_MAYA_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def isolate_documents_export_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests off ~/Documents/Nautilius unless a test overrides paths explicitly."""
    export_root = tmp_path / "prompt-piper-export"
    monkeypatch.setenv("PROMPT_PIPER_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("PROMPT_PIPER_HOST_EXPORT_ROOT", str(export_root))
    monkeypatch.setenv("REGISTRY_PATH", str(export_root / "registry"))
    monkeypatch.setenv("ARTIFACTS_PATH", str(export_root / "exports"))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(export_root / "audit"))
    monkeypatch.setenv("SESSIONS_PATH", str(tmp_path / "sessions"))
    monkeypatch.setenv("USER_SETTINGS_PATH", str(tmp_path / "user_settings.json"))

    from prompt_piper_api.config import get_settings
    from prompt_piper_api.services.user_settings_service import clear_user_settings_cache

    get_settings.cache_clear()
    clear_user_settings_cache()

    try:
        from prompt_piper_api.routes import sessions as sessions_routes

        sessions_routes._session_service = None
    except ImportError:
        pass

    yield
    get_settings.cache_clear()
    clear_user_settings_cache()

    try:
        from prompt_piper_api.routes import sessions as sessions_routes

        sessions_routes._session_service = None
    except ImportError:
        pass

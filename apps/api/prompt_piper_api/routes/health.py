from fastapi import APIRouter

from prompt_piper_api import __version__
from prompt_piper_api.config import Settings, get_settings
from prompt_piper_api.domain.user_settings import UserSettings
from prompt_piper_api.llm.factory import create_llm_client_from_env, load_local_chat_settings
from prompt_piper_api.schemas.health import HealthResponse, LlmHealthResponse, utc_now
from prompt_piper_api.services.user_settings_service import get_user_settings_service

router = APIRouter(tags=["health"])


def _disabled_llm_message(settings: Settings, prefs: UserSettings) -> str:
    """Explain why the health probe reports LLM disabled."""
    if not settings.prompt_piper_llm_enabled:
        return (
            "Local LLM is disabled in this API process (PROMPT_PIPER_LLM_ENABLED=false). "
            "make dev-api runs ensure_llm, which turns the chat model off when no CUDA/ROCm "
            "GPU is available or llama-server could not be started — even if .env still lists "
            f"{settings.prompt_piper_local_chat_model}. "
            "Fix: start the model server at "
            f"{settings.prompt_piper_local_base_url} yourself, then restart make dev-api; "
            "or install GPU drivers and restart so ensure_llm can launch llama-server."
        )
    if not prefs.llm_enabled:
        return "AI assistance is turned off in Settings (Enable AI assistance)."
    return "Local LLM disabled (CPU-only / rule-based mode)."


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()
    database = "sqlite" if settings.is_sqlite else "postgresql"
    return HealthResponse(
        status="ok",
        service="prompt-piper-api",
        version=__version__,
        timestamp=utc_now(),
        database=database,
    )


@router.get("/health/llm", response_model=LlmHealthResponse)
def llm_health_check() -> LlmHealthResponse:
    settings = get_settings()
    user_settings = get_user_settings_service()
    prefs = user_settings.load()
    if not user_settings.is_llm_enabled(settings):
        chat_settings = load_local_chat_settings(settings)
        return LlmHealthResponse(
            llm_enabled=False,
            status="disabled",
            endpoint=chat_settings.base_url,
            model_name=chat_settings.model_name,
            message=_disabled_llm_message(settings, prefs),
            checked_at=utc_now(),
        )

    chat_settings = load_local_chat_settings(settings)
    client = create_llm_client_from_env()
    if client is None:
        return LlmHealthResponse(
            llm_enabled=False,
            status="disabled",
            endpoint=chat_settings.base_url,
            model_name=chat_settings.model_name,
            message="LLM client not configured.",
            checked_at=utc_now(),
        )

    probe = client.health_check()
    return LlmHealthResponse(
        llm_enabled=True,
        status="ok" if probe.ok else "unreachable",
        endpoint=chat_settings.base_url,
        model_name=probe.model_name or chat_settings.model_name,
        message=probe.message,
        checked_at=utc_now(),
    )


@router.post("/health/llm/offload")
def offload_llm() -> dict[str, str]:
    """Release the local chat model's memory without deleting its downloaded weights."""
    import os
    from pathlib import Path

    from fastapi import HTTPException
    from prompt_piper.setup.llama_launcher import read_managed_pid, stop_managed_server
    from prompt_piper_api.llm.factory import clear_llm_client_cache

    pid = read_managed_pid()
    if pid is None:
        raise HTTPException(409, "No managed model server. Stop externally hosted models in their host application.")
    # A stale PID file must never stop an unrelated process.
    try:
        executable = Path(f"/proc/{pid}/exe").resolve(strict=True).name
    except OSError:
        raise HTTPException(409, "Managed model server is no longer running.") from None
    if executable not in {"llama-server", "llama-server-bin"}:
        raise HTTPException(409, "Cannot verify the managed model server process.")
    if not stop_managed_server():
        raise HTTPException(409, "No managed model server is running.")
    os.environ["PROMPT_PIPER_LLM_ENABLED"] = "false"
    get_settings.cache_clear()
    clear_llm_client_cache()
    return {"message": "Model offloaded. CPU mode is active. Restart the app to load the configured model again."}


@router.get("/health/hardware")
def hardware_capabilities() -> dict:
    """Read-only scan; no model downloads, process starts, or setting changes."""
    from prompt_piper.setup.hardware import scan_hardware
    return scan_hardware()

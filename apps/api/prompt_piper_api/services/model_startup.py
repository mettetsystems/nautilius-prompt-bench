"""Apply the running Maya endpoint as the API's process-local model default."""

import logging
import os

from prompt_piper.setup.preferred_endpoint import select_preferred_endpoint

from prompt_piper_api.config import get_settings
from prompt_piper_api.llm.factory import clear_llm_client_cache

logger = logging.getLogger(__name__)


def configure_preferred_endpoint() -> None:
    """Called before serving requests, including direct Uvicorn/container launches.

    No model processes, downloads, inference calls, or saved settings are changed.
    Explicit UI tooling overrides still take precedence in the LLM factory.
    """
    settings = get_settings()
    names = (
        "PROMPT_PIPER_LLM_ENABLED",
        "PROMPT_PIPER_LOCAL_MODEL_PRESET",
        "PROMPT_PIPER_LOCAL_BASE_URL",
        "PROMPT_PIPER_LOCAL_CHAT_MODEL",
        "PROMPT_PIPER_LOCAL_API_KEY",
        "PROMPT_PIPER_PREFER_MAYA",
        "PROMPT_PIPER_MAYA_BASE_URL",
        "PROMPT_PIPER_MAYA_API_KEY",
    )
    values = settings.model_dump(by_alias=True, include={name.lower() for name in names})
    preferred = select_preferred_endpoint(
        {name: str(value) for name, value in values.items() if value is not None}
    )
    if preferred is None:
        return
    os.environ.update(preferred.environment())
    get_settings.cache_clear()
    clear_llm_client_cache()
    logger.info(preferred.message)

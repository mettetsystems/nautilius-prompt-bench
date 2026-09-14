from fastapi import APIRouter, Depends

from prompt_piper_api.config import Settings, get_settings
from prompt_piper_api.schemas.inference import InferenceSettingsResponse, to_inference_settings
from prompt_piper_api.schemas.user_settings import (
    UserSettingsResponse,
    UserSettingsUpdateRequest,
    to_user_settings,
    to_user_settings_response,
)
from prompt_piper_api.services.user_settings_service import UserSettingsService, get_user_settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


def get_user_settings_service_dep() -> UserSettingsService:
    return get_user_settings_service()


@router.get("/inference", response_model=InferenceSettingsResponse)
def get_inference_settings(
    settings: Settings = Depends(get_settings),
    user_settings: UserSettingsService = Depends(get_user_settings_service_dep),
) -> InferenceSettingsResponse:
    response = to_inference_settings(settings, user_settings=user_settings)
    return response


@router.get("/user", response_model=UserSettingsResponse)
def get_user_settings(
    settings: Settings = Depends(get_settings),
    user_settings: UserSettingsService = Depends(get_user_settings_service_dep),
) -> UserSettingsResponse:
    return to_user_settings_response(user_settings.load(), settings)


@router.put("/user", response_model=UserSettingsResponse)
def update_user_settings(
    payload: UserSettingsUpdateRequest,
    settings: Settings = Depends(get_settings),
    user_settings: UserSettingsService = Depends(get_user_settings_service_dep),
) -> UserSettingsResponse:
    saved = user_settings.update(to_user_settings(payload))
    return to_user_settings_response(saved, settings)


from pydantic import BaseModel, SecretStr


class ModelSourceUpdate(BaseModel):
    hf_token: SecretStr | None = None
    local_repo: str | None = None
    clear_token: bool = False


@router.get("/model-source")
def get_model_source() -> dict:
    from prompt_piper.setup.model_sources import public_preferences
    return public_preferences()


@router.put("/model-source")
def update_model_source(payload: ModelSourceUpdate) -> dict:
    from fastapi import HTTPException
    from prompt_piper.setup.model_sources import save_preferences
    try:
        return save_preferences(hf_token=payload.hf_token.get_secret_value() if payload.hf_token else None,
                                local_repo=payload.local_repo, clear_token=payload.clear_token)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None

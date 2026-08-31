from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from prompt_piper_api import __version__
from prompt_piper_api.api.exception_handlers import register_exception_handlers
from prompt_piper_api.config import get_settings
from prompt_piper_api.db import init_db
from prompt_piper_api.routes import health_router, registry_router, sessions_router, settings_router
from prompt_piper_api.services.logging_config import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    for path in (
        settings.registry_path,
        settings.artifacts_path,
        settings.audit_log_path,
        settings.sessions_path,
        settings.prompt_piper_model_cache,
    ):
        path.mkdir(parents=True, exist_ok=True)
    if settings.is_sqlite and settings.sqlite_path is not None:
        settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Nautilius Prompting Workbench API",
        description="Local-first prompt engineering workbench",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5174",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(registry_router)
    app.include_router(settings_router)

    return app


app = create_app()

import os
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from prompt_piper_api.llm.enums import ModelProfile


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _expand_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = _repo_root() / path
    return path


def _env_var_configured(name: str) -> bool:
    """True when a variable is set in the process env or repo .env file."""
    if name in os.environ:
        return True
    env_file = _repo_root() / ".env"
    if not env_file.is_file():
        return False
    prefix = f"{name}="
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(prefix):
            return True
    return False


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=_repo_root() / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8010, alias="API_PORT")

    database_url: str = Field(
        default="sqlite:///./data/prompt_piper.db",
        alias="DATABASE_URL",
    )

    prompt_piper_clarification_base_url: str = Field(
        default="http://127.0.0.1:8081/v1", alias="PROMPT_PIPER_CLARIFICATION_BASE_URL",
    )
    prompt_piper_clarification_model: str = Field(
        default="DeepSeek-R1-Distill-Qwen-32B", alias="PROMPT_PIPER_CLARIFICATION_MODEL",
    )
    prompt_piper_clarification_enabled: bool = Field(
        default=False, alias="PROMPT_PIPER_CLARIFICATION_ENABLED",
    )
    prompt_piper_clarification_timeout: float = Field(
        default=180, ge=1, le=600, alias="PROMPT_PIPER_CLARIFICATION_TIMEOUT",
    )

    prompt_piper_export_root: Path = Field(
        default_factory=lambda: Path.home() / "Documents" / "Nautilius",
        alias="PROMPT_PIPER_EXPORT_ROOT",
    )
    prompt_piper_host_export_root: Path = Field(
        default_factory=lambda: Path.home() / "Documents" / "Nautilius",
        alias="PROMPT_PIPER_HOST_EXPORT_ROOT",
    )
    prompt_piper_registry_root: Path | None = Field(
        default=None,
        alias="PROMPT_PIPER_REGISTRY_ROOT",
    )
    prompt_piper_artifact_root: Path | None = Field(
        default=None,
        alias="PROMPT_PIPER_ARTIFACT_ROOT",
    )
    prompt_piper_model_cache: Path = Field(
        default=Path("./data/model-cache"),
        alias="PROMPT_PIPER_MODEL_CACHE",
    )

    registry_path: Path = Field(default=Path("./data/registry"), alias="REGISTRY_PATH")
    artifacts_path: Path = Field(default=Path("./data/artifacts"), alias="ARTIFACTS_PATH")
    audit_log_path: Path = Field(default=Path("./data/audit"), alias="AUDIT_LOG_PATH")
    sessions_path: Path = Field(default=Path("./data/sessions"), alias="SESSIONS_PATH")
    user_settings_path: Path = Field(
        default=Path("./data/user_settings.json"),
        alias="USER_SETTINGS_PATH",
    )
    lexicon_vector_index_path: Path = Field(
        default=Path("./data/lexicon/precision_vectors.json"),
        alias="LEXICON_VECTOR_INDEX_PATH",
    )

    prompt_piper_local_base_url: str = Field(
        default="http://127.0.0.1:8080/v1",
        alias="PROMPT_PIPER_LOCAL_BASE_URL",
    )
    prompt_piper_local_chat_model: str = Field(
        default="llama",
        alias="PROMPT_PIPER_LOCAL_CHAT_MODEL",
    )
    prompt_piper_local_embed_model: str = Field(
        default="llama",
        alias="PROMPT_PIPER_LOCAL_EMBED_MODEL",
    )
    prompt_piper_local_api_key: str | None = Field(default=None, alias="PROMPT_PIPER_LOCAL_API_KEY")
    prompt_piper_external_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "PROMPT_PIPER_EXTERNAL_ENABLED",
            "PROMPT_PIPER_EXTERNAL_INFERENCE_ENABLED",
        ),
        alias="PROMPT_PIPER_EXTERNAL_ENABLED",
    )
    prompt_piper_external_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="PROMPT_PIPER_EXTERNAL_BASE_URL",
    )
    prompt_piper_external_chat_model: str = Field(
        default="gpt-4o-mini",
        alias="PROMPT_PIPER_EXTERNAL_CHAT_MODEL",
    )
    prompt_piper_external_embed_model: str = Field(
        default="text-embedding-3-small",
        alias="PROMPT_PIPER_EXTERNAL_EMBED_MODEL",
    )
    prompt_piper_external_api_key: str | None = Field(
        default=None,
        alias="PROMPT_PIPER_EXTERNAL_API_KEY",
    )
    prompt_piper_llm_enabled: bool = Field(default=True, alias="PROMPT_PIPER_LLM_ENABLED")
    prompt_piper_model_profile: ModelProfile = Field(
        default=ModelProfile.COMPATIBILITY,
        alias="PROMPT_PIPER_MODEL_PROFILE",
    )
    prompt_piper_llm_timeout_seconds: float = Field(
        default=120.0,
        ge=5.0,
        alias="PROMPT_PIPER_LLM_TIMEOUT_SECONDS",
    )
    prompt_piper_local_model_preset: str | None = Field(
        default=None,
        alias="PROMPT_PIPER_LOCAL_MODEL_PRESET",
    )
    prompt_piper_allow_cpu_llm: bool = Field(
        default=False,
        alias="PROMPT_PIPER_ALLOW_CPU_LLM",
    )

    prompt_piper_embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5",
        alias="PROMPT_PIPER_EMBEDDING_MODEL",
    )
    prompt_piper_embedding_fallback: bool = Field(
        default=False,
        alias="PROMPT_PIPER_EMBEDDING_FALLBACK",
    )
    prompt_piper_embedding_device: str = Field(
        default="cpu",
        alias="PROMPT_PIPER_EMBEDDING_DEVICE",
    )
    similarity_index_path: Path | None = Field(default=None, alias="SIMILARITY_INDEX_PATH")
    similarity_warning_threshold: float = Field(default=0.90, alias="SIMILARITY_WARNING_THRESHOLD")

    require_approval_before_external_call: bool = Field(
        default=True,
        alias="REQUIRE_APPROVAL_BEFORE_EXTERNAL_CALL",
    )

    @field_validator("require_approval_before_external_call")
    @classmethod
    def approval_must_remain_required(cls, value: bool) -> bool:
        if not value:
            msg = "require_approval_before_external_call cannot be disabled in v1."
            raise ValueError(msg)
        return value

    @property
    def external_inference_enabled(self) -> bool:
        return self.prompt_piper_external_enabled

    @field_validator(
        "prompt_piper_export_root",
        "prompt_piper_host_export_root",
        "prompt_piper_registry_root",
        "prompt_piper_artifact_root",
        "prompt_piper_model_cache",
        "registry_path",
        "artifacts_path",
        "audit_log_path",
        "sessions_path",
        "user_settings_path",
        "lexicon_vector_index_path",
        mode="before",
    )
    @classmethod
    def resolve_path(cls, value: str | Path | None) -> Path | None:
        if value is None or value == "":
            return None
        return _expand_path(value)

    @model_validator(mode="after")
    def wire_documents_export_layout(self) -> Self:
        export_root = self.prompt_piper_export_root
        host_root = self.prompt_piper_host_export_root
        registry_root = self.prompt_piper_registry_root or (export_root / "registry")
        artifact_root = self.prompt_piper_artifact_root or (export_root / "exports")
        audit_root = export_root / "audit"

        export_layout_requested = (
            os.getenv("PROMPT_PIPER_EXPORT_ROOT") is not None
            or os.getenv("PROMPT_PIPER_REGISTRY_ROOT") is not None
            or os.getenv("PROMPT_PIPER_ARTIFACT_ROOT") is not None
            or _env_var_configured("PROMPT_PIPER_EXPORT_ROOT")
            or _env_var_configured("PROMPT_PIPER_REGISTRY_ROOT")
            or _env_var_configured("PROMPT_PIPER_ARTIFACT_ROOT")
        )
        if not export_layout_requested:
            return self

        if os.getenv("REGISTRY_PATH") is None:
            object.__setattr__(self, "registry_path", registry_root)
        if os.getenv("ARTIFACTS_PATH") is None:
            object.__setattr__(self, "artifacts_path", artifact_root)
        if os.getenv("AUDIT_LOG_PATH") is None:
            object.__setattr__(self, "audit_log_path", audit_root)

        object.__setattr__(self, "prompt_piper_export_root", export_root)
        object.__setattr__(self, "prompt_piper_host_export_root", host_root)
        object.__setattr__(self, "prompt_piper_registry_root", registry_root)
        object.__setattr__(self, "prompt_piper_artifact_root", artifact_root)
        return self

    @field_validator("similarity_index_path", mode="before")
    @classmethod
    def resolve_optional_path(cls, value: str | Path | None) -> Path | None:
        if value is None or value == "":
            return None
        path = Path(value)
        if not path.is_absolute():
            path = _repo_root() / path
        return path

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def sqlite_path(self) -> Path | None:
        if not self.is_sqlite:
            return None
        # sqlite:///./data/prompt_piper.db -> ./data/prompt_piper.db
        raw = self.database_url.removeprefix("sqlite:///")
        path = Path(raw)
        if not path.is_absolute():
            path = _repo_root() / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from prompt_piper_api.domain.requirement_card import RequirementCard


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


class RegistryLineageEntry(BaseModel):
    """Reference to a prior prompt that influenced this registry record."""

    prompt_id: str
    version: int = Field(ge=1)
    relationship: str = Field(
        description="How this record relates to the ancestor, e.g. derived_from or forked_from.",
    )


class RegistryMetadata(BaseModel):
    """Human-readable metadata written to metadata.yaml in the registry."""

    prompt_id: str
    version: int = Field(ge=1)
    title: str
    abstract: str = ""
    tags: list[str] = Field(default_factory=list)
    domain: str = ""
    task_family: str = ""
    output_form: str = ""
    target_provider: str = ""
    target_model: str = ""
    preferred_prompt_length: str = ""
    evaluation_scores: dict[str, float] = Field(default_factory=dict)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RegistryLineageFile(BaseModel):
    """Lineage references stored in lineage.json."""

    lineage: list[RegistryLineageEntry] = Field(default_factory=list)
    source_session_id: str | None = None


class PromptRegistryRecord(BaseModel):
    """Metadata for a finalized prompt stored in the local install registry."""

    prompt_id: str = Field(description="Stable identifier used in data/registry paths.")
    version: int = Field(ge=1, description="Immutable registry version number.")
    title: str
    abstract: str = Field(default="", description="Short summary for search and browsing.")
    tags: list[str] = Field(default_factory=list)
    domain: str = Field(default="", description="Subject domain, e.g. legal, engineering.")
    task_family: str = Field(
        default="",
        description="Broad task category, e.g. summarization, extraction.",
    )
    output_form: str = Field(
        default="",
        description="Expected output format, e.g. markdown table, JSON schema.",
    )
    target_provider: str = Field(default="", description="Optional provider hint for dispatch.")
    target_model: str = Field(default="", description="Optional model hint for dispatch.")
    preferred_prompt_length: str = Field(
        default="",
        description="Guidance such as short, medium, or explicit token budget.",
    )
    requirement_card: RequirementCard = Field(default_factory=RequirementCard)
    canonical_prompt_path: str = Field(
        description="Relative path to the canonical prompt body in data/registry.",
    )
    artifact_paths: dict[str, str] = Field(
        default_factory=dict,
        description="Export format to relative path under data/artifacts.",
    )
    evaluation_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Named evaluation metrics and scores from review or optimization.",
    )
    lineage: list[RegistryLineageEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> None:
        """Refresh updated_at after a mutation."""
        self.updated_at = utc_now()

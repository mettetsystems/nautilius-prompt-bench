from __future__ import annotations

import json
import re
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import yaml
from pydantic import BaseModel, Field

from prompt_piper_api.domain.registry import (
    RegistryLineageEntry,
    RegistryLineageFile,
    RegistryMetadata,
)
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.exceptions import InvalidPromptIdError, RegistryWriteError
from prompt_piper_api.services.path_safety import safe_child_path, validate_prompt_id

_SLUG_RE = re.compile(r"[^a-z0-9]+")

_ARTIFACT_PATHS = {
    "metadata": "metadata.yaml",
    "canonical_md": "canonical_prompt.md",
    "canonical_txt": "canonical_prompt.txt",
    "requirement_card": "requirement_card.json",
    "coding_prompt_spec_json": "coding_prompt_spec.json",
    "coding_prompt_spec_yaml": "coding_prompt_spec.yaml",
    "lineage": "lineage.json",
}


class RegistryWriteResult(BaseModel):
    prompt_id: str
    version: int = Field(ge=1)
    prompt_dir: Path
    metadata: RegistryMetadata
    git_commit_sha: str | None = None
    warning: str | None = None


def build_prompt_id(title: str, session_id: UUID) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    if not slug:
        slug = "prompt"
    slug = slug[:48].rstrip("-")
    prompt_id = f"{slug}-{session_id.hex[:8]}"
    return validate_prompt_id(prompt_id)


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


class GitRegistryService:
    """Write finalized prompts to a local directory on this installation."""

    def __init__(self, registry_path: Path) -> None:
        self._registry_path = registry_path

    @property
    def registry_path(self) -> Path:
        return self._registry_path

    def finalize_prompt(
        self,
        *,
        prompt_id: str,
        version: int,
        title: str,
        body: str,
        requirement_card: RequirementCard,
        session_id: UUID,
        abstract: str = "",
        tags: list[str] | None = None,
        domain: str = "",
        task_family: str = "",
        output_form: str = "",
        target_provider: str = "",
        target_model: str = "",
        preferred_prompt_length: str = "",
        lineage: list[RegistryLineageEntry] | None = None,
    ) -> RegistryWriteResult:
        prompt_id = validate_prompt_id(prompt_id)
        now = datetime.now(tz=UTC)
        resolved_abstract = abstract or _derive_abstract(requirement_card, body)
        resolved_output_form = (
            output_form or requirement_card.agent_contract.completion_contract
        )
        metadata = RegistryMetadata(
            prompt_id=prompt_id,
            version=version,
            title=title,
            abstract=resolved_abstract,
            tags=list(tags or []),
            domain=domain or "coding",
            task_family=task_family or requirement_card.task_identity.task_type,
            output_form=resolved_output_form,
            target_provider=target_provider,
            target_model=target_model,
            preferred_prompt_length=preferred_prompt_length,
            evaluation_scores={},
            artifact_paths=dict(_ARTIFACT_PATHS),
            created_at=now,
            updated_at=now,
        )

        prompt_dir = self._registry_path / prompt_id
        existing = self.load_metadata(prompt_id)
        if existing is not None and existing.version != version:
            raise RegistryWriteError(
                f"Registry entry for {prompt_id} already exists at version {existing.version}.",
                prompt_id=prompt_id,
            )

        staging_dir = self._write_atomic(
            prompt_dir=prompt_dir,
            metadata=metadata,
            title=title,
            body=body,
            requirement_card=requirement_card,
            lineage=lineage or [],
            session_id=session_id,
        )
        _ = staging_dir  # staging renamed into prompt_dir

        return RegistryWriteResult(
            prompt_id=prompt_id,
            version=version,
            prompt_dir=prompt_dir,
            metadata=metadata,
            git_commit_sha=None,
            warning=None,
        )

    def _write_atomic(
        self,
        *,
        prompt_dir: Path,
        metadata: RegistryMetadata,
        title: str,
        body: str,
        requirement_card: RequirementCard,
        lineage: list[RegistryLineageEntry],
        session_id: UUID,
    ) -> Path:
        self._registry_path.mkdir(parents=True, exist_ok=True)
        staging_root = Path(
            tempfile.mkdtemp(prefix=f".staging-{metadata.prompt_id}-", dir=self._registry_path)
        )
        try:
            self._write_metadata(staging_root, metadata)
            self._write_canonical_files(staging_root, title, body)
            self._write_requirement_card(staging_root, requirement_card)
            self._write_lineage(staging_root, lineage, session_id)

            if prompt_dir.exists():
                backup = prompt_dir.with_name(f".backup-{metadata.prompt_id}-{uuid4().hex[:8]}")
                prompt_dir.rename(backup)
                try:
                    staging_root.rename(prompt_dir)
                except OSError as exc:
                    backup.rename(prompt_dir)
                    raise RegistryWriteError(
                        "Failed to publish registry files atomically.",
                        prompt_id=metadata.prompt_id,
                    ) from exc
                shutil.rmtree(backup, ignore_errors=True)
            else:
                staging_root.rename(prompt_dir)
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            raise
        return prompt_dir

    def update_artifact_paths(
        self,
        prompt_id: str,
        *,
        artifact_paths: dict[str, str],
        evaluation_scores: dict[str, float] | None = None,
        expected_version: int | None = None,
    ) -> str | None:
        """Link generated export paths back to registry metadata.yaml."""
        prompt_id = validate_prompt_id(prompt_id)
        prompt_dir = self._registry_path / prompt_id
        metadata_path = prompt_dir / "metadata.yaml"
        if not metadata_path.is_file():
            return f"Registry metadata not found for prompt {prompt_id}."

        raw = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return f"Registry metadata for prompt {prompt_id} is invalid."

        current_version = int(raw.get("version", 1))
        if expected_version is not None and current_version != expected_version:
            return (
                f"Registry version mismatch for {prompt_id}: "
                f"expected {expected_version}, found {current_version}."
            )

        raw["artifact_paths"] = {**raw.get("artifact_paths", {}), **artifact_paths}
        if evaluation_scores:
            merged_scores = dict(raw.get("evaluation_scores", {}))
            merged_scores.update(evaluation_scores)
            raw["evaluation_scores"] = merged_scores
        raw["updated_at"] = _isoformat(datetime.now(tz=UTC))

        temp_path = metadata_path.with_suffix(".yaml.tmp")
        temp_path.write_text(
            yaml.dump(raw, default_flow_style=False, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        temp_path.replace(metadata_path)
        return None

    def load_metadata(self, prompt_id: str) -> RegistryMetadata | None:
        try:
            prompt_id = validate_prompt_id(prompt_id)
        except InvalidPromptIdError:
            return None
        metadata_path = safe_child_path(self._registry_path, prompt_id, "metadata.yaml")
        if metadata_path is None or not metadata_path.is_file():
            return None
        raw = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return RegistryMetadata.model_validate(raw)

    def list_prompts(self) -> list[RegistryMetadata]:
        if not self._registry_path.is_dir():
            return []
        prompts: list[RegistryMetadata] = []
        for entry in self._registry_path.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            try:
                validate_prompt_id(entry.name)
            except InvalidPromptIdError:
                continue
            metadata = self.load_metadata(entry.name)
            if metadata is not None:
                prompts.append(metadata)
        prompts.sort(key=lambda item: item.updated_at, reverse=True)
        return prompts

    def read_registry_file(self, prompt_id: str, filename: str) -> str | None:
        from prompt_piper_api.services.path_safety import validate_filename

        prompt_id = validate_prompt_id(prompt_id)
        filename = validate_filename(filename)
        path = safe_child_path(self._registry_path, prompt_id, filename)
        if path is None or not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def _write_metadata(self, prompt_dir: Path, metadata: RegistryMetadata) -> None:
        payload = metadata.model_dump(mode="json")
        payload["created_at"] = _isoformat(metadata.created_at)
        payload["updated_at"] = _isoformat(metadata.updated_at)
        text = yaml.dump(
            payload,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        (prompt_dir / "metadata.yaml").write_text(text, encoding="utf-8")

    def _write_canonical_files(self, prompt_dir: Path, title: str, body: str) -> None:
        (prompt_dir / "canonical_prompt.txt").write_text(body, encoding="utf-8")
        markdown = f"# {title}\n\n{body}" if title else body
        (prompt_dir / "canonical_prompt.md").write_text(markdown, encoding="utf-8")

    def _write_requirement_card(self, prompt_dir: Path, card: RequirementCard) -> None:
        (prompt_dir / "requirement_card.json").write_text(
            card.model_dump_json(indent=2),
            encoding="utf-8",
        )
        coding_spec = card.coding_spec_dict()
        (prompt_dir / "coding_prompt_spec.json").write_text(
            json.dumps(coding_spec, indent=2),
            encoding="utf-8",
        )
        (prompt_dir / "coding_prompt_spec.yaml").write_text(
            yaml.dump(
                coding_spec,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

    def _write_lineage(
        self,
        prompt_dir: Path,
        lineage: list[RegistryLineageEntry],
        session_id: UUID,
    ) -> None:
        payload = RegistryLineageFile(
            lineage=lineage,
            source_session_id=str(session_id),
        )
        (prompt_dir / "lineage.json").write_text(
            payload.model_dump_json(indent=2),
            encoding="utf-8",
        )


def _derive_abstract(card: RequirementCard, body: str) -> str:
    if card.objective.strip():
        return card.objective.strip()[:240]
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return first_line[:240]

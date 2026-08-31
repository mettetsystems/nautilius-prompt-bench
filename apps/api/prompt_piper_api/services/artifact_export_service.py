from __future__ import annotations

import hashlib
import json
import platform
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from prompt_piper_api import __version__
from prompt_piper_api.domain.artifacts import (
    ArtifactFileEntry,
    ArtifactGenerationResult,
    ArtifactManifest,
    ExportAuditRecord,
)
from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.registry import RegistryMetadata
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.domain.similarity import SimilarityCheckResult
from prompt_piper_api.services.artifact_service import (
    ArtifactService,
    pandoc_available,
    weasyprint_available,
)
from prompt_piper_api.services.api_pack_export import build_api_pack, dumps_pack_value
from prompt_piper_api.services.exceptions import InvalidPathError
from prompt_piper_api.services.harness_prompt_builder import build_harness_body
from prompt_piper_api.services.path_safety import safe_child_path, validate_prompt_id
from prompt_piper_api.services.similarity_index_service import build_lessons_learned

_EXPORT_PATH_KEYS: dict[str, str] = {
    "metadata": "metadata.yaml",
    "canonical_md": "canonical_prompt.md",
    "canonical_txt": "canonical_prompt.txt",
    "optimized_md": "optimized_prompt.md",
    "optimized_txt": "optimized_prompt.txt",
    "harness_md": "harness_prompt.md",
    "harness_txt": "harness_prompt.txt",
    "requirement_card": "requirement_card.json",
    "coding_prompt_spec_json": "coding_prompt_spec.json",
    "coding_prompt_spec_yaml": "coding_prompt_spec.yaml",
    "coding_harness_spec_json": "coding_harness_spec.json",
    "api_pack_readme": "api_pack/README.md",
    "api_openai": "api_pack/openai_chat_completions.json",
    "api_anthropic": "api_pack/anthropic_messages.json",
    "api_gemini": "api_pack/gemini_generate_content.json",
    "api_cursor_json": "api_pack/cursor_agent.json",
    "api_cursor_md": "api_pack/cursor_rules.md",
    "api_copilot_json": "api_pack/copilot_instructions.json",
    "api_copilot_md": "api_pack/copilot_instructions.md",
    "api_continue_json": "api_pack/continue_config.json",
    "api_continue_md": "api_pack/continue_system.md",
    "metrics": "metrics.json",
    "similarity_report": "similarity_report.json",
    "lessons_learned": "lessons_learned.md",
    "manifest": "artifact_manifest.json",
    "export_audit": "export_audit.json",
    "rendered_html": "rendered.html",
    "rendered_pdf": "rendered.pdf",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_COLLISION_SUFFIX_RE = re.compile(r"__export_\d{3}$")
_GENERATED_BY = f"prompt-piper/{__version__}"


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def safe_export_slug(title: str, *, fallback: str = "export") -> str:
    cleaned = _SLUG_RE.sub("-", title.strip().lower()).strip("-")
    if not cleaned:
        cleaned = fallback
    return cleaned[:64].strip("-") or fallback


def build_export_folder_name(
    *,
    label: str,
    prompt_id: str | None = None,
    fallback: str = "export",
    timestamp: datetime | None = None,
) -> str:
    when = timestamp or datetime.now(tz=UTC)
    stamp = when.astimezone(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    slug = safe_export_slug(label, fallback=fallback)
    if prompt_id is not None:
        validate_prompt_id(prompt_id)
        return f"{stamp}__{prompt_id}__{slug}"
    return f"{stamp}__{slug}"


def citeproc_available() -> bool:
    if not pandoc_available():
        return False
    try:
        result = shutil.which("pandoc")
        if result is None:
            return False
        import subprocess

        proc = subprocess.run(
            ["pandoc", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return "citeproc" in proc.stdout.lower()
    except OSError:
        return False


@dataclass
class _ExportWriteState:
    export_dir: Path
    file_entries: list[ArtifactFileEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def generated_files(self) -> list[str]:
        return [entry.name for entry in self.file_entries]


class ArtifactExportService:
    """Write Nautilius Prompting Workbench exports to unique folders under the Documents export root."""

    def __init__(
        self,
        artifact_service: ArtifactService,
        *,
        export_root: Path,
        host_export_root: Path,
        artifact_root: Path,
    ) -> None:
        self._artifact_service = artifact_service
        self._export_root = export_root.resolve()
        self._host_export_root = host_export_root
        self._artifact_root = artifact_root.resolve()

    @property
    def export_root(self) -> Path:
        return self._export_root

    @property
    def artifact_root(self) -> Path:
        return self._artifact_root

    @property
    def host_export_root(self) -> Path:
        return self._host_export_root

    def get_export_root(self) -> Path:
        return self._export_root

    def resolve_export_root(self) -> Path:
        return self.get_export_root()

    def container_to_host_path(self, container_path: Path) -> Path:
        try:
            relative = container_path.resolve().relative_to(self._export_root)
        except ValueError:
            return self._host_export_root / container_path.name
        return self._host_export_root / relative

    def _assert_under_artifact_root(self, path: Path) -> Path:
        root = self._artifact_root.resolve()
        target = path.resolve()
        if target != root and root not in target.parents:
            raise InvalidPathError(
                "Export path escapes configured artifact root.",
                filename=str(path),
            )
        return target

    def create_unique_export_folder(
        self,
        prompt_id: str,
        title: str,
        *,
        folder_label: str | None = None,
    ) -> Path:
        validate_prompt_id(prompt_id)
        label_source = (folder_label or title).strip() or title
        base_name = build_export_folder_name(
            label=label_source,
            fallback=prompt_id.split("-")[0],
        )
        candidate = self._artifact_root / base_name
        self._assert_under_artifact_root(candidate)

        if not candidate.exists():
            return candidate

        stem = base_name
        if _COLLISION_SUFFIX_RE.search(stem):
            stem = _COLLISION_SUFFIX_RE.sub("", stem)

        suffix = 2
        while True:
            next_name = f"{stem}__export_{suffix:03d}"
            candidate = self._artifact_root / next_name
            self._assert_under_artifact_root(candidate)
            if not candidate.exists():
                return candidate
            suffix += 1

    def allocate_unique_export_dir(
        self,
        *,
        prompt_id: str,
        safe_slug: str,
        timestamp: datetime | None = None,
    ) -> Path:
        validate_prompt_id(prompt_id)
        safe_slug = safe_export_slug(safe_slug, fallback="export")
        base_name = build_export_folder_name(
            label=safe_slug,
            prompt_id=prompt_id,
            fallback="export",
            timestamp=timestamp,
        )
        candidate = self._artifact_root / base_name
        self._assert_under_artifact_root(candidate)
        if not candidate.exists():
            return candidate

        stem = base_name
        if _COLLISION_SUFFIX_RE.search(stem):
            stem = _COLLISION_SUFFIX_RE.sub("", stem)

        suffix = 2
        while True:
            next_name = f"{stem}__export_{suffix:03d}"
            candidate = self._artifact_root / next_name
            self._assert_under_artifact_root(candidate)
            if not candidate.exists():
                return candidate
            suffix += 1

    @staticmethod
    def compute_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def sha256_file(path: Path) -> str:
        return ArtifactExportService.compute_sha256(path)

    @staticmethod
    def collect_tool_versions() -> dict[str, str]:
        versions: dict[str, str] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
        }
        versions["pandoc"] = "available" if pandoc_available() else "not_available"
        versions["citeproc"] = "available" if citeproc_available() else "not_available"
        versions["weasyprint"] = "available" if weasyprint_available() else "not_available"
        return versions

    def write_text_artifact(
        self,
        export_dir: Path,
        name: str,
        content: str,
        *,
        fmt: str,
        state: _ExportWriteState,
        optional: bool = False,
    ) -> Path:
        self._assert_under_artifact_root(export_dir)
        safe = safe_child_path(export_dir, name)
        if safe is None:
            raise InvalidPathError("Artifact filename escapes export folder.", filename=name)
        safe.parent.mkdir(parents=True, exist_ok=True)
        safe.write_text(content, encoding="utf-8")
        checksum = self.compute_sha256(safe)
        state.file_entries.append(
            ArtifactFileEntry(
                name=name,
                format=fmt,
                size_bytes=safe.stat().st_size,
                sha256=checksum,
                optional=optional,
            )
        )
        return safe

    def write_json_artifact(
        self,
        export_dir: Path,
        name: str,
        payload: Any,
        *,
        state: _ExportWriteState,
        optional: bool = False,
    ) -> Path:
        if hasattr(payload, "model_dump_json"):
            content = payload.model_dump_json(indent=2)
        elif isinstance(payload, str):
            content = payload
        else:
            content = json.dumps(payload, indent=2)
        return self.write_text_artifact(
            export_dir,
            name,
            content,
            fmt="json",
            state=state,
            optional=optional,
        )

    def write_yaml_artifact(
        self,
        export_dir: Path,
        name: str,
        payload: dict[str, Any],
        *,
        state: _ExportWriteState,
        optional: bool = False,
    ) -> Path:
        content = yaml.dump(
            payload,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        return self.write_text_artifact(
            export_dir,
            name,
            content,
            fmt="yaml",
            state=state,
            optional=optional,
        )

    def generate_html(self, markdown_content: str, *, title: str = "") -> tuple[str, str | None]:
        return self._artifact_service.generate_html(markdown_content, title=title)

    def generate_pdf(self, html_content: str, output_path: Path) -> str | None:
        self._assert_under_artifact_root(output_path.parent)
        safe = safe_child_path(output_path.parent, output_path.name)
        if safe is None:
            raise InvalidPathError(
                "PDF output path escapes export folder.",
                filename=output_path.name,
            )
        return self._artifact_service.generate_pdf(html_content, output_path)

    def generate_manifest(
        self,
        *,
        export_id: str,
        prompt_id: str,
        prompt_version: int,
        created_at: datetime,
        container_export_path: str,
        expected_host_export_path: str,
        files: list[ArtifactFileEntry],
        warnings: list[str],
        tool_versions: dict[str, str] | None = None,
    ) -> ArtifactManifest:
        return ArtifactManifest(
            export_id=export_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            created_at=created_at,
            container_export_path=container_export_path,
            expected_host_export_path=expected_host_export_path,
            files=list(files),
            generated_by=_GENERATED_BY,
            tool_versions=dict(tool_versions or self.collect_tool_versions()),
            warnings=list(warnings),
        )

    def generate_export_audit(
        self,
        *,
        export_id: str,
        prompt_id: str,
        prompt_version: int,
        session_id: str | None,
        created_at: datetime,
        container_export_path: str,
        expected_host_export_path: str,
        file_count: int,
        warnings: list[str],
    ) -> ExportAuditRecord:
        return ExportAuditRecord(
            export_id=export_id,
            prompt_id=prompt_id,
            prompt_version=prompt_version,
            session_id=session_id,
            created_at=created_at,
            container_export_path=container_export_path,
            expected_host_export_path=expected_host_export_path,
            file_count=file_count,
            warnings=list(warnings),
        )

    @staticmethod
    def resolve_latest_export_dir(artifact_root: Path, prompt_id: str) -> Path | None:
        validate_prompt_id(prompt_id)
        latest_file = artifact_root / ".latest" / f"{prompt_id}.json"
        if latest_file.is_file():
            payload = json.loads(latest_file.read_text(encoding="utf-8"))
            folder_name = payload.get("dir")
            if isinstance(folder_name, str):
                candidate = artifact_root / folder_name
                if candidate.is_dir():
                    return candidate

        prompt_prefix = f"__{prompt_id}__"
        matches = sorted(
            (
                entry
                for entry in artifact_root.iterdir()
                if entry.is_dir() and prompt_prefix in entry.name
            ),
            key=lambda item: item.name,
            reverse=True,
        )
        return matches[0] if matches else None

    def export(
        self,
        *,
        prompt_id: str,
        version: int,
        title: str,
        canonical_body: str,
        optimized_body: str | None,
        requirement_card: RequirementCard,
        registry_metadata: RegistryMetadata | None,
        optimization_result: OptimizationResult | None,
        pre_inference_metrics: PreInferenceMetrics | None,
        similarity_result: SimilarityCheckResult | None,
        include_pdf: bool = True,
        session_id: str | None = None,
        export_folder_label: str | None = None,
    ) -> ArtifactGenerationResult:
        validate_prompt_id(prompt_id)
        export_id = str(uuid4())
        export_dir = self.create_unique_export_folder(
            prompt_id,
            title,
            folder_label=export_folder_label,
        )
        export_dir.mkdir(parents=True, exist_ok=False)

        host_path = self.container_to_host_path(export_dir)
        container_path = export_dir.resolve()
        state = _ExportWriteState(export_dir=export_dir)
        now = datetime.now(tz=UTC)

        self.write_text_artifact(
            export_dir,
            "canonical_prompt.txt",
            self._artifact_service.generate_txt(canonical_body),
            fmt="txt",
            state=state,
        )
        canonical_md = self._artifact_service.generate_markdown(title=title, body=canonical_body)
        self.write_text_artifact(
            export_dir,
            "canonical_prompt.md",
            canonical_md,
            fmt="markdown",
            state=state,
        )

        if optimized_body is not None and optimization_result is not None:
            self.write_text_artifact(
                export_dir,
                "optimized_prompt.txt",
                self._artifact_service.generate_txt(optimized_body),
                fmt="txt",
                state=state,
            )
            optimized_md = self._artifact_service.generate_markdown(
                title=title,
                body=optimized_body,
            )
            self.write_text_artifact(
                export_dir,
                "optimized_prompt.md",
                optimized_md,
                fmt="markdown",
                state=state,
            )
        else:
            optimized_md = canonical_md

        metadata = registry_metadata or RegistryMetadata(
            prompt_id=prompt_id,
            version=version,
            title=title,
        )
        evaluation_scores = dict(metadata.evaluation_scores)
        if pre_inference_metrics is not None:
            evaluation_scores.update(
                {
                    "requirement_capture_score": pre_inference_metrics.requirement_capture_score,
                    "unspecified_field_honesty": pre_inference_metrics.unspecified_field_honesty,
                    "instruction_clarity": pre_inference_metrics.instruction_clarity,
                    "format_adherence": pre_inference_metrics.format_adherence,
                    "richness_score": pre_inference_metrics.richness_score,
                    "density_score": pre_inference_metrics.density_score,
                    "efficiency_score": pre_inference_metrics.efficiency_score,
                    "denoising_score": pre_inference_metrics.denoising_score,
                    "deconfliction_score": pre_inference_metrics.deconfliction_score,
                }
            )

        export_folder_name = export_dir.name
        artifact_paths = {
            key: f"{export_folder_name}/{value}" for key, value in _EXPORT_PATH_KEYS.items()
        }
        if optimized_body is None or optimization_result is None:
            for key in ("optimized_md", "optimized_txt"):
                artifact_paths.pop(key, None)

        updated_metadata = metadata.model_copy(
            update={
                "artifact_paths": artifact_paths,
                "evaluation_scores": evaluation_scores,
                "updated_at": now,
            }
        )
        metadata_payload = updated_metadata.model_dump(mode="json")
        metadata_payload["created_at"] = _isoformat(updated_metadata.created_at)
        metadata_payload["updated_at"] = _isoformat(now)
        self.write_yaml_artifact(export_dir, "metadata.yaml", metadata_payload, state=state)
        self.write_json_artifact(
            export_dir,
            "requirement_card.json",
            requirement_card,
            state=state,
        )
        coding_spec = requirement_card.coding_spec_dict()
        self.write_json_artifact(
            export_dir,
            "coding_prompt_spec.json",
            coding_spec,
            state=state,
        )
        self.write_yaml_artifact(
            export_dir,
            "coding_prompt_spec.yaml",
            coding_spec,
            state=state,
        )

        harness_source = optimized_body or canonical_body
        # Prefer the optimized contract when it already has the long-horizon sections.
        harness_body = build_harness_body(requirement_card)
        source_lower = harness_source.lower()
        if "long-horizon coding agent contract" in source_lower or "task identity" in source_lower:
            harness_body = harness_source
        api_pack = build_api_pack(
            requirement_card,
            harness_body=harness_body,
            title=title,
        )
        for relative_name, value in api_pack.items():
            text = dumps_pack_value(value)
            fmt = "markdown" if relative_name.endswith(".md") else (
                "json" if relative_name.endswith(".json") else "txt"
            )
            self.write_text_artifact(
                export_dir,
                relative_name,
                text,
                fmt=fmt,
                state=state,
            )

        metrics_payload: dict[str, object] = {
            "optimization": (
                optimization_result.metrics.model_dump()
                if optimization_result is not None
                else None
            ),
            "pre_inference": (
                pre_inference_metrics.model_dump() if pre_inference_metrics is not None else None
            ),
        }
        self.write_json_artifact(export_dir, "metrics.json", metrics_payload, state=state)

        if similarity_result is not None:
            self.write_json_artifact(
                export_dir,
                "similarity_report.json",
                similarity_result.model_dump(mode="json"),
                state=state,
            )
        else:
            artifact_paths.pop("similarity_report", None)

        lessons = build_lessons_learned(requirement_card)
        self.write_text_artifact(
            export_dir,
            "lessons_learned.md",
            lessons,
            fmt="markdown",
            state=state,
        )

        rendered_html, html_warning = self.generate_html(optimized_md, title=title)
        if html_warning:
            state.warnings.append(html_warning)
        self.write_text_artifact(
            export_dir,
            "rendered.html",
            rendered_html,
            fmt="html",
            state=state,
            optional=True,
        )

        if include_pdf:
            pdf_path = export_dir / "rendered.pdf"
            pdf_warning = self.generate_pdf(rendered_html, pdf_path)
            if pdf_warning:
                state.warnings.append(pdf_warning)
            elif pdf_path.is_file():
                checksum = self.compute_sha256(pdf_path)
                state.file_entries.append(
                    ArtifactFileEntry(
                        name="rendered.pdf",
                        format="pdf",
                        size_bytes=pdf_path.stat().st_size,
                        sha256=checksum,
                        optional=True,
                    )
                )

        tool_versions = self.collect_tool_versions()
        manifest = self.generate_manifest(
            export_id=export_id,
            prompt_id=prompt_id,
            prompt_version=version,
            created_at=now,
            container_export_path=str(container_path),
            expected_host_export_path=str(host_path),
            files=list(state.file_entries),
            warnings=list(state.warnings),
            tool_versions=tool_versions,
        )

        audit_record = self.generate_export_audit(
            export_id=export_id,
            prompt_id=prompt_id,
            prompt_version=version,
            session_id=session_id,
            created_at=now,
            container_export_path=str(container_path),
            expected_host_export_path=str(host_path),
            file_count=len(state.file_entries),
            warnings=list(state.warnings),
        )
        self.write_json_artifact(export_dir, "export_audit.json", audit_record, state=state)

        manifest_path = export_dir / "artifact_manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        manifest_checksum = self.compute_sha256(manifest_path)
        state.file_entries.append(
            ArtifactFileEntry(
                name="artifact_manifest.json",
                format="json",
                size_bytes=manifest_path.stat().st_size,
                sha256=manifest_checksum,
            )
        )
        manifest = self.generate_manifest(
            export_id=export_id,
            prompt_id=prompt_id,
            prompt_version=version,
            created_at=now,
            container_export_path=str(container_path),
            expected_host_export_path=str(host_path),
            files=list(state.file_entries),
            warnings=list(state.warnings),
            tool_versions=tool_versions,
        )
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

        latest_payload = {
            "export_id": export_id,
            "version": version,
            "dir": export_dir.name,
            "container_export_path": str(container_path),
            "expected_host_export_path": str(host_path),
        }
        latest_path = self._artifact_root / ".latest" / f"{prompt_id}.json"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")

        return ArtifactGenerationResult(
            export_id=export_id,
            prompt_id=prompt_id,
            version=version,
            container_export_path=str(container_path),
            expected_host_export_path=str(host_path),
            manifest_path=str(manifest_path),
            generated_files=state.generated_files,
            manifest=manifest,
            artifact_paths=artifact_paths,
            warnings=list(state.warnings),
        )

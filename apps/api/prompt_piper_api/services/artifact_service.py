from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from prompt_piper_api.domain.artifacts import (
    ArtifactFileEntry,
    ArtifactGenerationResult,
    ArtifactManifest,
)
from prompt_piper_api.domain.optimization import OptimizationResult
from prompt_piper_api.domain.pre_inference_metrics import PreInferenceMetrics
from prompt_piper_api.domain.registry import RegistryMetadata
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.domain.similarity import SimilarityCheckResult
from prompt_piper_api.services.exceptions import ArtifactExistsError
from prompt_piper_api.services.path_safety import artifact_version_dir, artifact_version_label
from prompt_piper_api.services.similarity_index_service import build_lessons_learned

_ARTIFACT_PATH_KEYS: dict[str, str] = {
    "metadata": "metadata.yaml",
    "canonical_md": "canonical_prompt.md",
    "canonical_txt": "canonical_prompt.txt",
    "optimized_md": "optimized_prompt.md",
    "optimized_txt": "optimized_prompt.txt",
    "requirement_card": "requirement_card.json",
    "coding_prompt_spec_json": "coding_prompt_spec.json",
    "coding_prompt_spec_yaml": "coding_prompt_spec.yaml",
    "metrics": "metrics.json",
    "similarity_report": "similarity_report.json",
    "lessons_learned": "lessons_learned.md",
    "manifest": "artifact_manifest.json",
    "optimized_html": "optimized_prompt.html",
    "optimized_pdf": "optimized_prompt.pdf",
}


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except ImportError:
        return False


class ArtifactService:
    """Generate stable local export artifacts from canonical and optimized prompts."""

    def __init__(self, artifacts_path: Path) -> None:
        self._artifacts_path = artifacts_path

    @property
    def artifacts_path(self) -> Path:
        return self._artifacts_path

    def generate_markdown(self, *, title: str, body: str) -> str:
        stripped = body.strip()
        if not title.strip():
            return stripped
        return f"# {title.strip()}\n\n{stripped}"

    def generate_txt(self, body: str) -> str:
        return body

    def generate_html(self, markdown_content: str, *, title: str = "") -> tuple[str, str | None]:
        if pandoc_available():
            result = subprocess.run(
                ["pandoc", "-f", "markdown", "-t", "html", "--standalone"],
                input=markdown_content,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout, None
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            warning = f"Pandoc HTML conversion failed: {detail}"
        else:
            warning = "Pandoc is not available; using built-in HTML fallback."

        page_title = title.strip() or "Prompt Export"
        escaped_title = (
            page_title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        body_html = (
            markdown_content.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>\n")
        )
        html = (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            f'  <meta charset="utf-8"/>\n'
            f"  <title>{escaped_title}</title>\n"
            "  <style>body{font-family:system-ui,sans-serif;line-height:1.5;"
            "max-width:48rem;margin:2rem auto;padding:0 1rem;}</style>\n"
            "</head>\n"
            "<body>\n"
            f"{body_html}\n"
            "</body>\n"
            "</html>\n"
        )
        return html, warning

    def generate_pdf(self, html_content: str, output_path: Path) -> str | None:
        if weasyprint_available():
            try:
                from weasyprint import HTML

                HTML(string=html_content).write_pdf(str(output_path))
                return None
            except Exception as exc:  # noqa: BLE001 — surface tool failure as warning
                return f"WeasyPrint PDF generation failed: {exc}"

        if pandoc_available():
            md_path = output_path.with_suffix(".md.tmp")
            html_path = output_path.with_suffix(".html.tmp")
            try:
                html_path.write_text(html_content, encoding="utf-8")
                result = subprocess.run(
                    ["pandoc", str(html_path), "-o", str(output_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode == 0 and output_path.is_file():
                    return None
                detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
                return f"Pandoc PDF generation failed: {detail}"
            finally:
                md_path.unlink(missing_ok=True)
                html_path.unlink(missing_ok=True)

        if not weasyprint_available() and not pandoc_available():
            return "WeasyPrint and Pandoc are not available; PDF export skipped."
        return "PDF export skipped because no HTML-to-PDF converter succeeded."

    def generate_manifest(
        self,
        *,
        export_id: str,
        prompt_id: str,
        version: int,
        container_export_path: str,
        expected_host_export_path: str,
        files: list[ArtifactFileEntry],
        warnings: list[str],
        tool_versions: dict[str, str] | None = None,
    ) -> ArtifactManifest:
        return ArtifactManifest(
            export_id=export_id,
            prompt_id=prompt_id,
            prompt_version=version,
            container_export_path=container_export_path,
            expected_host_export_path=expected_host_export_path,
            files=files,
            warnings=list(warnings),
            tool_versions=dict(tool_versions or {}),
        )

    @staticmethod
    def resolve_latest_artifact_dir(artifacts_path: Path, prompt_id: str) -> Path | None:
        """Return the newest export folder for a prompt."""
        from prompt_piper_api.services.artifact_export_service import ArtifactExportService

        latest = ArtifactExportService.resolve_latest_export_dir(artifacts_path, prompt_id)
        if latest is not None:
            return latest

        from prompt_piper_api.services.path_safety import validate_prompt_id

        validate_prompt_id(prompt_id)
        latest_file = artifacts_path / prompt_id / "latest.json"
        if latest_file.is_file():
            payload = json.loads(latest_file.read_text(encoding="utf-8"))
            version_dir = payload.get("dir")
            if isinstance(version_dir, str):
                candidate = artifacts_path / prompt_id / version_dir
                if candidate.is_dir():
                    return candidate
        prompt_root = artifacts_path / prompt_id
        if not prompt_root.is_dir():
            return None
        version_dirs = sorted(
            (
                entry
                for entry in prompt_root.iterdir()
                if entry.is_dir() and entry.name.startswith("v")
            ),
            key=lambda item: item.name,
            reverse=True,
        )
        return version_dirs[0] if version_dirs else None

    def generate(
        self,
        *,
        prompt_id: str,
        version: int,
        title: str,
        canonical_body: str,
        optimized_body: str,
        requirement_card: RequirementCard,
        registry_metadata: RegistryMetadata | None,
        optimization_result: OptimizationResult,
        pre_inference_metrics: PreInferenceMetrics | None,
        similarity_result: SimilarityCheckResult | None,
        include_pdf: bool = True,
    ) -> ArtifactGenerationResult:
        artifact_dir = artifact_version_dir(self._artifacts_path, prompt_id, version)
        if artifact_dir.exists() and any(artifact_dir.iterdir()):
            raise ArtifactExistsError(
                f"Artifacts for {prompt_id} version {version} already exist.",
                prompt_id=prompt_id,
                version=version,
            )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        version_prefix = f"{artifact_version_label(version)}/"

        warnings: list[str] = []
        file_entries: list[ArtifactFileEntry] = []

        def write_text(name: str, fmt: str, content: str, *, optional: bool = False) -> None:
            path = artifact_dir / name
            path.write_text(content, encoding="utf-8")
            file_entries.append(
                ArtifactFileEntry(
                    name=name,
                    format=fmt,
                    size_bytes=path.stat().st_size,
                    optional=optional,
                )
            )

        canonical_md = self.generate_markdown(title=title, body=canonical_body)
        optimized_md = self.generate_markdown(title=title, body=optimized_body)
        write_text("canonical_prompt.txt", "txt", self.generate_txt(canonical_body))
        write_text("canonical_prompt.md", "markdown", canonical_md)
        write_text("optimized_prompt.txt", "txt", self.generate_txt(optimized_body))
        write_text("optimized_prompt.md", "markdown", optimized_md)

        now = datetime.now(tz=UTC)
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

        artifact_paths = {
            key: f"{version_prefix}{value}" for key, value in _ARTIFACT_PATH_KEYS.items()
        }
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
        metadata_yaml = yaml.dump(
            metadata_payload,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        write_text("metadata.yaml", "yaml", metadata_yaml)

        write_text(
            "requirement_card.json",
            "json",
            requirement_card.model_dump_json(indent=2),
        )
        from prompt_piper_api.services.contract_resolver import resolve_contract
        coding_spec = resolve_contract(requirement_card).coding_spec_dict()
        write_text(
            "coding_prompt_spec.json",
            "json",
            json.dumps(coding_spec, indent=2),
        )
        coding_yaml = yaml.dump(
            coding_spec,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        write_text("coding_prompt_spec.yaml", "yaml", coding_yaml)

        metrics_payload: dict[str, object] = {
            "optimization": optimization_result.metrics.model_dump(),
            "pre_inference": (
                pre_inference_metrics.model_dump() if pre_inference_metrics is not None else None
            ),
        }
        write_text("metrics.json", "json", json.dumps(metrics_payload, indent=2))

        similarity_payload = (
            similarity_result.model_dump(mode="json")
            if similarity_result is not None
            else {"warning": None, "matches": []}
        )
        write_text(
            "similarity_report.json",
            "json",
            json.dumps(similarity_payload, indent=2),
        )

        lessons = build_lessons_learned(requirement_card)
        write_text("lessons_learned.md", "markdown", lessons)

        optimized_html, html_warning = self.generate_html(optimized_md, title=title)
        if html_warning:
            warnings.append(html_warning)
        write_text("optimized_prompt.html", "html", optimized_html, optional=True)

        if include_pdf:
            pdf_path = artifact_dir / "optimized_prompt.pdf"
            pdf_warning = self.generate_pdf(optimized_html, pdf_path)
            if pdf_warning:
                warnings.append(pdf_warning)
            elif pdf_path.is_file():
                file_entries.append(
                    ArtifactFileEntry(
                        name="optimized_prompt.pdf",
                        format="pdf",
                        size_bytes=pdf_path.stat().st_size,
                        optional=True,
                    )
                )

        export_id = str(uuid4())
        container_path = str(artifact_dir)
        manifest = self.generate_manifest(
            export_id=export_id,
            prompt_id=prompt_id,
            version=version,
            expected_host_export_path=container_path,
            container_export_path=container_path,
            files=file_entries,
            warnings=warnings,
        )
        file_entries.append(
            ArtifactFileEntry(
                name="artifact_manifest.json",
                format="json",
                size_bytes=0,
            )
        )
        manifest = manifest.model_copy(update={"files": list(file_entries)})
        manifest_path = artifact_dir / "artifact_manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        manifest_size = manifest_path.stat().st_size
        file_entries[-1] = ArtifactFileEntry(
            name="artifact_manifest.json",
            format="json",
            size_bytes=manifest_size,
        )
        manifest = manifest.model_copy(update={"files": list(file_entries)})

        latest_payload = {
            "version": version,
            "dir": artifact_version_label(version),
            "artifact_dir": str(artifact_dir),
        }
        latest_path = self._artifacts_path / prompt_id / "latest.json"
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(json.dumps(latest_payload, indent=2), encoding="utf-8")

        return ArtifactGenerationResult(
            export_id=export_id,
            prompt_id=prompt_id,
            version=version,
            container_export_path=container_path,
            expected_host_export_path=container_path,
            manifest_path=str(manifest_path),
            generated_files=[entry.name for entry in file_entries],
            manifest=manifest,
            artifact_paths=artifact_paths,
            warnings=warnings,
        )

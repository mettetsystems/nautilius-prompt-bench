from __future__ import annotations

from pathlib import Path

from prompt_piper_api.config import Settings
from prompt_piper_api.services.artifact_export_service import ArtifactExportService
from prompt_piper_api.services.artifact_service import ArtifactService


def create_artifact_export_service(
    settings: Settings | None = None,
    *,
    export_root: Path | None = None,
    host_export_root: Path | None = None,
    artifact_root: Path | None = None,
) -> ArtifactExportService:
    """Build an export service wired to Documents export paths."""
    if settings is not None:
        resolved_export = settings.prompt_piper_export_root
        resolved_host = settings.prompt_piper_host_export_root
        resolved_artifact = settings.prompt_piper_artifact_root or settings.artifacts_path
    else:
        resolved_export = export_root or Path.home() / "Documents" / "Nautilius"
        resolved_host = host_export_root or resolved_export
        resolved_artifact = artifact_root or (resolved_export / "exports")

    return ArtifactExportService(
        ArtifactService(resolved_artifact),
        export_root=resolved_export,
        host_export_root=resolved_host,
        artifact_root=resolved_artifact,
    )

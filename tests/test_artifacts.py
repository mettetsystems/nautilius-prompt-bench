import json
from pathlib import Path
from uuid import UUID

import pytest
import yaml
from export_test_helpers import build_test_export_service
from fastapi.testclient import TestClient
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.main import app
from prompt_piper_api.services.artifact_export_service import ArtifactExportService
from prompt_piper_api.services.artifact_service import (
    ArtifactService,
    pandoc_available,
)
from prompt_piper_api.services.clarification_flow import drive_session_to_edit
from prompt_piper_api.services.exceptions import StateTransitionError
from prompt_piper_api.services.git_registry_service import GitRegistryService
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.session_service import SessionService


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "registry"


@pytest.fixture
def export_base(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def artifact_export(export_base: Path) -> ArtifactExportService:
    return build_test_export_service(export_base)


@pytest.fixture
def service(registry_path: Path, artifact_export: ArtifactExportService) -> SessionService:
    return SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=None,
        optimizer=TokenOptimizationEngine(),
        artifact_export=artifact_export,
    )


def _sample_body() -> str:
    return "\n".join(
        [
            "Technical Context",
            "-----------------",
            "Environment: Python with FastAPI and Pydantic",
            "",
            "Core Task and Scope",
            "-------------------",
            "Objective: Add FastAPI endpoint for weekly engineering status summaries.",
            "",
            "Architectural Rules and Constraints",
            "-----------------------------------",
            "Keep the response within 300 words.",
            "Use only provided source notes.",
            "",
            "Inputs, Outputs, and Contracts",
            "------------------------------",
            "Output contract: JSON with blockers, owners, and next steps.",
        ]
    )


def _enter_approval_state(service: SessionService, *, body: str | None = None) -> UUID:
    created = service.create_session(
        initial_request="Summarize weekly engineering status for leadership review.",
    )
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Engineering managers", "Bulleted summary with risks"],
    )
    record = service.get_session(session_id)
    record.session.requirement_card.objective = (
        "Summarize weekly engineering status for leadership review."
    )
    record.session.requirement_card.unresolved_fields = []
    if body is not None:
        record.drafts[-1].body = body
    service.finalize(session_id, acknowledge_first_shot_risk=True)
    service.optimize(session_id)
    service.approve_optimization(session_id)
    return session_id


def _artifact_dir(artifact_export: ArtifactExportService, prompt_id: str) -> Path:
    resolved = ArtifactExportService.resolve_latest_export_dir(
        artifact_export.artifact_root,
        prompt_id,
    )
    assert resolved is not None
    return resolved


def test_artifacts_created_under_unique_export_directory(
    service: SessionService,
    artifact_export: ArtifactExportService,
) -> None:
    session_id = _enter_approval_state(service, body=_sample_body())
    result = service.generate_artifacts(session_id)

    prompt_id = result.prompt_id
    assert prompt_id
    artifact_dir = _artifact_dir(artifact_export, prompt_id)
    assert artifact_dir.is_dir()
    assert artifact_dir.name.count("-") >= 2
    assert "weekly" in artifact_dir.name.lower() or "engineering" in artifact_dir.name.lower()

    expected_files = {
        "canonical_prompt.txt",
        "canonical_prompt.md",
        "optimized_prompt.txt",
        "optimized_prompt.md",
        "metadata.yaml",
        "requirement_card.json",
        "metrics.json",
        "lessons_learned.md",
        "artifact_manifest.json",
        "export_audit.json",
        "rendered.html",
    }
    written = {path.name for path in artifact_dir.iterdir() if path.is_file()}
    assert expected_files.issubset(written)


def test_manifest_lists_all_generated_files(
    service: SessionService,
    artifact_export: ArtifactExportService,
) -> None:
    session_id = _enter_approval_state(service, body=_sample_body())
    result = service.generate_artifacts(session_id)
    prompt_id = result.prompt_id
    assert prompt_id

    manifest = json.loads(
        (_artifact_dir(artifact_export, prompt_id) / "artifact_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    artifact_dir = _artifact_dir(artifact_export, prompt_id)
    manifest_names = {entry["name"] for entry in manifest["files"]}
    disk_names = {
        path.relative_to(artifact_dir).as_posix()
        for path in artifact_dir.rglob("*")
        if path.is_file()
    }
    assert "artifact_manifest.json" in manifest_names
    assert "export_audit.json" in manifest_names
    assert manifest_names.issubset(disk_names)
    assert len(manifest["files"]) >= 10
    assert manifest["export_id"]
    for entry in manifest["files"]:
        assert entry.get("sha256")


def test_missing_pandoc_and_weasyprint_return_warnings_not_crash(
    service: SessionService,
    artifact_export: ArtifactExportService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "prompt_piper_api.services.artifact_service.pandoc_available",
        lambda: False,
    )
    monkeypatch.setattr(
        "prompt_piper_api.services.artifact_service.weasyprint_available",
        lambda: False,
    )

    session_id = _enter_approval_state(service, body=_sample_body())
    result = service.generate_artifacts(session_id)

    assert result.artifact_result is not None
    assert result.artifact_warning is not None
    assert "Pandoc" in result.artifact_warning or "WeasyPrint" in result.artifact_warning
    prompt_id = result.prompt_id
    assert prompt_id
    export_dir = _artifact_dir(artifact_export, prompt_id)
    assert (export_dir / "canonical_prompt.txt").is_file()
    assert (export_dir / "rendered.html").is_file()
    assert not (export_dir / "rendered.pdf").is_file()


def test_registry_metadata_links_artifact_paths(
    service: SessionService,
    registry_path: Path,
    artifact_export: ArtifactExportService,
) -> None:
    session_id = _enter_approval_state(service, body=_sample_body())
    result = service.generate_artifacts(session_id)
    prompt_id = result.prompt_id
    assert prompt_id

    metadata = yaml.safe_load(
        (registry_path / prompt_id / "metadata.yaml").read_text(encoding="utf-8")
    )
    paths = metadata["artifact_paths"]
    assert paths["optimized_md"].endswith("optimized_prompt.md")
    assert "/" in paths["optimized_md"]
    assert paths["manifest"].endswith("artifact_manifest.json")
    assert paths["metrics"].endswith("metrics.json")
    assert "requirement_capture_score" in metadata["evaluation_scores"]


def test_generate_artifacts_transitions_to_exported(service: SessionService) -> None:
    session_id = _enter_approval_state(service, body=_sample_body())
    service.generate_artifacts(session_id)
    record = service.get_session(session_id)
    assert record.session.state is SessionState.EXPORTED


def test_generate_artifacts_rejects_wrong_state(service: SessionService) -> None:
    session_id = _enter_approval_state(service, body=_sample_body())
    record = service.get_session(session_id)
    record.session.state = SessionState.OPTIMIZATION
    with pytest.raises(StateTransitionError, match="Artifact generation"):
        service.generate_artifacts(session_id)


def test_artifact_service_unit_methods() -> None:
    svc = ArtifactService(Path("/tmp/unused"))
    md = svc.generate_markdown(title="Weekly Status", body="Do the thing.")
    assert md.startswith("# Weekly Status")
    assert svc.generate_txt("plain") == "plain"

    html, warning = svc.generate_html("# Title\n\nBody", title="Title")
    assert "<html" in html.lower()
    if not pandoc_available():
        assert warning is not None


def test_api_route_generates_artifacts(
    registry_path: Path,
    export_base: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompt_piper_api.config import get_settings
    from prompt_piper_api.routes import sessions as sessions_routes

    artifact_root = export_base / "exports"
    monkeypatch.setenv("REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("ARTIFACTS_PATH", str(artifact_root))
    monkeypatch.setenv("PROMPT_PIPER_EXPORT_ROOT", str(export_base))
    monkeypatch.setenv("PROMPT_PIPER_HOST_EXPORT_ROOT", str(export_base))
    get_settings.cache_clear()
    sessions_routes._session_service = None

    client = TestClient(app)
    created = client.post(
        "/sessions",
        json={"initial_request": "Summarize weekly engineering status for leadership review."},
    )
    session_id = created.json()["session"]["id"]
    service = sessions_routes.get_session_service()
    drive_session_to_edit(
        service,
        UUID(session_id),
        answers=["Engineering managers", "Bulleted summary with risks"],
    )

    detail = client.get(f"/sessions/{session_id}").json()
    card = detail["requirement_card"]
    card["task_identity"]["objective"] = (
        "Summarize weekly engineering status for leadership review."
    )
    card["unresolved_fields"] = []

    record = service.get_session(UUID(session_id))
    record.session.requirement_card = type(record.session.requirement_card).model_validate(card)
    record.drafts[-1].body = _sample_body()

    client.post(f"/sessions/{session_id}/finalize", json={"acknowledge_first_shot_risk": True})
    client.post(f"/sessions/{session_id}/optimize")
    client.post(f"/sessions/{session_id}/optimize/approve")

    response = client.post(f"/sessions/{session_id}/artifacts")
    assert response.status_code == 200
    body = response.json()
    assert body["artifact_manifest"] is not None
    assert body["export_id"]
    assert body["container_export_path"]
    assert body["expected_host_export_path"]
    assert body["manifest_path"]
    assert body["generated_files"]
    assert body["session"]["state"] == SessionState.EXPORTED.value
    prompt_id = body["prompt_id"]
    latest = ArtifactExportService.resolve_latest_export_dir(artifact_root, prompt_id)
    assert latest is not None
    assert (latest / "artifact_manifest.json").is_file()

    get_settings.cache_clear()
    sessions_routes._session_service = None

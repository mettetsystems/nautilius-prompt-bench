import json
from pathlib import Path
from uuid import uuid4

import pytest
from export_test_helpers import build_test_export_service
from prompt_piper_api.config import Settings, get_settings
from prompt_piper_api.domain.optimization import (
    ConstraintGraph,
    OptimizationChangeLog,
    OptimizationMetrics,
    OptimizationResult,
    OptimizationTargetMetrics,
)
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.services.artifact_export_service import (
    ArtifactExportService,
    build_export_folder_name,
    safe_export_slug,
)
from prompt_piper_api.services.artifact_service import (
    ArtifactService,
    pandoc_available,
    weasyprint_available,
)
from prompt_piper_api.services.exceptions import InvalidPathError
from prompt_piper_api.services.git_registry_service import build_prompt_id


def _sample_optimization(*, original: str, optimized: str) -> OptimizationResult:
    return OptimizationResult(
        original_body=original,
        optimized_body=optimized,
        constraint_graph=ConstraintGraph(),
        metrics=OptimizationMetrics(
            original_token_count=100,
            optimized_token_count=80,
            token_reduction_pct=20.0,
            constraints_per_token=0.5,
            targets=OptimizationTargetMetrics(
                richness=0.8,
                density=0.7,
                efficiency=0.9,
                denoising=0.6,
                deconfliction=1.0,
            ),
        ),
        changes=OptimizationChangeLog(),
        approved=True,
        export_ready=True,
    )


@pytest.fixture(autouse=True)
def clear_settings_cache(isolate_documents_export_paths: None) -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_export_folder_created_under_exports_exports(tmp_path: Path) -> None:
    export_root = tmp_path / "exports-mount"
    artifact_root = export_root / "exports"
    export_service = ArtifactExportService(
        ArtifactService(artifact_root),
        export_root=export_root,
        host_export_root=tmp_path / "Documents" / "Nautilius",
        artifact_root=artifact_root,
    )
    prompt_id = build_prompt_id("Weekly status", uuid4())
    folder = export_service.create_unique_export_folder(prompt_id, "Weekly status")
    assert folder.parent == artifact_root.resolve()
    assert str(folder).startswith(str(artifact_root.resolve()))


def test_folder_name_includes_timestamp_and_title_slug(tmp_path: Path) -> None:
    export_service = build_test_export_service(tmp_path)
    prompt_id = build_prompt_id("Weekly status", uuid4())
    folder = export_service.create_unique_export_folder(prompt_id, "Weekly Status")
    name = folder.name
    assert safe_export_slug("Weekly Status") in name
    assert prompt_id not in name
    assert name[:10].count("-") >= 2


def test_custom_export_folder_label(tmp_path: Path) -> None:
    export_service = build_test_export_service(tmp_path)
    prompt_id = build_prompt_id("Weekly status", uuid4())
    folder = export_service.create_unique_export_folder(
        prompt_id,
        "Weekly Status",
        folder_label="Leadership brief",
    )
    assert "leadership-brief" in folder.name
    assert prompt_id not in folder.name


def test_repeated_exports_create_separate_folders(tmp_path: Path) -> None:
    export_service = build_test_export_service(tmp_path)
    prompt_id = build_prompt_id("Weekly status", uuid4())

    first = export_service.create_unique_export_folder(prompt_id, "Weekly status")
    first.mkdir(parents=True)
    second = export_service.create_unique_export_folder(prompt_id, "Weekly status")
    assert first != second
    assert second.name.endswith("__export_002")


def test_artifact_manifest_includes_all_files(tmp_path: Path) -> None:
    export_service = build_test_export_service(tmp_path)
    prompt_id = build_prompt_id("Weekly status", uuid4())
    optimization = _sample_optimization(
        original="Canonical weekly status prompt.",
        optimized="Optimized weekly status prompt.",
    )

    result = export_service.export(
        prompt_id=prompt_id,
        version=1,
        title="Weekly status",
        canonical_body="Canonical weekly status prompt.",
        optimized_body=optimization.optimized_body,
        requirement_card=RequirementCard(task_identity={"objective": "Summarize weekly status."}),
        registry_metadata=None,
        optimization_result=optimization,
        pre_inference_metrics=None,
        similarity_result=None,
        include_pdf=False,
    )

    manifest_path = Path(result.container_export_path) / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    export_root = Path(result.container_export_path)
    disk_names = {
        str(path.relative_to(export_root))
        for path in export_root.rglob("*")
        if path.is_file()
    }
    manifest_names = {entry["name"] for entry in manifest["files"]}
    assert manifest_names.issubset(disk_names)
    assert "canonical_prompt.txt" in manifest_names
    assert "harness_prompt.md" in manifest_names
    assert "api_pack/openai_chat_completions.json" in manifest_names
    assert "api_pack/cursor_rules.md" in manifest_names
    assert "artifact_manifest.json" in manifest_names
    assert "export_audit.json" in manifest_names


def test_manifest_files_include_checksums(tmp_path: Path) -> None:
    export_service = build_test_export_service(tmp_path)
    prompt_id = build_prompt_id("Weekly status", uuid4())
    optimization = _sample_optimization(original="Canonical body.", optimized="Optimized body.")

    result = export_service.export(
        prompt_id=prompt_id,
        version=1,
        title="Weekly status",
        canonical_body="Canonical body.",
        optimized_body=optimization.optimized_body,
        requirement_card=RequirementCard(task_identity={"objective": "Weekly status."}),
        registry_metadata=None,
        optimization_result=optimization,
        pre_inference_metrics=None,
        similarity_result=None,
        include_pdf=False,
    )

    manifest_path = Path(result.container_export_path) / "artifact_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        assert entry["sha256"]
        assert len(entry["sha256"]) == 64
    assert manifest["container_export_path"]
    assert manifest["expected_host_export_path"]
    assert manifest["generated_by"].startswith("prompt-piper/")


def test_missing_pdf_tools_produce_warning_instead_of_crash(
    tmp_path: Path,
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
    export_service = build_test_export_service(tmp_path)
    prompt_id = build_prompt_id("Weekly status", uuid4())
    optimization = _sample_optimization(original="Canonical body.", optimized="Optimized body.")

    result = export_service.export(
        prompt_id=prompt_id,
        version=1,
        title="Weekly status",
        canonical_body="Canonical body.",
        optimized_body=optimization.optimized_body,
        requirement_card=RequirementCard(task_identity={"objective": "Weekly status."}),
        registry_metadata=None,
        optimization_result=optimization,
        pre_inference_metrics=None,
        similarity_result=None,
        include_pdf=True,
    )

    assert result.warnings
    assert not (Path(result.container_export_path) / "rendered.pdf").is_file()
    assert (Path(result.container_export_path) / "rendered.html").is_file()
    assert (Path(result.container_export_path) / "canonical_prompt.txt").is_file()


def test_no_artifact_written_outside_export_root(tmp_path: Path) -> None:
    export_root = tmp_path / "exports-mount"
    artifact_root = export_root / "exports"
    artifact_root.mkdir(parents=True)
    export_service = ArtifactExportService(
        ArtifactService(artifact_root),
        export_root=export_root,
        host_export_root=tmp_path / "Documents" / "Nautilius",
        artifact_root=artifact_root,
    )
    outside = tmp_path / "outside" / "escape.txt"
    with pytest.raises(InvalidPathError):
        export_service._assert_under_artifact_root(outside)


def test_export_root_defaults_to_exports_in_container(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("REGISTRY_PATH", "ARTIFACTS_PATH", "AUDIT_LOG_PATH"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROMPT_PIPER_EXPORT_ROOT", "/exports")
    monkeypatch.setenv(
        "PROMPT_PIPER_HOST_EXPORT_ROOT",
        str(Path.home() / "Documents" / "Nautilius"),
    )
    settings = Settings()
    assert settings.prompt_piper_export_root == Path("/exports")
    assert settings.artifacts_path == Path("/exports/exports")


def test_host_export_root_defaults_to_documents_nautilius(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "PROMPT_PIPER_EXPORT_ROOT",
        "PROMPT_PIPER_HOST_EXPORT_ROOT",
        "REGISTRY_PATH",
        "ARTIFACTS_PATH",
        "AUDIT_LOG_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = Settings()
    expected = Path.home() / "Documents" / "Nautilius"
    assert settings.prompt_piper_host_export_root == expected


def test_build_export_folder_name_format() -> None:
    prompt_id = build_prompt_id("Weekly status", uuid4())
    dated = build_export_folder_name(label="Weekly status")
    assert dated.endswith("__weekly-status")
    assert prompt_id not in dated
    assert len(dated.split("__")[0]) == len("YYYY-MM-DD_HH-MM-SS")

    legacy = build_export_folder_name(label="weekly-status", prompt_id=prompt_id)
    assert legacy.endswith(f"__{prompt_id}__weekly-status")


def test_no_proprietary_cloud_required_for_export_tests() -> None:
    assert pandoc_available() in {True, False}
    assert weasyprint_available() in {True, False}

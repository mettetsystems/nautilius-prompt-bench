from __future__ import annotations

from pathlib import Path

from prompt_piper_api.config import Settings
from prompt_piper_api.services.artifact_factory import create_artifact_export_service
from prompt_piper_api.services.audit_log_service import AuditLogService
from prompt_piper_api.services.clarification_flow import drive_session_to_edit
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.external_inference_service import ExternalInferenceService
from prompt_piper_api.services.git_registry_service import GitRegistryService
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.session_service import SessionService
from prompt_piper_api.services.similarity_check_service import SimilarityCheckService
from prompt_piper_api.services.similarity_factory import create_similarity_check_service

from prompt_piper.demo.scenario import DemoRunResult, DemoScenario, load_scenario


def build_demo_service(
    *,
    registry_path: Path,
    artifacts_path: Path,
    audit_path: Path | None = None,
    similarity_index_path: Path | None = None,
) -> SessionService:
    audit_path = audit_path or artifacts_path.parent / "audit"
    settings = Settings(
        registry_path=registry_path,
        artifacts_path=artifacts_path,
        audit_log_path=audit_path,
        prompt_piper_export_root=artifacts_path.parent,
        prompt_piper_host_export_root=artifacts_path.parent,
        prompt_piper_registry_root=registry_path,
        prompt_piper_artifact_root=artifacts_path,
        prompt_piper_external_enabled=False,
        similarity_index_path=similarity_index_path,
        prompt_piper_embedding_fallback=True,
    )
    similarity: SimilarityCheckService | None = None
    if similarity_index_path is not None:
        similarity = create_similarity_check_service(
            settings,
            index_path=similarity_index_path,
            embedding=EmbeddingService(prefer_fallback=True),
        )
    return SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=similarity,
        optimizer=TokenOptimizationEngine(),
        artifact_export=create_artifact_export_service(settings),
        external_inference=ExternalInferenceService(
            settings,
            AuditLogService(audit_path),
            artifacts_path,
        ),
    )


def run_coding_prompt_demo(
    *,
    registry_path: Path,
    artifacts_path: Path,
    audit_path: Path | None = None,
    similarity_index_path: Path | None = None,
    scenario_path: Path | None = None,
) -> DemoRunResult:
    scenario = load_scenario(scenario_path)
    similarity_index_path = similarity_index_path or artifacts_path.parent / "similarity_index.json"
    service = build_demo_service(
        registry_path=registry_path,
        artifacts_path=artifacts_path,
        audit_path=audit_path,
        similarity_index_path=similarity_index_path,
    )
    return execute_demo_flow(
        service,
        scenario,
        registry_path=registry_path,
        artifacts_path=artifacts_path,
    )


def execute_demo_flow(
    service: SessionService,
    scenario: DemoScenario,
    *,
    registry_path: Path,
    artifacts_path: Path,
) -> DemoRunResult:
    created = service.create_session(
        initial_request=scenario.initial_request,
        title=scenario.title,
    )
    session_id = created.record.session.id

    drive_session_to_edit(
        service,
        session_id,
        answers=list(scenario.clarification_answers),
    )
    record = service.get_session(session_id)
    assert record.current_draft is not None

    for instruction in scenario.edit_instructions:
        service.edit_draft(session_id, instruction)

    finalized = service.finalize(session_id, acknowledge_first_shot_risk=True)
    prompt_id = finalized.prompt_id
    if not prompt_id:
        msg = "Demo finalization did not assign a prompt_id."
        raise RuntimeError(msg)

    service.optimize(session_id)
    service.approve_optimization(session_id)
    artifact_result = service.generate_artifacts(session_id)

    registry_dir = registry_path / prompt_id
    generation = artifact_result.artifact_result
    artifact_dir = (
        Path(generation.artifact_dir) if generation is not None else artifacts_path / prompt_id
    )
    manifest_files = (
        [artifact_dir / entry.name for entry in generation.manifest.files]
        if generation is not None
        else []
    )

    artifact_paths = sorted(
        {path for path in manifest_files if path.is_file()},
        key=lambda item: item.name,
    )

    return DemoRunResult(
        session_id=str(session_id),
        prompt_id=prompt_id,
        registry_dir=registry_dir,
        artifact_dir=artifact_dir,
        artifact_paths=artifact_paths,
    )


# Back-compat alias for older imports / scripts.
run_implementation_report_demo = run_coding_prompt_demo

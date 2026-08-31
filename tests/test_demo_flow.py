from pathlib import Path

import pytest
import yaml
from prompt_piper.demo.runner import build_demo_service, run_coding_prompt_demo
from prompt_piper.demo.scenario import DemoScenario, load_scenario
from prompt_piper_api.domain.enums import SessionState
from tests.clarification_helpers import drive_session_to_edit


@pytest.fixture
def demo_registry_path(tmp_path: Path) -> Path:
    return tmp_path / "registry"


@pytest.fixture
def demo_artifacts_path(tmp_path: Path) -> Path:
    return tmp_path / "artifacts"


@pytest.fixture
def demo_similarity_index_path(tmp_path: Path) -> Path:
    return tmp_path / "similarity_index.json"


@pytest.fixture
def demo_scenario() -> DemoScenario:
    return load_scenario()


def test_coding_prompt_demo_end_to_end(
    demo_registry_path: Path,
    demo_artifacts_path: Path,
    demo_similarity_index_path: Path,
    demo_scenario: DemoScenario,
) -> None:
    service = build_demo_service(
        registry_path=demo_registry_path,
        artifacts_path=demo_artifacts_path,
        similarity_index_path=demo_similarity_index_path,
    )

    created = service.create_session(
        initial_request=demo_scenario.initial_request,
        title=demo_scenario.title,
    )
    session_id = created.record.session.id
    assert created.clarification_field in {
        "agent_contract.definition_of_done",
        "agent_contract.change_scope",
        "agent_contract.architecture_policy",
    }

    drive_session_to_edit(
        service,
        session_id,
        answers=list(demo_scenario.clarification_answers),
    )
    record = service.get_session(session_id)
    draft = record.current_draft
    assert draft is not None
    initial_body = draft.body.lower()
    for phrase in demo_scenario.expected_initial_draft_contains:
        assert phrase.lower() in initial_body, f"missing expected phrase: {phrase}"

    assert record.session.state is SessionState.EDIT

    for instruction in demo_scenario.edit_instructions:
        service.edit_draft(session_id, instruction)

    edited_body = service.get_session(session_id).current_draft
    assert edited_body is not None
    edited_lower = edited_body.body.lower()
    for phrase in demo_scenario.expected_after_edits_contains:
        assert phrase.lower() in edited_lower, f"missing after edits: {phrase}"

    finalized = service.finalize(session_id, acknowledge_first_shot_risk=True)
    prompt_id = finalized.prompt_id
    assert prompt_id
    assert finalized.similarity_result is not None
    assert service.get_session(session_id).session.state is SessionState.SIMILARITY_CHECK

    service.optimize(session_id)
    assert service.get_session(session_id).session.state is SessionState.OPTIMIZATION

    service.approve_optimization(session_id)
    artifacts = service.generate_artifacts(session_id)

    assert artifacts.artifact_result is not None
    from prompt_piper_api.services.artifact_export_service import ArtifactExportService

    artifact_dir = ArtifactExportService.resolve_latest_export_dir(demo_artifacts_path, prompt_id)
    assert artifact_dir is not None and artifact_dir.is_dir()

    for filename in demo_scenario.core_artifact_files:
        assert (artifact_dir / filename).is_file(), f"missing artifact: {filename}"

    manifest = yaml.safe_load((artifact_dir / "artifact_manifest.json").read_text())
    manifest_names = {entry["name"] for entry in manifest["files"]}
    for filename in demo_scenario.core_artifact_files:
        assert filename in manifest_names

    registry_dir = demo_registry_path / prompt_id
    for filename in demo_scenario.registry_files:
        assert (registry_dir / filename).is_file(), f"missing registry file: {filename}"

    assert service.get_session(session_id).session.state is SessionState.EXPORTED


def test_demo_runner_module(
    demo_registry_path: Path,
    demo_artifacts_path: Path,
    demo_similarity_index_path: Path,
) -> None:
    result = run_coding_prompt_demo(
        registry_path=demo_registry_path,
        artifacts_path=demo_artifacts_path,
        similarity_index_path=demo_similarity_index_path,
    )
    assert result.prompt_id
    assert result.artifact_dir.is_dir()

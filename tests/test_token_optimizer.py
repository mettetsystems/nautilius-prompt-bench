from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from prompt_piper_api.domain.enums import SessionState
from prompt_piper_api.services.exceptions import StateTransitionError
from prompt_piper_api.services.git_registry_service import GitRegistryService
from prompt_piper_api.services.optimization.engine import TokenOptimizationEngine
from prompt_piper_api.services.optimization.metrics import ApprovalExportPass
from prompt_piper_api.services.session_service import SessionService
from tests.clarification_helpers import drive_session_to_edit


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "registry"


@pytest.fixture
def service(registry_path: Path) -> SessionService:
    return SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=None,
        optimizer=TokenOptimizationEngine(),
    )


def _sample_body(*, repeat_line: str | None = None, conflict: bool = False) -> str:
    lines = [
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
    ]
    if conflict:
        lines.extend(
            [
                "Be exhaustive and comprehensive in coverage.",
                "Keep a minimal token footprint with a short answer.",
                "Follow a minimum-necessary change policy.",
                "The agent may rewrite unrelated subsystems and change anything.",
                "Pause and persist when blocked.",
                "Never pause and never escalate; spin indefinitely.",
                "No force-push.",
                "git push --force is allowed.",
            ]
        )
    if repeat_line:
        lines.extend(["", "Technical Context", "-----------------", repeat_line, repeat_line])
    lines.extend(
        [
            "",
            "Inputs, Outputs, and Contracts",
            "------------------------------",
            "Output contract: JSON with blockers, owners, and next steps.",
            "",
            "Edge Cases and Error Strategy",
            "-----------------------------",
            "Failure handling: raise HTTPException on validation errors.",
            "",
            "Response Formatting",
            "-------------------",
            "Explanation level: brief rationale then code.",
            "Covers blockers and owners.",
        ]
    )
    return "\n".join(lines)

def _enter_similarity_check(
    service: SessionService,
    *,
    body: str | None = None,
) -> UUID:
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
    return session_id


def test_optimizer_preserves_objective(service: SessionService) -> None:
    session_id = _enter_similarity_check(service, body=_sample_body())
    card = service.get_session(session_id).session.requirement_card

    result = service.optimize(session_id)
    assert result.optimization_result is not None
    assert ApprovalExportPass.objective_preserved(
        result.optimization_result.original_body,
        result.optimization_result.optimized_body,
        card,
    )
    assert "weekly engineering status" in result.optimization_result.optimized_body.lower()


def test_optimizer_removes_repeated_text(service: SessionService) -> None:
    repeat = "Audience: Engineering managers"
    session_id = _enter_similarity_check(service, body=_sample_body(repeat_line=repeat))

    result = service.optimize(session_id)
    assert result.optimization_result is not None
    # Contract rewrite drops draft-only filler; repeated audience lines must not survive.
    assert result.optimization_result.optimized_body.count(repeat) == 0
    assert "Long-Horizon Coding Agent Contract" in result.optimization_result.optimized_body
    assert "Task Identity" in result.optimization_result.optimized_body
    notes = " ".join(result.optimization_result.changes.clarified)
    assert "long-horizon" in notes.lower() or "clarity" in notes.lower()


def test_optimizer_flags_hard_conflicts(service: SessionService) -> None:
    session_id = _enter_similarity_check(service, body=_sample_body(conflict=True))

    result = service.optimize(session_id)
    assert result.optimization_result is not None
    descriptions = {item.description for item in result.optimization_result.hard_conflicts}
    assert "be exhaustive vs minimal tokens" in descriptions
    assert "minimum-necessary change vs unrestricted edits" in descriptions
    assert "pause-and-persist vs never stop" in descriptions
    assert "no force-push vs force-push allowed" in descriptions


def test_optimizer_returns_metrics(service: SessionService) -> None:
    session_id = _enter_similarity_check(service, body=_sample_body())

    result = service.optimize(session_id)
    assert result.optimization_result is not None
    metrics = result.optimization_result.metrics
    assert metrics.original_token_count > 0
    assert metrics.optimized_token_count > 0
    assert metrics.targets.clarity >= 0.0
    assert metrics.targets.richness >= 0.0
    assert metrics.targets.density >= 0.0
    assert metrics.targets.efficiency >= 0.0
    assert metrics.targets.denoising >= 0.0
    assert metrics.targets.deconfliction >= 0.0
    assert len(result.optimization_result.passes_completed) == 5


def test_does_not_export_without_approval(service: SessionService) -> None:
    session_id = _enter_similarity_check(service, body=_sample_body())

    optimized = service.optimize(session_id)
    assert optimized.optimization_result is not None
    assert optimized.optimization_result.export_ready is False
    assert optimized.optimization_result.approved is False

    approved = service.approve_optimization(session_id)
    assert approved.optimization_result is not None
    assert approved.optimization_result.export_ready is True
    assert approved.optimization_result.approved is True
    assert approved.record.session.state is SessionState.APPROVAL


def test_approval_blocked_when_hard_conflicts_exist(service: SessionService) -> None:
    session_id = _enter_similarity_check(service, body=_sample_body(conflict=True))
    service.optimize(session_id)

    with pytest.raises(StateTransitionError):
        service.approve_optimization(session_id)


def test_optimize_api_route(client: TestClient, service: SessionService) -> None:
    from prompt_piper_api.main import app
    from prompt_piper_api.routes.sessions import get_session_service

    session_id = _enter_similarity_check(service, body=_sample_body())
    app.dependency_overrides[get_session_service] = lambda: service
    try:
        response = client.post(f"/sessions/{session_id}/optimize")
        assert response.status_code == 200
        body = response.json()
        assert body["optimization_result"] is not None
        assert body["session"]["state"] == SessionState.OPTIMIZATION
    finally:
        app.dependency_overrides.clear()

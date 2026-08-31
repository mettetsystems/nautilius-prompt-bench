from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from prompt_piper_api.main import app
from prompt_piper_api.services.git_registry_service import GitRegistryService


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "registry"


@pytest.fixture
def artifacts_path(tmp_path: Path) -> Path:
    return tmp_path / "artifacts"


@pytest.fixture
def client(
    registry_path: Path,
    artifacts_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    from prompt_piper_api.config import get_settings
    from prompt_piper_api.routes import registry as registry_routes

    monkeypatch.setenv("REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("ARTIFACTS_PATH", str(artifacts_path))
    get_settings.cache_clear()
    registry_routes._browse_service = None
    return TestClient(app)


def test_list_registry_prompts_empty(client: TestClient) -> None:
    response = client.get("/registry/prompts")
    assert response.status_code == 200
    assert response.json() == []


def test_get_registry_prompt_detail(
    client: TestClient,
    registry_path: Path,
    artifacts_path: Path,
) -> None:
    registry = GitRegistryService(registry_path)
    from prompt_piper_api.domain.requirement_card import RequirementCard

    card = RequirementCard(task_identity={"objective": "Summarize status updates."})
    registry.finalize_prompt(
        prompt_id="weekly-status-abc12345",
        version=1,
        title="Weekly Status",
        body="Summarize the week.",
        requirement_card=card,
        session_id=__import__("uuid").uuid4(),
    )

    artifact_dir = artifacts_path / "weekly-status-abc12345"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "optimized_prompt.txt").write_text("Optimized body", encoding="utf-8")

    listed = client.get("/registry/prompts")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["prompt_id"] == "weekly-status-abc12345"

    detail = client.get("/registry/prompts/weekly-status-abc12345")
    assert detail.status_code == 200
    body = detail.json()
    assert body["metadata"]["title"] == "Weekly Status"
    assert "Summarize the week." in body["canonical_prompt"]
    assert body["requirement_card"]["task_identity"]["objective"] == "Summarize status updates."

    metadata = yaml.safe_load(
        (registry_path / "weekly-status-abc12345" / "metadata.yaml").read_text()
    )
    assert metadata["artifact_paths"]["canonical_txt"] == "canonical_prompt.txt"


def test_get_registry_prompt_not_found(client: TestClient) -> None:
    response = client.get("/registry/prompts/missing-prompt")
    assert response.status_code == 404

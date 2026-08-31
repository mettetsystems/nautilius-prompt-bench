from pathlib import Path
from uuid import UUID

import pytest
from prompt_piper_api.config import Settings
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.domain.similarity import SIMILARITY_WARNING_MESSAGE
from prompt_piper_api.services.embedding_service import EmbeddingService
from prompt_piper_api.services.git_registry_service import GitRegistryService
from prompt_piper_api.services.session_service import SessionService
from prompt_piper_api.services.similarity_check_service import SimilarityCheckService
from prompt_piper_api.services.similarity_factory import create_similarity_check_service
from tests.clarification_helpers import drive_session_to_edit


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    return tmp_path / "registry"


@pytest.fixture
def similarity_index_path(tmp_path: Path) -> Path:
    return tmp_path / "similarity_index.json"


@pytest.fixture
def embedding_service() -> EmbeddingService:
    return EmbeddingService(prefer_fallback=True)


@pytest.fixture
def similarity_service(
    similarity_index_path: Path,
    embedding_service: EmbeddingService,
) -> SimilarityCheckService:
    settings = Settings(
        similarity_index_path=similarity_index_path,
        similarity_warning_threshold=0.90,
        prompt_piper_embedding_fallback=True,
    )
    return create_similarity_check_service(
        settings,
        index_path=similarity_index_path,
        embedding=embedding_service,
    )


@pytest.fixture
def service(
    registry_path: Path,
    similarity_service: SimilarityCheckService,
) -> SessionService:
    return SessionService(
        llm=None,
        registry=GitRegistryService(registry_path),
        similarity=similarity_service,
    )


def _enter_edit_state(service: SessionService) -> UUID:
    created = service.create_session(initial_request="Draft a weekly status update prompt")
    session_id = created.record.session.id
    drive_session_to_edit(
        service,
        session_id,
        answers=["Engineering managers", "Bulleted summary with risks"],
    )
    return session_id


def test_embedding_fallback_works(embedding_service: EmbeddingService) -> None:
    assert embedding_service.using_fallback is True
    vectors = embedding_service.embed(["hello world", "completely different topic"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    assert vectors[0] != vectors[1]


def test_similarity_score_threshold_triggers_warning(
    similarity_service: SimilarityCheckService,
) -> None:
    body = (
        "Core Task and Scope: summarize weekly status for engineering managers.\n"
        "Technical Context: include risks and next steps.\n"
        "Output contract: bulleted summary."
    )
    card = RequirementCard(task_identity={"objective": "Weekly status summary"})
    artifact_paths = {"canonical_txt": "canonical_prompt.txt"}

    similarity_service.check_and_index(
        prompt_id="weekly-status-prior1234",
        version=1,
        title="Weekly status",
        body=body,
        abstract="Weekly status summary",
        requirement_card=card,
        artifact_paths=artifact_paths,
    )

    result = similarity_service.check_and_index(
        prompt_id="weekly-status-new5678",
        version=1,
        title="Weekly status v2",
        body=body,
        abstract="Weekly status summary",
        requirement_card=card,
        artifact_paths=artifact_paths,
    )

    assert result.warning == SIMILARITY_WARNING_MESSAGE
    assert result.matches
    assert result.matches[0].similarity_score >= 0.90


def test_lower_similarity_does_not_warn(similarity_service: SimilarityCheckService) -> None:
    card = RequirementCard(task_identity={"objective": "Different objectives"})
    artifact_paths = {"canonical_txt": "canonical_prompt.txt"}

    similarity_service.check_and_index(
        prompt_id="legal-contract-prior12",
        version=1,
        title="Legal contract review",
        body="Core Task and Scope: review vendor contracts for liability clauses and indemnification.",
        abstract="Contract review",
        requirement_card=card,
        artifact_paths=artifact_paths,
    )

    result = similarity_service.check_and_index(
        prompt_id="recipe-generator-new34",
        version=1,
        title="Recipe generator",
        body="Core Task and Scope: create vegetarian dinner recipes with pantry ingredients and timing.",
        abstract="Recipe generation",
        requirement_card=card,
        artifact_paths=artifact_paths,
    )

    assert result.warning is None


def test_three_documents_are_indexed_per_finalized_prompt(
    similarity_service: SimilarityCheckService,
) -> None:
    prompt_id = "three-doc-prompt-abcd"
    similarity_service.check_and_index(
        prompt_id=prompt_id,
        version=1,
        title="Indexed prompt",
        body="Core Task and Scope: draft onboarding checklist for new hires.",
        abstract="Onboarding checklist",
        requirement_card=RequirementCard(
            task_identity={
                "objective": "Onboarding checklist",
                "additional_constraints": ["Cover first-week tasks", "Keep it concise"],
            },
        ),
        artifact_paths={"canonical_txt": "canonical_prompt.txt"},
    )

    count = similarity_service._index.count_documents_for_prompt(prompt_id)
    assert count == 3


def test_prior_prompt_metadata_is_returned(similarity_service: SimilarityCheckService) -> None:
    body = "Core Task and Scope: summarize customer interview notes for product discovery."
    artifact_paths = {
        "canonical_txt": "canonical_prompt.txt",
        "metadata": "metadata.yaml",
    }

    similarity_service.check_and_index(
        prompt_id="customer-interview-prior",
        version=1,
        title="Customer interview summary",
        body=body,
        abstract="Interview summary",
        requirement_card=RequirementCard(task_identity={"objective": "Interview summary"}),
        artifact_paths=artifact_paths,
    )

    result = similarity_service.check_and_index(
        prompt_id="customer-interview-new",
        version=1,
        title="Customer interview summary v2",
        body=body,
        abstract="Interview summary",
        requirement_card=RequirementCard(task_identity={"objective": "Interview summary"}),
        artifact_paths=artifact_paths,
    )

    assert result.matches
    top = result.matches[0]
    assert top.prompt_id == "customer-interview-prior"
    assert top.title == "Customer interview summary"
    assert top.artifact_paths["canonical_txt"] == "canonical_prompt.txt"
    assert top.similarity_score >= 0.90


def test_finalize_runs_similarity_check(service: SessionService) -> None:
    session_id = _enter_edit_state(service)
    result = service.finalize(session_id, acknowledge_first_shot_risk=True)

    assert result.prompt_id
    assert result.similarity_result is not None

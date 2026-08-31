from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from prompt_piper_api.db.similarity_models import SimilarityDocumentRow
from prompt_piper_api.domain.requirement_card import RequirementCard
from prompt_piper_api.domain.similarity import DocumentKind
from prompt_piper_api.services.similarity_utils import (
    deserialize_embedding,
    lexical_overlap_score,
    serialize_embedding,
)


@dataclass(frozen=True)
class IndexedDocument:
    prompt_id: str
    version: int
    title: str
    document_kind: DocumentKind
    text: str
    embedding: list[float]
    artifact_paths: dict[str, str]
    indexed_at: datetime | None = None


def compress_abstract(abstract: str, body: str, *, max_len: int = 400) -> str:
    source = abstract.strip() or body.strip()
    if len(source) <= max_len:
        return source
    return source[: max_len - 3].rstrip() + "..."


def build_lessons_learned(card: RequirementCard) -> str:
    parts: list[str] = []
    if card.task_identity.additional_constraints:
        parts.append(
            "Constraints: " + "; ".join(card.task_identity.additional_constraints)
        )
    if card.agent_contract.change_scope.strip():
        parts.append("Change scope: " + card.agent_contract.change_scope.strip()[:240])
    if card.agent_contract.failure_recovery.strip():
        parts.append("Failure recovery: " + card.agent_contract.failure_recovery.strip()[:240])
    if card.agent_contract.tool_safety.strip():
        parts.append("Tool safety: " + card.agent_contract.tool_safety.strip()[:240])
    return "\n".join(parts) if parts else "No lessons captured yet."


def build_index_documents(
    *,
    prompt_id: str,
    version: int,
    title: str,
    body: str,
    abstract: str,
    requirement_card: RequirementCard,
    artifact_paths: dict[str, str],
    embeddings: list[list[float]],
) -> list[IndexedDocument]:
    texts = [
        body,
        compress_abstract(abstract, body),
        build_lessons_learned(requirement_card),
    ]
    kinds = [
        DocumentKind.CANONICAL,
        DocumentKind.ABSTRACT,
        DocumentKind.LESSONS_LEARNED,
    ]
    if len(embeddings) != len(kinds):
        msg = "Expected three embeddings for canonical, abstract, and lessons-learned documents"
        raise ValueError(msg)

    indexed_at = datetime.now(tz=UTC)
    return [
        IndexedDocument(
            prompt_id=prompt_id,
            version=version,
            title=title,
            document_kind=kind,
            text=document_text,
            embedding=embedding,
            artifact_paths=artifact_paths,
            indexed_at=indexed_at,
        )
        for kind, document_text, embedding in zip(kinds, texts, embeddings, strict=True)
    ]


class SimilarityIndexStore(Protocol):
    def replace_prompt_documents(self, documents: list[IndexedDocument]) -> None: ...

    def list_documents(
        self,
        *,
        exclude_prompt_id: str | None = None,
        min_indexed_at: datetime | None = None,
    ) -> list[IndexedDocument]: ...

    def count_documents_for_prompt(self, prompt_id: str) -> int: ...

    def lexical_candidate_prompt_ids(self, query: str, *, limit: int = 50) -> list[str]: ...


class JsonSimilarityIndexStore:
    """File-backed similarity index for early local development."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def replace_prompt_documents(self, documents: list[IndexedDocument]) -> None:
        if not documents:
            return
        payload = self._load()
        prompt_id = documents[0].prompt_id
        payload["documents"] = [
            item
            for item in payload["documents"]
            if item.get("prompt_id") != prompt_id
        ]
        payload["documents"].extend(self._serialize(document) for document in documents)
        self._save(payload)

    def list_documents(
        self,
        *,
        exclude_prompt_id: str | None = None,
        min_indexed_at: datetime | None = None,
    ) -> list[IndexedDocument]:
        payload = self._load()
        documents: list[IndexedDocument] = []
        for item in payload["documents"]:
            if exclude_prompt_id and item.get("prompt_id") == exclude_prompt_id:
                continue
            document = self._deserialize(item)
            if min_indexed_at is not None:
                indexed_at = document.indexed_at
                if indexed_at is None or indexed_at < min_indexed_at:
                    continue
            documents.append(document)
        return documents

    def count_documents_for_prompt(self, prompt_id: str) -> int:
        payload = self._load()
        return sum(1 for item in payload["documents"] if item.get("prompt_id") == prompt_id)

    def lexical_candidate_prompt_ids(self, query: str, *, limit: int = 50) -> list[str]:
        scored: dict[str, float] = {}
        for document in self.list_documents():
            score = lexical_overlap_score(query, document.text)
            if score <= 0.0:
                continue
            current = scored.get(document.prompt_id, 0.0)
            scored[document.prompt_id] = max(current, score)
        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
        return [prompt_id for prompt_id, _score in ranked[:limit]]

    def _load(self) -> dict[str, list[dict[str, object]]]:
        if not self._path.exists():
            return {"documents": []}
        data = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"documents": []}
        documents = data.get("documents", [])
        if not isinstance(documents, list):
            return {"documents": []}
        return {"documents": documents}

    def _save(self, payload: dict[str, list[dict[str, object]]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _serialize(document: IndexedDocument) -> dict[str, object]:
        payload = {
            "prompt_id": document.prompt_id,
            "version": document.version,
            "title": document.title,
            "document_kind": document.document_kind.value,
            "text": document.text,
            "embedding": document.embedding,
            "artifact_paths": document.artifact_paths,
        }
        if document.indexed_at is not None:
            payload["indexed_at"] = document.indexed_at.isoformat()
        return payload

    @staticmethod
    def _deserialize(item: dict[str, object]) -> IndexedDocument:
        raw_embedding = item.get("embedding", [])
        raw_paths = item.get("artifact_paths", {})
        embedding_values: list[float] = []
        if isinstance(raw_embedding, list):
            embedding_values = [float(value) for value in raw_embedding]
        artifact_paths: dict[str, str] = {}
        if isinstance(raw_paths, dict):
            artifact_paths = {str(key): str(value) for key, value in raw_paths.items()}
        indexed_at: datetime | None = None
        raw_indexed_at = item.get("indexed_at")
        if isinstance(raw_indexed_at, str) and raw_indexed_at:
            indexed_at = datetime.fromisoformat(raw_indexed_at)
        return IndexedDocument(
            prompt_id=str(item["prompt_id"]),
            version=int(str(item["version"])),
            title=str(item.get("title", "")),
            document_kind=DocumentKind(str(item["document_kind"])),
            text=str(item["text"]),
            embedding=embedding_values,
            artifact_paths=artifact_paths,
            indexed_at=indexed_at,
        )


class DatabaseSimilarityIndexStore:
    """SQLite or PostgreSQL-backed similarity index."""

    def __init__(self, engine: Engine, *, use_postgres_fts: bool) -> None:
        self._engine = engine
        self._use_postgres_fts = use_postgres_fts

    def replace_prompt_documents(self, documents: list[IndexedDocument]) -> None:
        if not documents:
            return
        prompt_id = documents[0].prompt_id
        with Session(self._engine) as session:
            rows = session.exec(
                select(SimilarityDocumentRow).where(SimilarityDocumentRow.prompt_id == prompt_id)
            ).all()
            for row in rows:
                session.delete(row)
            for document in documents:
                session.add(self._to_row(document))
            session.commit()

    def list_documents(
        self,
        *,
        exclude_prompt_id: str | None = None,
        min_indexed_at: datetime | None = None,
    ) -> list[IndexedDocument]:
        with Session(self._engine) as session:
            statement = select(SimilarityDocumentRow)
            if exclude_prompt_id:
                statement = statement.where(SimilarityDocumentRow.prompt_id != exclude_prompt_id)
            if min_indexed_at is not None:
                statement = statement.where(SimilarityDocumentRow.created_at >= min_indexed_at)
            rows = session.exec(statement).all()
            return [self._from_row(row) for row in rows]

    def count_documents_for_prompt(self, prompt_id: str) -> int:
        with Session(self._engine) as session:
            rows = session.exec(
                select(SimilarityDocumentRow).where(SimilarityDocumentRow.prompt_id == prompt_id)
            ).all()
            return len(rows)

    def lexical_candidate_prompt_ids(self, query: str, *, limit: int = 50) -> list[str]:
        if self._use_postgres_fts:
            return self._postgres_fts_candidates(query, limit=limit)
        scored: dict[str, float] = {}
        for document in self.list_documents():
            score = lexical_overlap_score(query, document.text)
            if score <= 0.0:
                continue
            current = scored.get(document.prompt_id, 0.0)
            scored[document.prompt_id] = max(current, score)
        ranked = sorted(scored.items(), key=lambda item: item[1], reverse=True)
        return [prompt_id for prompt_id, _score in ranked[:limit]]

    def _postgres_fts_candidates(self, query: str, *, limit: int) -> list[str]:
        sql = text(
            """
            SELECT DISTINCT prompt_id
            FROM similarity_documents
            WHERE to_tsvector('english', text) @@ plainto_tsquery('english', :query)
            LIMIT :limit
            """
        )
        with self._engine.connect() as connection:
            rows = connection.execute(sql, {"query": query, "limit": limit}).fetchall()
        return [str(row[0]) for row in rows]

    @staticmethod
    def _to_row(document: IndexedDocument) -> SimilarityDocumentRow:
        return SimilarityDocumentRow(
            prompt_id=document.prompt_id,
            version=document.version,
            title=document.title,
            document_kind=document.document_kind.value,
            text=document.text,
            embedding_json=serialize_embedding(document.embedding),
            artifact_paths_json=json.dumps(document.artifact_paths),
            created_at=datetime.now(tz=UTC),
        )

    @staticmethod
    def _from_row(row: SimilarityDocumentRow) -> IndexedDocument:
        artifact_paths = json.loads(row.artifact_paths_json)
        return IndexedDocument(
            prompt_id=row.prompt_id,
            version=row.version,
            title=row.title,
            document_kind=DocumentKind(row.document_kind),
            text=row.text,
            embedding=deserialize_embedding(row.embedding_json),
            artifact_paths={
                str(key): str(value) for key, value in artifact_paths.items()
            },
            indexed_at=row.created_at,
        )


class SimilarityIndexService:
    """Index finalized prompts as three retrievable documents."""

    def __init__(self, store: SimilarityIndexStore) -> None:
        self._store = store

    @property
    def store(self) -> SimilarityIndexStore:
        return self._store

    def index_prompt(
        self,
        *,
        prompt_id: str,
        version: int,
        title: str,
        body: str,
        abstract: str,
        requirement_card: RequirementCard,
        artifact_paths: dict[str, str],
        embeddings: list[list[float]],
    ) -> list[IndexedDocument]:
        documents = build_index_documents(
            prompt_id=prompt_id,
            version=version,
            title=title,
            body=body,
            abstract=abstract,
            requirement_card=requirement_card,
            artifact_paths=artifact_paths,
            embeddings=embeddings,
        )
        self._store.replace_prompt_documents(documents)
        return documents

    def list_documents(
        self,
        *,
        exclude_prompt_id: str | None = None,
        min_indexed_at: datetime | None = None,
    ) -> list[IndexedDocument]:
        return self._store.list_documents(
            exclude_prompt_id=exclude_prompt_id,
            min_indexed_at=min_indexed_at,
        )

    def count_documents_for_prompt(self, prompt_id: str) -> int:
        return self._store.count_documents_for_prompt(prompt_id)

    def lexical_candidate_prompt_ids(self, query: str, *, limit: int = 50) -> list[str]:
        return self._store.lexical_candidate_prompt_ids(query, limit=limit)

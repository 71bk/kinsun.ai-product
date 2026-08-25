from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from rag_ingestion.embedding_types import EmbeddingError, EmbeddingResult
from rag_ingestion.postgres_embedding_artifact import (
    generate_authorized_postgres_embedding_artifact,
)


@dataclass(frozen=True)
class _Chunk:
    chunk_id: str
    embedding_text: str
    embedding_text_sha256: str


class _Embedder:
    model_id = "gemini-embedding-001"
    dimension = 1024

    def __init__(self) -> None:
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        self.calls += 1
        vectors = tuple(tuple(float(index) / 1024 for index in range(1024)) for _ in texts)
        return EmbeddingResult(
            vectors=vectors,
            success_count=len(texts),
            failure_count=0,
        )


def _chunk(chunk_id: str, text: str) -> _Chunk:
    return _Chunk(
        chunk_id=chunk_id,
        embedding_text=text,
        embedding_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def test_generates_atomic_profile_bound_artifact_outside_repository(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact_path = tmp_path / "external" / "embeddings.jsonl"
    embedder = _Embedder()

    result = generate_authorized_postgres_embedding_artifact(
        authorization_status="STAGING_EMBEDDING_AUTHORIZED",
        authorized_allowlist_sha256="a" * 64,
        provider="google",
        model_id=embedder.model_id,
        dimension=embedder.dimension,
        document_task_type="RETRIEVAL_DOCUMENT",
        config_version="1.0.0",
        expected_chunk_count=2,
        embedder=embedder,
        chunks=(
            _chunk("synthetic_001", "合成公開資料一"),
            _chunk("synthetic_002", "合成公開資料二"),
        ),
        artifact_path=artifact_path,
        repository_root=repository_root,
        rag_mode="staging",
        production_enabled=False,
    )

    rows = [json.loads(line) for line in artifact_path.read_text(encoding="utf-8").splitlines()]
    assert embedder.calls == 1
    assert rows[0] == {
        "record_type": "manifest",
        "schema_version": "2.0.0",
        "allowlist_sha256": "a" * 64,
        "embedding_provider": "google",
        "embedding_model_id": "gemini-embedding-001",
        "embedding_dimension": 1024,
        "document_task_type": "RETRIEVAL_DOCUMENT",
        "config_version": "1.0.0",
        "chunk_count": 2,
    }
    assert len(rows) == 3
    assert result.artifact_sha256 == hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    assert result.success_count == 2
    assert result.failure_count == 0
    assert not list(artifact_path.parent.glob(".*.tmp"))


def test_rejects_unapproved_profile_before_provider_call(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    embedder = _Embedder()

    with pytest.raises(EmbeddingError, match="Google provider"):
        generate_authorized_postgres_embedding_artifact(
            authorization_status="STAGING_EMBEDDING_AUTHORIZED",
            authorized_allowlist_sha256="a" * 64,
            provider="bedrock",
            model_id=embedder.model_id,
            dimension=1024,
            document_task_type="RETRIEVAL_DOCUMENT",
            config_version="1.0.0",
            expected_chunk_count=1,
            embedder=embedder,
            chunks=(_chunk("synthetic_001", "合成公開資料"),),
            artifact_path=tmp_path / "artifact.jsonl",
            repository_root=repository_root,
            rag_mode="staging",
            production_enabled=False,
        )

    assert embedder.calls == 0

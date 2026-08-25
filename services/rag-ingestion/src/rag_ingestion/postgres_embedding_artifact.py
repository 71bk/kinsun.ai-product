"""Generate a signed-scope embedding artifact for the PostgreSQL RAG projection."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rag_ingestion.bedrock_embedder import _atomic_write_jsonl
from rag_ingestion.embedding_types import DocumentEmbeddingProvider, EmbeddingError
from rag_ingestion.settings import (
    GOOGLE_DOCUMENT_INPUT_TYPE,
    REQUIRED_EMBEDDING_DIMENSION,
    ensure_artifact_outside_repository,
)

EMBEDDING_ARTIFACT_SCHEMA_VERSION = "2.0.0"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EmbeddingArtifactChunk(Protocol):
    chunk_id: str
    embedding_text: str
    embedding_text_sha256: str


@dataclass(frozen=True, slots=True)
class AuthorizedEmbeddingArtifactResult:
    artifact_path: Path
    artifact_sha256: str
    allowlist_sha256: str
    provider: str
    model_id: str
    dimension: int
    document_task_type: str
    config_version: str
    success_count: int
    failure_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "status": "EMBEDDED",
            "artifact_location": "external_temp",
            "embedding_artifact_sha256": self.artifact_sha256,
            "allowlist_sha256": self.allowlist_sha256,
            "embedding_provider": self.provider,
            "embedding_model_id": self.model_id,
            "embedding_dimension": self.dimension,
            "document_task_type": self.document_task_type,
            "config_version": self.config_version,
            "embedding_success_count": self.success_count,
            "embedding_failure_count": self.failure_count,
            "external_access_performed": True,
            "database_write_performed": False,
            "retrieval_activation_status": "NOT_AUTHORIZED",
            "production_approved": False,
        }


def generate_authorized_postgres_embedding_artifact(
    *,
    authorization_status: str,
    authorized_allowlist_sha256: str,
    provider: str,
    model_id: str,
    dimension: int,
    document_task_type: str,
    config_version: str,
    expected_chunk_count: int,
    embedder: DocumentEmbeddingProvider,
    chunks: Sequence[EmbeddingArtifactChunk],
    artifact_path: Path,
    repository_root: Path,
    rag_mode: str,
    production_enabled: bool,
) -> AuthorizedEmbeddingArtifactResult:
    """Generate all vectors and atomically publish a profile-bound external artifact."""

    if authorization_status != "STAGING_EMBEDDING_AUTHORIZED":
        raise EmbeddingError("fixed-hash staging embedding authorization is required")
    if not _SHA256_PATTERN.fullmatch(authorized_allowlist_sha256):
        raise EmbeddingError("authorized allowlist SHA-256 is invalid")
    if rag_mode != "staging" or production_enabled:
        raise EmbeddingError("PostgreSQL document embedding is staging-only")
    if provider != "google":
        raise EmbeddingError("the PostgreSQL v002 profile must use the approved Google provider")
    if not model_id.strip() or embedder.model_id != model_id:
        raise EmbeddingError("embedding provider model does not match the bound profile")
    if dimension != REQUIRED_EMBEDDING_DIMENSION or embedder.dimension != dimension:
        raise EmbeddingError(f"embedding dimension must be {REQUIRED_EMBEDDING_DIMENSION}")
    if document_task_type != GOOGLE_DOCUMENT_INPUT_TYPE:
        raise EmbeddingError(f"document task type must be {GOOGLE_DOCUMENT_INPUT_TYPE}")
    if not config_version.strip():
        raise EmbeddingError("embedding config version is required")
    if len(chunks) != expected_chunk_count or expected_chunk_count <= 0:
        raise EmbeddingError("authorized chunk count differs from the projection")

    safe_path = ensure_artifact_outside_repository(artifact_path, repository_root)
    result = embedder.embed_documents([chunk.embedding_text for chunk in chunks])
    if result.failure_count != 0 or result.success_count != expected_chunk_count:
        raise EmbeddingError("embedding provider did not return the complete authorized corpus")
    rows = [
        {
            "record_type": "manifest",
            "schema_version": EMBEDDING_ARTIFACT_SCHEMA_VERSION,
            "allowlist_sha256": authorized_allowlist_sha256,
            "embedding_provider": provider,
            "embedding_model_id": model_id,
            "embedding_dimension": dimension,
            "document_task_type": document_task_type,
            "config_version": config_version,
            "chunk_count": expected_chunk_count,
        },
        *[
            {
                "record_type": "embedding",
                "chunk_id": chunk.chunk_id,
                "embedding_text_sha256": chunk.embedding_text_sha256,
                "allowlist_sha256": authorized_allowlist_sha256,
                "embedding_model_id": model_id,
                "embedding_dimension": dimension,
                "embedding": list(vector),
            }
            for chunk, vector in zip(chunks, result.vectors, strict=True)
        ],
    ]
    _atomic_write_jsonl(safe_path, rows)
    artifact_sha256 = hashlib.sha256(safe_path.read_bytes()).hexdigest()
    return AuthorizedEmbeddingArtifactResult(
        artifact_path=safe_path,
        artifact_sha256=artifact_sha256,
        allowlist_sha256=authorized_allowlist_sha256,
        provider=provider,
        model_id=model_id,
        dimension=dimension,
        document_task_type=document_task_type,
        config_version=config_version,
        success_count=result.success_count,
        failure_count=result.failure_count,
    )

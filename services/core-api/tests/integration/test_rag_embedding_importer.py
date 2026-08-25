from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg
import pytest

from app.rag_embedding_importer import (
    EmbeddingImportError,
    EmbeddingProfileBinding,
    import_embeddings,
    load_embedding_import_batch,
    verify_embeddings,
)
from app.rag_projection_importer import ProjectionBatch, ProjectionChunk, import_projection

EXPECTED_PROFILE_ID = EmbeddingProfileBinding(
    provider="google",
    model_id="gemini-embedding-001",
    dimension=1024,
    document_task_type="RETRIEVAL_DOCUMENT",
    config_version="1.0.0",
).profile_id


def _sync_test_database_url() -> str:
    value = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test",
    )
    return value.replace("postgresql+asyncpg://", "postgresql://")


def _projection() -> ProjectionBatch:
    chunk = ProjectionChunk(
        chunk_id="integration_embedding_rag_v2_v001_0001",
        source_id="integration_embedding_source",
        chunk_index=1,
        artifact_version="v001",
        schema_version="2.1.0",
        document_title="整合測試長照指南",
        section_title="申請方式",
        content_type="service_guide",
        language="zh-Hant",
        locale="zh-TW",
        chunk_text="整合測試公開資料。",
        embedding_text="整合測試公開資料，供文件檢索。",
        text_sha256="2" * 64,
        embedding_text_sha256="3" * 64,
        record_sha256="4" * 64,
        source_version="integration-v1",
        review_status="needs_review",
        current_status="current",
        risk_level="low",
        production_approved=False,
        retrieval_eligible=True,
        stop_normal_rag=False,
        requires_human_review=True,
        requires_official_assessment=False,
        requires_professional_assessment=False,
        allowed_audiences=("elder",),
        allowed_purposes=("general_information",),
        citation={"title": "整合測試長照指南"},
        governance={"production_approved": False},
        provenance={"source_version": "integration-v1"},
        retrieval_policy={"retrieval_eligible": True},
    )
    return ProjectionBatch(
        release_id="integration-rag-embedding-v1",
        artifact_version="v001",
        candidate_sha256="1" * 64,
        source_count=1,
        chunk_count=1,
        review_status="needs_review",
        human_source_review="NOT_COMPLETED",
        production_approved=False,
        chunks=(chunk,),
    )


def _write_artifact(path: Path, *, vector_value: float) -> str:
    rows = [
        {
            "record_type": "manifest",
            "schema_version": "2.0.0",
            "allowlist_sha256": "5" * 64,
            "embedding_provider": "google",
            "embedding_model_id": "gemini-embedding-001",
            "embedding_dimension": 1024,
            "document_task_type": "RETRIEVAL_DOCUMENT",
            "config_version": "1.0.0",
            "chunk_count": 1,
        },
        {
            "record_type": "embedding",
            "chunk_id": "integration_embedding_rag_v2_v001_0001",
            "embedding_text_sha256": "3" * 64,
            "allowlist_sha256": "5" * 64,
            "embedding_model_id": "gemini-embedding-001",
            "embedding_dimension": 1024,
            "embedding": [vector_value] * 1024,
        },
    ]
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pgvector_embedding_import_is_atomic_idempotent_and_profile_bound(
    tmp_path: Path,
) -> None:
    projection = _projection()
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    artifact = tmp_path / "embeddings.jsonl"
    artifact_sha256 = _write_artifact(artifact, vector_value=0.125)
    batch = load_embedding_import_batch(
        artifact,
        repository_root=repository_root,
        projection=projection,
        expected_artifact_sha256=artifact_sha256,
        expected_allowlist_sha256="5" * 64,
        expected_profile_id=EXPECTED_PROFILE_ID,
    )

    with psycopg.connect(_sync_test_database_url()) as connection:
        try:
            import_projection(connection, projection)
            first = import_embeddings(connection, batch)
            second = import_embeddings(connection, batch)
            verified = verify_embeddings(connection, batch)

            assert first.inserted_embedding_count == 1
            assert first.existing_embedding_count == 0
            assert second.inserted_embedding_count == 0
            assert second.existing_embedding_count == 1
            assert verified["status"] == "VERIFIED"
            assert verified["stored_embedding_count"] == 1

            changed_artifact = tmp_path / "changed-embeddings.jsonl"
            changed_sha256 = _write_artifact(changed_artifact, vector_value=0.25)
            changed_batch = load_embedding_import_batch(
                changed_artifact,
                repository_root=repository_root,
                projection=projection,
                expected_artifact_sha256=changed_sha256,
                expected_allowlist_sha256="5" * 64,
                expected_profile_id=EXPECTED_PROFILE_ID,
            )
            with pytest.raises(EmbeddingImportError, match="vector mismatch"):
                import_embeddings(connection, changed_batch)

            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM rag_public.chunk_embedding WHERE release_id = %s",
                    (projection.release_id,),
                )
                assert cursor.fetchone()[0] == 1
                cursor.execute(
                    """
                    SELECT count(*) FROM rag_public.ingestion_run
                    WHERE release_id = %s AND operation = 'EMBED_DOCUMENTS'
                    """,
                    (projection.release_id,),
                )
                assert cursor.fetchone()[0] == 2
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM rag_public.ingestion_run WHERE release_id = %s",
                    (projection.release_id,),
                )
                cursor.execute(
                    "DELETE FROM rag_public.chunk_embedding WHERE release_id = %s",
                    (projection.release_id,),
                )
                cursor.execute(
                    "DELETE FROM rag_public.chunk_projection WHERE release_id = %s",
                    (projection.release_id,),
                )
                cursor.execute(
                    "DELETE FROM rag_public.rag_release WHERE release_id = %s",
                    (projection.release_id,),
                )
                cursor.execute(
                    "DELETE FROM rag_public.embedding_profile WHERE embedding_profile_id = %s",
                    (batch.profile.profile_id,),
                )

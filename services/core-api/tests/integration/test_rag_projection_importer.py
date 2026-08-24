from __future__ import annotations

import os

import psycopg

from app.rag_projection_importer import ProjectionBatch, ProjectionChunk, import_projection


def _sync_test_database_url() -> str:
    value = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://kinsun:kinsun_local_dev@localhost:5432/kinsun_test",
    )
    return value.replace("postgresql+asyncpg://", "postgresql://")


def _batch() -> ProjectionBatch:
    chunk = ProjectionChunk(
        chunk_id="integration_rag_v2_v001_0001",
        source_id="integration_source",
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
        text_sha256="b" * 64,
        embedding_text_sha256="c" * 64,
        record_sha256="d" * 64,
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
        release_id="integration-rag-v1",
        artifact_version="v001",
        candidate_sha256="a" * 64,
        source_count=1,
        chunk_count=1,
        review_status="needs_review",
        human_source_review="NOT_COMPLETED",
        production_approved=False,
        chunks=(chunk,),
    )


def test_postgres_projection_import_is_atomic_idempotent_and_vector_null() -> None:
    batch = _batch()
    with psycopg.connect(_sync_test_database_url()) as connection:
        try:
            first = import_projection(connection, batch)
            second = import_projection(connection, batch)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT count(*), count(search_vector), count(lexical_text)
                    FROM rag_public.chunk_projection
                    WHERE release_id = %s
                    """,
                    (batch.release_id,),
                )
                projection_counts = cursor.fetchone()
                cursor.execute(
                    "SELECT count(*) FROM rag_public.chunk_embedding WHERE release_id = %s",
                    (batch.release_id,),
                )
                embedding_count = cursor.fetchone()[0]

            assert first.inserted_chunk_count == 1
            assert first.existing_chunk_count == 0
            assert second.inserted_chunk_count == 0
            assert second.existing_chunk_count == 1
            assert projection_counts == (1, 1, 1)
            assert embedding_count == 0
        finally:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM rag_public.ingestion_run WHERE release_id = %s",
                    (batch.release_id,),
                )
                cursor.execute(
                    "DELETE FROM rag_public.chunk_projection WHERE release_id = %s",
                    (batch.release_id,),
                )
                cursor.execute(
                    "DELETE FROM rag_public.rag_release WHERE release_id = %s",
                    (batch.release_id,),
                )

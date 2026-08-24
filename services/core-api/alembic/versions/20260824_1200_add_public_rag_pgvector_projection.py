"""add public RAG PostgreSQL projection

Revision ID: e6f8a0b2c345
Revises: c5d7e9f1a234
Create Date: 2026-08-24 12:00:00+08:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e6f8a0b2c345"
down_revision: str | Sequence[str] | None = "c5d7e9f1a234"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RAG_SCHEMA = "rag_public"


def upgrade() -> None:
    # Keep shared extension objects outside application-owned schemas.  The
    # Core migrations temporarily change search_path, so relying on the
    # session's first schema would make a later schema downgrade remove the
    # extension types while leaving a misleading migration history.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    op.execute(f"CREATE SCHEMA {RAG_SCHEMA}")
    op.execute(f"REVOKE ALL ON SCHEMA {RAG_SCHEMA} FROM PUBLIC")

    op.execute(
        f"""
        CREATE TABLE {RAG_SCHEMA}.embedding_profile (
            embedding_profile_id VARCHAR(160) PRIMARY KEY,
            provider VARCHAR(64) NOT NULL,
            model_id VARCHAR(256) NOT NULL,
            dimension INTEGER NOT NULL,
            document_task_type VARCHAR(64) NOT NULL,
            config_version VARCHAR(80) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_rag_embedding_profile_provider
                CHECK (provider ~ '^[a-z][a-z0-9_-]{{1,63}}$'),
            CONSTRAINT ck_rag_embedding_profile_dimension
                CHECK (dimension = 1024),
            CONSTRAINT ck_rag_embedding_profile_document_task
                CHECK (document_task_type = 'RETRIEVAL_DOCUMENT'),
            CONSTRAINT uq_rag_embedding_profile_compatibility
                UNIQUE (provider, model_id, dimension, document_task_type, config_version)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE {RAG_SCHEMA}.rag_release (
            release_id VARCHAR(160) PRIMARY KEY,
            artifact_version VARCHAR(32) NOT NULL,
            candidate_sha256 CHAR(64) NOT NULL UNIQUE,
            source_count INTEGER NOT NULL CHECK (source_count > 0),
            chunk_count INTEGER NOT NULL CHECK (chunk_count > 0),
            release_status VARCHAR(32) NOT NULL,
            review_status VARCHAR(32) NOT NULL,
            human_source_review VARCHAR(32) NOT NULL,
            production_approved BOOLEAN NOT NULL DEFAULT false,
            embedding_profile_id VARCHAR(160)
                REFERENCES {RAG_SCHEMA}.embedding_profile(embedding_profile_id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_rag_release_candidate_sha256
                CHECK (candidate_sha256 ~ '^[0-9a-f]{{64}}$'),
            CONSTRAINT ck_rag_release_status
                CHECK (release_status IN (
                    'STAGING_CANDIDATE', 'APPROVED', 'SUPERSEDED', 'REVOKED'
                )),
            CONSTRAINT ck_rag_release_candidate_not_production
                CHECK (release_status <> 'STAGING_CANDIDATE' OR NOT production_approved),
            CONSTRAINT uq_rag_release_embedding_profile
                UNIQUE (release_id, embedding_profile_id)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE {RAG_SCHEMA}.chunk_projection (
            release_id VARCHAR(160) NOT NULL
                REFERENCES {RAG_SCHEMA}.rag_release(release_id) ON DELETE RESTRICT,
            chunk_id VARCHAR(240) NOT NULL,
            source_id VARCHAR(200) NOT NULL,
            chunk_index INTEGER NOT NULL CHECK (chunk_index > 0),
            artifact_version VARCHAR(32) NOT NULL,
            schema_version VARCHAR(32) NOT NULL,
            document_title VARCHAR(500) NOT NULL,
            section_title VARCHAR(500),
            content_type VARCHAR(120) NOT NULL,
            language VARCHAR(32) NOT NULL,
            locale VARCHAR(32) NOT NULL,
            chunk_text TEXT NOT NULL,
            embedding_text TEXT NOT NULL,
            text_sha256 CHAR(64) NOT NULL,
            embedding_text_sha256 CHAR(64) NOT NULL,
            record_sha256 CHAR(64) NOT NULL,
            source_version VARCHAR(160),
            review_status VARCHAR(32) NOT NULL,
            current_status VARCHAR(32) NOT NULL,
            risk_level VARCHAR(32),
            production_approved BOOLEAN NOT NULL DEFAULT false,
            retrieval_eligible BOOLEAN NOT NULL DEFAULT false,
            stop_normal_rag BOOLEAN,
            requires_human_review BOOLEAN NOT NULL DEFAULT true,
            requires_official_assessment BOOLEAN,
            requires_professional_assessment BOOLEAN,
            allowed_audiences TEXT[] NOT NULL DEFAULT '{{}}',
            allowed_purposes TEXT[] NOT NULL DEFAULT '{{}}',
            citation JSONB NOT NULL,
            governance JSONB NOT NULL,
            provenance JSONB NOT NULL,
            retrieval_policy JSONB NOT NULL,
            lexical_text TEXT GENERATED ALWAYS AS (
                lower(
                    document_title || ' ' || coalesce(section_title, '') || ' ' || chunk_text
                )
            ) STORED,
            search_vector TSVECTOR GENERATED ALWAYS AS (
                to_tsvector(
                    'simple'::regconfig,
                    document_title || ' ' || coalesce(section_title, '') || ' ' || chunk_text
                )
            ) STORED,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (release_id, chunk_id),
            CONSTRAINT uq_rag_chunk_source_index
                UNIQUE (release_id, source_id, chunk_index),
            CONSTRAINT ck_rag_chunk_text_sha256
                CHECK (text_sha256 ~ '^[0-9a-f]{{64}}$'),
            CONSTRAINT ck_rag_chunk_embedding_text_sha256
                CHECK (embedding_text_sha256 ~ '^[0-9a-f]{{64}}$'),
            CONSTRAINT ck_rag_chunk_record_sha256
                CHECK (record_sha256 ~ '^[0-9a-f]{{64}}$'),
            CONSTRAINT ck_rag_chunk_text_present
                CHECK (length(chunk_text) > 0 AND length(embedding_text) > 0),
            CONSTRAINT ck_rag_chunk_candidate_not_production
                CHECK (artifact_version <> 'v002' OR NOT production_approved)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE {RAG_SCHEMA}.chunk_embedding (
            release_id VARCHAR(160) NOT NULL,
            chunk_id VARCHAR(240) NOT NULL,
            embedding_profile_id VARCHAR(160) NOT NULL,
            embedding_text_sha256 CHAR(64) NOT NULL,
            embedding public.vector(1024) NOT NULL,
            embedded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (release_id, chunk_id),
            CONSTRAINT fk_rag_embedding_chunk
                FOREIGN KEY (release_id, chunk_id)
                REFERENCES {RAG_SCHEMA}.chunk_projection(release_id, chunk_id)
                ON DELETE CASCADE,
            CONSTRAINT fk_rag_embedding_release_profile
                FOREIGN KEY (release_id, embedding_profile_id)
                REFERENCES {RAG_SCHEMA}.rag_release(release_id, embedding_profile_id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_rag_embedding_text_sha256
                CHECK (embedding_text_sha256 ~ '^[0-9a-f]{{64}}$')
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE {RAG_SCHEMA}.ingestion_run (
            run_id UUID PRIMARY KEY,
            release_id VARCHAR(160) NOT NULL
                REFERENCES {RAG_SCHEMA}.rag_release(release_id) ON DELETE RESTRICT,
            operation VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL,
            candidate_sha256 CHAR(64) NOT NULL,
            expected_source_count INTEGER NOT NULL CHECK (expected_source_count > 0),
            expected_chunk_count INTEGER NOT NULL CHECK (expected_chunk_count > 0),
            processed_chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (processed_chunk_count >= 0),
            inserted_chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (inserted_chunk_count >= 0),
            existing_chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (existing_chunk_count >= 0),
            failure_count INTEGER NOT NULL DEFAULT 0 CHECK (failure_count >= 0),
            error_code VARCHAR(120),
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at TIMESTAMPTZ,
            CONSTRAINT ck_rag_ingestion_operation
                CHECK (operation IN ('PROJECT_CHUNKS', 'EMBED_DOCUMENTS')),
            CONSTRAINT ck_rag_ingestion_status
                CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED')),
            CONSTRAINT ck_rag_ingestion_candidate_sha256
                CHECK (candidate_sha256 ~ '^[0-9a-f]{{64}}$'),
            CONSTRAINT ck_rag_ingestion_complete_counts
                CHECK (
                    status <> 'COMPLETED'
                    OR (
                        failure_count = 0
                        AND processed_chunk_count = expected_chunk_count
                        AND inserted_chunk_count + existing_chunk_count = expected_chunk_count
                        AND completed_at IS NOT NULL
                    )
                )
        )
        """
    )

    op.execute(
        f"""
        CREATE INDEX ix_rag_chunk_source
            ON {RAG_SCHEMA}.chunk_projection (release_id, source_id, chunk_index)
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_rag_chunk_governance
            ON {RAG_SCHEMA}.chunk_projection (
                release_id,
                production_approved,
                review_status,
                current_status,
                risk_level,
                retrieval_eligible
            )
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_rag_chunk_scope
            ON {RAG_SCHEMA}.chunk_projection
            USING GIN (allowed_purposes, allowed_audiences)
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_rag_chunk_search_vector
            ON {RAG_SCHEMA}.chunk_projection USING GIN (search_vector)
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_rag_chunk_lexical_trgm
            ON {RAG_SCHEMA}.chunk_projection
            USING GIN (lexical_text public.gin_trgm_ops)
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_rag_chunk_embedding_hnsw
            ON {RAG_SCHEMA}.chunk_embedding
            USING hnsw (embedding public.vector_cosine_ops)
        """
    )
    op.execute(
        f"""
        CREATE INDEX ix_rag_ingestion_release_started
            ON {RAG_SCHEMA}.ingestion_run (release_id, started_at DESC)
        """
    )

    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {RAG_SCHEMA} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {RAG_SCHEMA} FROM PUBLIC")
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {RAG_SCHEMA} " "REVOKE ALL ON TABLES FROM PUBLIC"
    )
    op.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {RAG_SCHEMA} " "REVOKE ALL ON SEQUENCES FROM PUBLIC"
    )


def downgrade() -> None:
    op.execute(f"DROP SCHEMA IF EXISTS {RAG_SCHEMA} CASCADE")
    # Extensions are instance-level shared dependencies. Do not remove them on
    # downgrade because another schema or service may already use them.

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Protocol, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from agent_runtime.rag.models import (
    HybridSearchPlan,
    PostgresSearchSettings,
    QueryEmbeddingSettings,
)
from agent_runtime.rag.search_backend import SearchHit

POSTGRES_CANDIDATE_LIMIT = 50

# This is the only executable PostgreSQL search template. The provider-neutral
# plan contributes bounded values only; it can never add SQL, identifiers, or
# operators. Release/profile integrity and governance are checked before either
# retrieval leg can see a row.
POSTGRES_HYBRID_SEARCH_SQL = """
WITH query_input AS (
    SELECT
        plainto_tsquery('simple'::regconfig, CAST(:query AS text)) AS ts_query,
        lower(CAST(:query AS text)) AS lexical_query,
        CAST(:query_vector AS public.vector) AS query_vector
),
release_scope AS (
    SELECT release.release_id
    FROM rag_public.rag_release AS release
    JOIN rag_public.embedding_profile AS profile
      ON profile.embedding_profile_id = release.embedding_profile_id
    WHERE release.release_id = CAST(:release_id AS text)
      AND release.embedding_profile_id = CAST(:embedding_profile_id AS text)
      AND profile.provider = CAST(:embedding_provider AS text)
      AND profile.model_id = CAST(:embedding_model_id AS text)
      AND profile.dimension = CAST(:embedding_dimension AS integer)
      AND profile.document_task_type = 'RETRIEVAL_DOCUMENT'
      AND release.release_status IN ('STAGING_CANDIDATE', 'APPROVED')
      AND (
          (release.review_status = 'verified' AND release.production_approved IS TRUE)
          OR (
              CAST(:allow_needs_review AS boolean) IS TRUE
              AND release.review_status IN ('needs_review', 'verified')
              AND release.production_approved IS FALSE
          )
      )
      AND release.chunk_count = (
          SELECT count(*)
          FROM rag_public.chunk_projection AS counted_projection
          WHERE counted_projection.release_id = release.release_id
      )
      AND release.chunk_count = (
          SELECT count(*)
          FROM rag_public.chunk_embedding AS counted_embedding
          WHERE counted_embedding.release_id = release.release_id
            AND counted_embedding.embedding_profile_id = release.embedding_profile_id
      )
      AND EXISTS (
          SELECT 1
          FROM rag_public.ingestion_run AS projection_run
          WHERE projection_run.release_id = release.release_id
            AND projection_run.operation = 'PROJECT_CHUNKS'
            AND projection_run.status = 'COMPLETED'
            AND projection_run.candidate_sha256 = release.candidate_sha256
            AND projection_run.failure_count = 0
      )
      AND EXISTS (
          SELECT 1
          FROM rag_public.ingestion_run AS embedding_run
          WHERE embedding_run.release_id = release.release_id
            AND embedding_run.operation = 'EMBED_DOCUMENTS'
            AND embedding_run.status = 'COMPLETED'
            AND embedding_run.candidate_sha256 = release.candidate_sha256
            AND embedding_run.failure_count = 0
      )
),
eligible AS (
    SELECT projection.*, embedding.embedding
    FROM release_scope
    JOIN rag_public.chunk_projection AS projection USING (release_id)
    JOIN rag_public.chunk_embedding AS embedding
      ON embedding.release_id = projection.release_id
     AND embedding.chunk_id = projection.chunk_id
     AND embedding.embedding_profile_id = CAST(:embedding_profile_id AS text)
     AND embedding.embedding_text_sha256 = projection.embedding_text_sha256
    WHERE projection.current_status = 'current'
      AND projection.stop_normal_rag IS FALSE
      AND projection.retrieval_eligible IS TRUE
      AND jsonb_typeof(
          projection.retrieval_policy -> 'retrieval_block_reasons'
      ) = 'array'
      AND jsonb_array_length(
          projection.retrieval_policy -> 'retrieval_block_reasons'
      ) = 0
      AND (
          (
              projection.review_status = 'verified'
              AND projection.production_approved IS TRUE
          )
          OR (
              CAST(:allow_needs_review AS boolean) IS TRUE
              AND projection.review_status IN ('needs_review', 'verified')
              AND projection.production_approved IS FALSE
          )
      )
      AND (
        (
            CAST(:policy_overlay_enabled AS boolean) IS TRUE
            AND cardinality(CAST(:policy_candidate_chunk_ids AS text[])) = 554
            AND projection.chunk_id = ANY(CAST(:policy_candidate_chunk_ids AS text[]))
        )
        OR (
              CAST(:policy_overlay_enabled AS boolean) IS FALSE
              AND projection.governance ->> 'data_classification' = 'public'
              AND projection.governance ->> 'distribution_scope' = 'public_knowledge'
              AND projection.provenance ->> 'is_official_source' = 'true'
              AND projection.risk_level IN ('low', 'medium')
              AND projection.requires_official_assessment IS NOT NULL
              AND projection.requires_professional_assessment IS NOT NULL
              AND CAST(:audience AS text) IS NOT NULL
              AND cardinality(projection.allowed_audiences) > 0
              AND (
                  CAST(:allow_all_audiences AS boolean) IS TRUE
                  OR CAST(:audience AS text) = ANY(projection.allowed_audiences)
              )
              AND CAST(:purpose AS text) IS NOT NULL
              AND CAST(:purpose AS text) = ANY(projection.allowed_purposes)
        )
    )
),
lexical_raw AS (
    SELECT
        eligible.chunk_id,
        CASE
            WHEN query_input.lexical_query LIKE
                '%' || lower(eligible.document_title) || '%'
                THEN 1.0
            ELSE 0.0
        END
        + greatest(
              ts_rank_cd(eligible.search_vector, query_input.ts_query, 32),
              public.word_similarity(query_input.lexical_query, eligible.lexical_text)
          ) AS raw_score
    FROM eligible
    CROSS JOIN query_input
    WHERE eligible.search_vector @@ query_input.ts_query
       OR public.word_similarity(query_input.lexical_query, eligible.lexical_text) > 0
    ORDER BY raw_score DESC, eligible.chunk_id
    LIMIT CAST(:candidate_limit AS integer)
),
lexical_normalized AS (
    SELECT
        chunk_id,
        raw_score,
        CASE
            WHEN max(raw_score) OVER () > min(raw_score) OVER ()
                THEN (raw_score - min(raw_score) OVER ())
                    / (max(raw_score) OVER () - min(raw_score) OVER ())
            WHEN raw_score > 0 THEN 1.0
            ELSE 0.0
        END AS normalized_score
    FROM lexical_raw
),
vector_raw AS (
    SELECT
        eligible.chunk_id,
        greatest(
            0.0,
            least(1.0, 1.0 - (eligible.embedding <=> query_input.query_vector))
        ) AS raw_score
    FROM eligible
    CROSS JOIN query_input
    ORDER BY eligible.embedding <=> query_input.query_vector, eligible.chunk_id
    LIMIT CAST(:candidate_limit AS integer)
),
vector_normalized AS (
    SELECT
        chunk_id,
        raw_score,
        CASE
            WHEN max(raw_score) OVER () > min(raw_score) OVER ()
                THEN (raw_score - min(raw_score) OVER ())
                    / (max(raw_score) OVER () - min(raw_score) OVER ())
            WHEN raw_score > 0 THEN 1.0
            ELSE 0.0
        END AS normalized_score
    FROM vector_raw
),
fused AS (
    SELECT
        coalesce(lexical.chunk_id, vector.chunk_id) AS chunk_id,
        coalesce(lexical.raw_score, 0.0) AS raw_lexical_score,
        coalesce(vector.raw_score, 0.0) AS raw_vector_score,
        CAST(:bm25_weight AS double precision)
            * coalesce(lexical.normalized_score, 0.0)
            + CAST(:vector_weight AS double precision)
            * coalesce(vector.normalized_score, 0.0) AS score
    FROM lexical_normalized AS lexical
    FULL OUTER JOIN vector_normalized AS vector USING (chunk_id)
),
ranked AS (
    SELECT chunk_id, score, raw_lexical_score, raw_vector_score
    FROM fused
    WHERE score >= CAST(:min_score AS double precision)
       OR raw_lexical_score >= CAST(:min_score AS double precision)
       OR raw_vector_score >= CAST(:min_score AS double precision)
    ORDER BY score DESC, chunk_id
    LIMIT CAST(:top_k AS integer)
)
SELECT
    ranked.score,
    ranked.raw_lexical_score,
    ranked.raw_vector_score,
    eligible.chunk_id,
    eligible.source_id,
    eligible.chunk_text AS text,
    eligible.document_title AS document_name,
    eligible.citation ->> 'section' AS section,
    coalesce(
        (eligible.citation ->> 'printed_page_start')::integer,
        (eligible.citation ->> 'physical_page_start')::integer
    ) AS page_start,
    coalesce(
        (eligible.citation ->> 'printed_page_end')::integer,
        (eligible.citation ->> 'physical_page_end')::integer
    ) AS page_end,
    coalesce(
        eligible.citation ->> 'official_source_page_url',
        eligible.citation ->> 'direct_official_source_url',
        eligible.citation ->> 'source_page_url',
        eligible.citation ->> 'direct_source_url'
    ) AS source_url,
    eligible.current_status,
    eligible.stop_normal_rag,
    eligible.risk_level,
    eligible.requires_official_assessment,
    eligible.requires_professional_assessment,
    eligible.allowed_audiences,
    eligible.allowed_purposes,
    eligible.retrieval_eligible,
    ARRAY(
        SELECT jsonb_array_elements_text(
            eligible.retrieval_policy -> 'retrieval_block_reasons'
        )
    ) AS retrieval_block_reasons,
    eligible.artifact_version,
    eligible.document_title AS title,
    eligible.citation ->> 'publisher' AS publisher,
    (eligible.citation ->> 'physical_page_start')::integer AS physical_page_start,
    (eligible.citation ->> 'physical_page_end')::integer AS physical_page_end,
    (eligible.citation ->> 'printed_page_start')::integer AS printed_page_start,
    (eligible.citation ->> 'printed_page_end')::integer AS printed_page_end,
    eligible.citation ->> 'source_locator' AS source_locator,
    eligible.citation ->> 'direct_official_source_url' AS direct_official_source_url,
    eligible.citation ->> 'official_source_page_url' AS official_source_page_url,
    eligible.citation ->> 'direct_source_url' AS direct_source_url,
    eligible.citation ->> 'source_page_url' AS source_page_url,
    TRUE AS is_official_source,
    eligible.provenance ->> 'source_version' AS source_version,
    eligible.provenance ->> 'source_version_date' AS source_version_date,
    eligible.provenance ->> 'version_published_at' AS version_published_at,
    eligible.provenance ->> 'source_page_updated_at' AS source_page_updated_at,
    eligible.provenance ->> 'published_at' AS published_at,
    eligible.provenance ->> 'last_verified_at' AS last_verified_at,
    eligible.review_status,
    eligible.production_approved
FROM ranked
JOIN eligible USING (chunk_id)
ORDER BY ranked.score DESC, eligible.chunk_id
"""


class PostgresSearchBackendError(RuntimeError):
    """PostgreSQL did not return a complete governed search response."""


class _MappingResult(Protocol):
    def all(self) -> list[Mapping[str, object]]: ...


class _ExecuteResult(Protocol):
    def mappings(self) -> _MappingResult: ...


class PostgresSearchBackend:
    """Read-only PostgreSQL/pgvector implementation of ``SearchBackend``."""

    def __init__(
        self,
        engine: AsyncEngine,
        settings: PostgresSearchSettings,
        embedding_settings: QueryEmbeddingSettings,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._embedding_settings = embedding_settings

    async def search(self, plan: HybridSearchPlan) -> list[SearchHit]:
        query_vector = _vector_literal(plan.query_vector, self._embedding_settings.dimension)
        parameters: dict[str, object] = {
            "query": plan.query,
            "query_vector": query_vector,
            "release_id": self._settings.release_id,
            "embedding_profile_id": self._settings.embedding_profile_id,
            "embedding_provider": self._embedding_settings.provider,
            "embedding_model_id": self._embedding_settings.model_id,
            "embedding_dimension": self._embedding_settings.dimension,
            "allow_needs_review": plan.allow_needs_review,
            "allow_all_audiences": plan.allow_all_audiences,
            "policy_overlay_enabled": plan.policy_candidate_chunk_ids is not None,
            "policy_candidate_chunk_ids": list(plan.policy_candidate_chunk_ids or ()),
            "audience": plan.audience,
            "purpose": plan.purpose,
            "candidate_limit": POSTGRES_CANDIDATE_LIMIT,
            "top_k": plan.search_result_limit,
            "min_score": plan.min_score,
            "bm25_weight": plan.bm25_weight,
            "vector_weight": plan.vector_weight,
        }
        try:
            async with self._engine.connect() as connection:
                result = cast(
                    _ExecuteResult,
                    await connection.execute(text(POSTGRES_HYBRID_SEARCH_SQL), parameters),
                )
                rows = result.mappings().all()
        except Exception as exc:
            # Driver messages may include endpoints or query text. Keep them behind
            # the adapter boundary; Retriever returns a fixed public fallback.
            raise PostgresSearchBackendError(
                f"PostgreSQL search failed: {type(exc).__name__}"
            ) from exc
        return _to_search_hits(rows)

    async def aclose(self) -> None:
        await self._engine.dispose()


def build_postgres_engine(settings: PostgresSearchSettings) -> AsyncEngine:
    """Create a bounded read-only pool without connecting during app import."""

    database_url = settings.database_url.get_secret_value()
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return create_async_engine(
        database_url,
        pool_size=settings.pool_min_size,
        max_overflow=settings.pool_max_size - settings.pool_min_size,
        pool_pre_ping=True,
        pool_timeout=max(1.0, settings.statement_timeout_ms / 1000),
        connect_args={
            "server_settings": {
                "application_name": "kinsun-agent-runtime-rag",
                "default_transaction_read_only": "on",
                "statement_timeout": str(settings.statement_timeout_ms),
            }
        },
    )


def build_postgres_search_backend(
    settings: PostgresSearchSettings,
    embedding_settings: QueryEmbeddingSettings,
) -> PostgresSearchBackend:
    return PostgresSearchBackend(
        build_postgres_engine(settings),
        settings,
        embedding_settings,
    )


def _vector_literal(vector: list[float], expected_dimension: int) -> str:
    if len(vector) != expected_dimension:
        raise PostgresSearchBackendError("query embedding dimension mismatch")
    if any(not math.isfinite(value) for value in vector):
        raise PostgresSearchBackendError("query embedding contains a non-finite value")
    return "[" + ",".join(format(value, ".17g") for value in vector) + "]"


def _to_search_hits(rows: list[Mapping[str, object]]) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for row in rows:
        score = row.get("score")
        if isinstance(score, bool) or not isinstance(score, int | float):
            raise PostgresSearchBackendError("PostgreSQL search returned a malformed score")
        if not math.isfinite(float(score)):
            raise PostgresSearchBackendError("PostgreSQL search returned a non-finite score")
        raw_vector_score = row.get("raw_vector_score")
        if raw_vector_score is not None and (
            isinstance(raw_vector_score, bool)
            or not isinstance(raw_vector_score, int | float)
            or not math.isfinite(float(raw_vector_score))
        ):
            raise PostgresSearchBackendError(
                "PostgreSQL search returned a malformed raw vector score"
            )
        raw_lexical_score = row.get("raw_lexical_score")
        if raw_lexical_score is not None and (
            isinstance(raw_lexical_score, bool)
            or not isinstance(raw_lexical_score, int | float)
            or not math.isfinite(float(raw_lexical_score))
        ):
            raise PostgresSearchBackendError(
                "PostgreSQL search returned a malformed raw lexical score"
            )
        source = dict(row)
        source.pop("score", None)
        source.pop("raw_vector_score", None)
        source.pop("raw_lexical_score", None)
        hits.append(
            SearchHit(
                score=float(score),
                source=source,
                raw_vector_score=(
                    float(raw_vector_score) if raw_vector_score is not None else None
                ),
                raw_lexical_score=(
                    float(raw_lexical_score) if raw_lexical_score is not None else None
                ),
            )
        )
    return hits

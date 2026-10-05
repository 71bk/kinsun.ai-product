"""Read-only export of complete, profile-bound document embedding cache evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping

from psycopg.rows import dict_row

from app.rag_embedding_importer import EmbeddingProfileBinding


class KnowledgeCacheError(ValueError):
    """Errors contain fixed codes only, never database or source payloads."""


def _require(condition, code):
    if not condition:
        raise KnowledgeCacheError(code)


def validate_cache_snapshot(release, projections, embeddings, receipts, registry):
    _require(registry.get("schema_version") == "knowledge-embedding-profiles-v1", "REGISTRY_SCHEMA")
    _require(
        isinstance(release.get("candidate_sha256"), str)
        and re.fullmatch(r"[a-f0-9]{64}", release["candidate_sha256"]) is not None,
        "CANDIDATE_HASH",
    )
    profile_id = release["embedding_profile_id"]
    profiles = registry.get("profiles", [])
    matches = [p for p in profiles if p.get("profile_id") == profile_id]
    _require(len(matches) == 1, "REGISTRY_PROFILE")
    profile = matches[0]
    _require(
        set(profile)
        == {
            "profile_id",
            "provider",
            "model_id",
            "model_version",
            "document_task_type",
            "dimension",
            "config_version",
        },
        "PROFILE_SHAPE",
    )
    keys = ("provider", "model_id", "dimension", "document_task_type", "config_version")
    _require(all(profile.get(k) == release.get(k) for k in keys), "PROFILE_DRIFT")
    _require(profile.get("model_version") == release["model_id"], "MODEL_VERSION_UNAVAILABLE")
    binding = EmbeddingProfileBinding(**{k: release[k] for k in keys})
    _require(binding.profile_id == profile_id, "PROFILE_ID_MISMATCH")
    _require(release["release_status"] == "STAGING_CANDIDATE", "RELEASE_STATUS")
    _require(release["production_approved"] is False, "PRODUCTION_NOT_ALLOWED")
    count = release["chunk_count"]
    _require(type(count) is int and count > 0, "RELEASE_COUNT")
    _require(len(projections) == len(embeddings) == count, "INCOMPLETE_COVERAGE")
    projected = {p["chunk_id"]: p for p in projections}
    vectors = {e["chunk_id"]: e for e in embeddings}
    _require(
        len(projected) == len(vectors) == count and projected.keys() == vectors.keys(),
        "DUPLICATE_OR_MISSING_IDS",
    )
    _require(len({p["source_id"] for p in projections}) == release["source_count"], "SOURCE_COUNT")
    for operation in ("PROJECT_CHUNKS", "EMBED_DOCUMENTS"):
        _require(
            any(
                r["operation"] == operation
                and r["status"] == "COMPLETED"
                and r["candidate_sha256"] == release["candidate_sha256"]
                and r["failure_count"] == 0
                and r["expected_source_count"] == release["source_count"]
                and r["expected_chunk_count"] == r["processed_chunk_count"] == count
                and r["inserted_chunk_count"] + r["existing_chunk_count"] == count
                for r in receipts
            ),
            "INCOMPLETE_RECEIPT",
        )
    entries = []
    for cid in sorted(projected):
        row, embedding = projected[cid], vectors[cid]
        text = row["embedding_text"]
        _require(isinstance(text, str) and bool(text.strip()), "INVALID_TEXT")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        _require(
            digest == row["embedding_text_sha256"] == embedding["embedding_text_sha256"],
            "TEXT_HASH_DRIFT",
        )
        _require(embedding["embedding_profile_id"] == profile_id, "VECTOR_PROFILE_DRIFT")
        vector = embedding["embedding"]
        if isinstance(vector, str):
            try:
                vector = json.loads(vector)
            except ValueError as exc:
                raise KnowledgeCacheError("INVALID_VECTOR") from exc
        _require(
            isinstance(vector, list) and len(vector) == profile["dimension"], "VECTOR_DIMENSION"
        )
        _require(
            all(type(v) in (int, float) and math.isfinite(v) for v in vector), "INVALID_VECTOR"
        )
        _require(any(v != 0 for v in vector), "ZERO_VECTOR")
        entries.append(
            {
                "embedding_text": text,
                "embedding_text_sha256": digest,
                "profile_id": profile_id,
                "vector": vector,
            }
        )
    return {
        "schema_version": "knowledge-embedding-cache-v1",
        "profiles": [dict(profile)],
        "entries": entries,
    }


def export_knowledge_cache(connection, *, release_id: str, registry: Mapping):
    """Take all evidence from one repeatable-read, read-only database snapshot."""
    with connection.transaction():
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '15000ms'")
            cursor.execute(
                """SELECT release.*, profile.provider, profile.model_id,
                profile.dimension, profile.document_task_type, profile.config_version
                FROM rag_public.rag_release AS release JOIN rag_public.embedding_profile AS profile
                ON profile.embedding_profile_id = release.embedding_profile_id
                WHERE release.release_id = %s""",
                (release_id,),
            )
            release = cursor.fetchone()
            _require(release is not None, "RELEASE_NOT_FOUND")
            cursor.execute(
                """SELECT chunk_id, source_id, embedding_text, embedding_text_sha256
                FROM rag_public.chunk_projection WHERE release_id = %s ORDER BY chunk_id""",
                (release_id,),
            )
            projections = cursor.fetchall()
            cursor.execute(
                """SELECT chunk_id, embedding_profile_id, embedding_text_sha256,
                embedding::text AS embedding FROM rag_public.chunk_embedding
                WHERE release_id = %s ORDER BY chunk_id""",
                (release_id,),
            )
            embeddings = cursor.fetchall()
            cursor.execute(
                """SELECT operation, status, candidate_sha256, failure_count,
                expected_source_count, expected_chunk_count, processed_chunk_count,
                inserted_chunk_count, existing_chunk_count FROM rag_public.ingestion_run
                WHERE release_id = %s""",
                (release_id,),
            )
            cache = validate_cache_snapshot(
                release, projections, embeddings, cursor.fetchall(), registry
            )
    return cache

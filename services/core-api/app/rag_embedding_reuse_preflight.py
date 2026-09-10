"""Pure preflight for reusing attested embeddings; no connection or write API.

Callers must load both projections and the original external embedding artifact
with their existing hash-pinned loaders. Snapshot rows must come from one explicit
read-only, repeatable-read transaction. This function cannot attest how a caller
obtained rows, authorize a sync, or protect against changes after the snapshot.
An apply workflow must independently revalidate and lock the live source rows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from app.rag_embedding_importer import (
    EmbeddingImportBatch,
    EmbeddingImportError,
    _parse_database_vector,
    _validate_vector,
    _vector_fingerprint,
)
from app.rag_projection_importer import ProjectionBatch


class EmbeddingReusePreflightError(ValueError):
    """Sanitized failure; no source text, vector, connection, or credentials."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EmbeddingReusePreflightError(code)


def _index(rows: list[dict[str, Any]], expected: set[str]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        _require(isinstance(row, dict), "INVALID_SNAPSHOT_ROW")
        chunk_id = row.get("chunk_id")
        _require(isinstance(chunk_id, str), "INVALID_SNAPSHOT_ID")
        _require(chunk_id in expected and chunk_id not in result, "SNAPSHOT_ID_MISMATCH")
        result[chunk_id] = row
    _require(set(result) == expected, "INCOMPLETE_SNAPSHOT")
    return result


def validate_embedding_reuse_snapshot(
    *,
    source: ProjectionBatch,
    target: ProjectionBatch,
    original_embeddings: EmbeddingImportBatch,
    crosswalk: dict[str, str],
    projection_rows: list[dict[str, Any]],
    embedding_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare all supplied live metadata/vector bytes with immutable evidence.

    ``crosswalk`` maps source IDs to target IDs. Projection rows contain exactly
    ``release_id`` plus ProjectionChunk fields (SQL arrays may be lists).
    Embedding rows contain release_id, chunk_id, embedding_profile_id,
    embedding_text_sha256 and embedding (the PostgreSQL vector text).
    Success is snapshot equivalence, NOT external verification or sync approval.
    """
    try:
        return _validate(
            source, target, original_embeddings, crosswalk, projection_rows, embedding_rows
        )
    except EmbeddingReusePreflightError:
        raise
    except (TypeError, ValueError, KeyError, OverflowError, AttributeError) as exc:
        raise EmbeddingReusePreflightError("INVALID_REUSE_EVIDENCE") from exc


def _validate(source, target, original, crosswalk, projection_rows, embedding_rows):
    _require(
        source.production_approved is False
        and target.production_approved is False
        and original.production_approved is False,
        "PRODUCTION_NOT_ALLOWED",
    )
    _require(source.release_id != target.release_id, "SUCCESSOR_REQUIRED")
    for field in (
        "release_id",
        "artifact_version",
        "candidate_sha256",
        "source_count",
        "chunk_count",
        "review_status",
        "human_source_review",
    ):
        _require(
            _canonical(getattr(source, field)) == _canonical(getattr(original, field)),
            "ORIGINAL_ARTIFACT_BINDING_MISMATCH",
        )
    old = {row.chunk_id: row for row in source.chunks}
    new = {row.chunk_id: row for row in target.chunks}
    _require(
        len(old) == len(source.chunks) == source.chunk_count > 0
        and len(new) == len(target.chunks) == target.chunk_count == source.chunk_count,
        "PROJECTION_COUNT_MISMATCH",
    )
    _require(
        len({row.source_id for row in old.values()}) == source.source_count
        and len({row.source_id for row in new.values()}) == target.source_count
        and target.source_count == source.source_count,
        "SOURCE_COUNT_MISMATCH",
    )
    _require(
        set(crosswalk) == set(old) and set(crosswalk.values()) == set(new),
        "CROSSWALK_MISMATCH",
    )
    attested = {row.chunk_id: row for row in original.records}
    _require(
        len(attested) == len(original.records) and set(attested) == set(old),
        "ORIGINAL_VECTOR_COVERAGE_MISMATCH",
    )
    live_projection = _index(projection_rows, set(old))
    live_embeddings = _index(embedding_rows, set(old))
    evidence = []
    for old_id in sorted(old):
        prior = old[old_id]
        successor = new[crosswalk[old_id]]
        expected_row = {"release_id": source.release_id, **asdict(prior)}
        # Canonical JSON compares bool/null/numeric types strictly, unlike ==.
        _require(
            _canonical(live_projection[old_id]) == _canonical(expected_row),
            "LIVE_PROJECTION_DRIFT",
        )
        for field in (
            "source_id",
            "chunk_index",
            "chunk_text",
            "embedding_text",
            "text_sha256",
            "embedding_text_sha256",
        ):
            _require(
                _canonical(getattr(prior, field)) == _canonical(getattr(successor, field)),
                "SUCCESSOR_CONTENT_CHANGED",
            )
        for text_field, hash_field in (
            ("chunk_text", "text_sha256"),
            ("embedding_text", "embedding_text_sha256"),
        ):
            _require(
                hashlib.sha256(getattr(prior, text_field).encode("utf-8")).hexdigest()
                == getattr(prior, hash_field),
                "SOURCE_TEXT_HASH_MISMATCH",
            )
        vector_row = live_embeddings[old_id]
        _require(
            set(vector_row)
            == {
                "release_id",
                "chunk_id",
                "embedding_profile_id",
                "embedding_text_sha256",
                "embedding",
            },
            "INVALID_VECTOR_ROW_SHAPE",
        )
        _require(
            vector_row["release_id"] == source.release_id
            and vector_row["embedding_profile_id"] == original.profile.profile_id
            and vector_row["embedding_text_sha256"] == prior.embedding_text_sha256
            and attested[old_id].embedding_text_sha256 == prior.embedding_text_sha256,
            "LIVE_VECTOR_BINDING_MISMATCH",
        )
        try:
            expected_vector = _validate_vector(list(attested[old_id].vector), 1024)
            live_vector = _parse_database_vector(vector_row["embedding"], 1024)
        except EmbeddingImportError as exc:
            raise EmbeddingReusePreflightError("INVALID_VECTOR") from exc
        fingerprint = _vector_fingerprint(live_vector)
        _require(
            fingerprint
            == _vector_fingerprint(expected_vector)
            == attested[old_id].vector_fingerprint,
            "VECTOR_FINGERPRINT_MISMATCH",
        )
        evidence.append(
            {
                "prior_chunk_id": old_id,
                "chunk_id": successor.chunk_id,
                "prior_record_sha256": prior.record_sha256,
                "record_sha256": successor.record_sha256,
                "embedding_text_sha256": prior.embedding_text_sha256,
                "vector_fingerprint": fingerprint,
            }
        )
    return {
        "status": "SUPPLIED_SNAPSHOT_MATCHES_ATTESTED_INPUTS",
        "source_release_id": source.release_id,
        "target_release_id": target.release_id,
        "source_candidate_sha256": source.candidate_sha256,
        "target_candidate_sha256": target.candidate_sha256,
        "original_embedding_artifact_sha256": original.artifact_sha256,
        "embedding_profile_id": original.profile.profile_id,
        "source_count": source.source_count,
        "chunk_count": len(evidence),
        "row_evidence_sha256": hashlib.sha256(_canonical(evidence)).hexdigest(),
        "rows": evidence,
        "database_access_performed": False,
        "external_sync": "NOT_AUTHORIZED",
        "runtime_activation": "NOT_AUTHORIZED",
        "production_approved": False,
    }

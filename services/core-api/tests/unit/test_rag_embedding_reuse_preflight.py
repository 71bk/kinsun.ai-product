from __future__ import annotations

import copy
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from app.rag_embedding_importer import (
    EmbeddingImportBatch,
    EmbeddingProfileBinding,
    EmbeddingRecord,
    _vector_fingerprint,
)
from app.rag_embedding_reuse_preflight import (
    EmbeddingReusePreflightError,
    validate_embedding_reuse_snapshot,
)
from app.rag_projection_importer import load_projection_batch

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def projections():
    base = ROOT / "data/rag-v2/candidates"
    return (
        load_projection_batch(
            base / "v002", ROOT / "contracts/schemas/rag/rag-chunk-v2.1.schema.json"
        ),
        load_projection_batch(
            base / "v004", base / "v004/schemas/rag-law-repair-chunk-v004.schema.json"
        ),
    )


def inputs(source, target):
    profile = EmbeddingProfileBinding(
        "google", "gemini-embedding-001", 1024, "RETRIEVAL_DOCUMENT", "1.0.0"
    )
    # Synthetic vectors only: this fixture does not attest the real database.
    vector = (0.125,) * 1024
    original = EmbeddingImportBatch(
        release_id=source.release_id,
        artifact_version=source.artifact_version,
        candidate_sha256=source.candidate_sha256,
        allowlist_sha256="a" * 64,
        artifact_sha256="b" * 64,
        source_count=source.source_count,
        chunk_count=source.chunk_count,
        review_status=source.review_status,
        human_source_review=source.human_source_review,
        production_approved=False,
        profile=profile,
        records=tuple(
            EmbeddingRecord(
                row.chunk_id, row.embedding_text_sha256, vector, _vector_fingerprint(vector)
            )
            for row in source.chunks
        ),
    )
    return dict(
        source=source,
        target=target,
        original_embeddings=original,
        crosswalk={row.chunk_id: row.chunk_id.replace("_v002_", "_v004_") for row in source.chunks},
        projection_rows=[{"release_id": source.release_id, **asdict(row)} for row in source.chunks],
        embedding_rows=[
            dict(
                release_id=source.release_id,
                chunk_id=row.chunk_id,
                embedding_profile_id=profile.profile_id,
                embedding_text_sha256=row.embedding_text_sha256,
                embedding="[" + ",".join(["0.125"] * 1024) + "]",
            )
            for row in source.chunks
        ],
    )


@pytest.fixture
def sample(projections):
    source, target = projections
    law = "moj_long_term_care_services_act_20210609"

    def subset(batch):
        chunks = tuple(
            row
            for row in batch.chunks
            if row.source_id == law and row.chunk_id.endswith(("_0002", "_0048"))
        )
        return replace(batch, chunks=chunks, chunk_count=2, source_count=1)

    return inputs(subset(source), subset(target))


def test_complete_candidate_snapshot_and_synthetic_vectors(projections, monkeypatch):
    import socket

    def no_network(*args, **kwargs):
        raise AssertionError("No network permitted")

    monkeypatch.setattr(socket, "socket", no_network)
    result = validate_embedding_reuse_snapshot(**inputs(*projections))
    assert result["chunk_count"] == 726
    assert result["source_count"] == 17
    assert result["external_sync"] == result["runtime_activation"] == "NOT_AUTHORIZED"
    assert result["database_access_performed"] is False
    assert result["production_approved"] is False
    assert all("embedding" not in row for row in result["rows"])


def test_deterministic_independent_of_snapshot_order(sample):
    expected = validate_embedding_reuse_snapshot(**sample)
    sample["projection_rows"].reverse()
    sample["embedding_rows"].reverse()
    assert validate_embedding_reuse_snapshot(**sample) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("stop_normal_rag", True),
        ("current_status", "superseded"),
        ("review_status", "verified"),
        ("requires_professional_assessment", True),
        ("allowed_purposes", []),
        ("production_approved", 0),
        ("chunk_text", "private sentinel must not appear in errors"),
        ("record_sha256", "f" * 64),
        ("extra", None),
    ],
)
def test_full_projection_drift_rejected_even_with_old_record_hash(sample, field, value):
    sample["projection_rows"][0][field] = value
    with pytest.raises(EmbeddingReusePreflightError, match="^LIVE_PROJECTION_DRIFT$"):
        validate_embedding_reuse_snapshot(**sample)


def test_nested_blocker_drift_is_not_overridden(sample):
    sample["projection_rows"][0]["retrieval_policy"]["retrieval_block_reasons"].append("revoked")
    with pytest.raises(EmbeddingReusePreflightError, match="LIVE_PROJECTION_DRIFT"):
        validate_embedding_reuse_snapshot(**sample)


@pytest.mark.parametrize("collection", ["projection_rows", "embedding_rows"])
@pytest.mark.parametrize("mutation", ["missing", "duplicate", "unknown"])
def test_exact_snapshot_coverage(sample, collection, mutation):
    rows = sample[collection]
    if mutation == "missing":
        rows.pop()
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    else:
        rows[0]["chunk_id"] = "unknown"
    with pytest.raises(EmbeddingReusePreflightError):
        validate_embedding_reuse_snapshot(**sample)


@pytest.mark.parametrize(
    "field,value",
    [
        ("release_id", "other"),
        ("embedding_profile_id", "other"),
        ("embedding_text_sha256", "0" * 64),
        ("embedding", "[0.25," + ",".join(["0.125"] * 1023) + "]"),
        ("embedding", "[nan," + ",".join(["0.125"] * 1023) + "]"),
        ("embedding", "[1,2]"),
        ("extra", True),
    ],
)
def test_vector_drift_and_invalid_vectors(sample, field, value):
    sample["embedding_rows"][0][field] = value
    with pytest.raises(EmbeddingReusePreflightError):
        validate_embedding_reuse_snapshot(**sample)


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate_sha256", "0" * 64),
        ("release_id", "other"),
        ("source_count", 9),
        ("chunk_count", 1),
        ("production_approved", True),
    ],
)
def test_original_artifact_binding(sample, field, value):
    sample["original_embeddings"] = replace(sample["original_embeddings"], **{field: value})
    with pytest.raises(EmbeddingReusePreflightError):
        validate_embedding_reuse_snapshot(**sample)


def test_changed_successor_text_and_crosswalk_rejected(sample):
    rows = sample["target"].chunks
    sample["target"] = replace(
        sample["target"], chunks=(replace(rows[0], embedding_text="changed"), rows[1])
    )
    with pytest.raises(EmbeddingReusePreflightError, match="SUCCESSOR_CONTENT_CHANGED"):
        validate_embedding_reuse_snapshot(**sample)
    sample["target"] = replace(sample["target"], chunks=rows)
    keys = list(sample["crosswalk"])
    sample["crosswalk"][keys[1]] = sample["crosswalk"][keys[0]]
    with pytest.raises(EmbeddingReusePreflightError, match="CROSSWALK_MISMATCH"):
        validate_embedding_reuse_snapshot(**sample)


def test_original_fingerprint_is_verified_not_trusted(sample):
    original = sample["original_embeddings"]
    rows = original.records
    sample["original_embeddings"] = replace(
        original,
        records=(
            replace(rows[0], vector_fingerprint="0" * 64),
            rows[1],
        ),
    )
    with pytest.raises(EmbeddingReusePreflightError, match="VECTOR_FINGERPRINT_MISMATCH"):
        validate_embedding_reuse_snapshot(**sample)

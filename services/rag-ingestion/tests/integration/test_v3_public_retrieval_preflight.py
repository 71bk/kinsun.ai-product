from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.v3_public_retrieval_preflight import (
    V3PublicRetrievalPreflightError,
    build_v3_owner_public_use_acceptance,
    build_v3_preflight,
    validate_v3_owner_public_use_acceptance,
    validate_v3_preflight,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_committed_v3_owner_acceptance_is_valid() -> None:
    result = validate_v3_owner_public_use_acceptance(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["review_status"] == "needs_review"
    assert result["production_approved"] is False


def test_committed_v3_preflight_is_valid() -> None:
    result = validate_v3_preflight(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["prior_artifact_entry_count"] > 0
    assert result["inventory_entry_count"] >= result["prior_artifact_entry_count"]
    assert result["production_approved"] is False


def test_v3_formal_packages_refuse_overwrite() -> None:
    with pytest.raises(V3PublicRetrievalPreflightError, match="refuse to overwrite"):
        build_v3_owner_public_use_acceptance(
            REPOSITORY_ROOT,
            project_owner_id="IanHsu",
            signed_at="2026-08-26T00:00:00+08:00",
            authorization_statements=["synthetic overwrite test"],
        )

    with pytest.raises(V3PublicRetrievalPreflightError, match="refuse to overwrite"):
        build_v3_preflight(REPOSITORY_ROOT)

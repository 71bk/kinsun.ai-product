from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.v3_verified_candidate import (
    V3VerifiedCandidateError,
    build_owner_human_review_acceptance,
    build_verified_audit_preflight,
    build_verified_candidate,
    build_verified_preflight,
    validate_owner_human_review_acceptance,
    validate_verified_audit_preflight,
    validate_verified_build_preflight_snapshot,
    validate_verified_candidate,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_committed_owner_human_review_acceptance_is_valid() -> None:
    result = validate_owner_human_review_acceptance(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["review_status"] == "verified"


def test_committed_verified_build_preflight_snapshot_is_valid() -> None:
    result = validate_verified_build_preflight_snapshot(REPOSITORY_ROOT)

    assert result["status"] == "PASS_BUILD_SNAPSHOT"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["prior_artifact_entry_count"] > 0
    assert result["inventory_entry_count"] >= result["prior_artifact_entry_count"]
    assert result["production_approved"] is False


def test_committed_verified_audit_preflight_is_current() -> None:
    result = validate_verified_audit_preflight(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["candidate_artifact_entry_count"] > 0
    assert result["inventory_entry_count"] >= result["candidate_artifact_entry_count"]
    assert result["production_approved"] is False


def test_committed_verified_candidate_is_valid() -> None:
    result = validate_verified_candidate(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["verified_count"] == 726
    assert result["current_chunk_count"] == 725
    assert result["superseded_chunk_count"] == 1
    assert result["production_approved"] is False


def test_verified_formal_packages_refuse_overwrite() -> None:
    with pytest.raises(V3VerifiedCandidateError, match="refuse to overwrite"):
        build_owner_human_review_acceptance(
            REPOSITORY_ROOT,
            project_owner_id="IanHsu",
            signed_at="2026-08-26T12:00:00+08:00",
            authorization_statements=["synthetic overwrite test"],
        )
    with pytest.raises(V3VerifiedCandidateError, match="refuse to overwrite"):
        build_verified_preflight(REPOSITORY_ROOT)
    with pytest.raises(V3VerifiedCandidateError, match="refuse to overwrite"):
        build_verified_candidate(REPOSITORY_ROOT)
    with pytest.raises(V3VerifiedCandidateError, match="refuse to overwrite"):
        build_verified_audit_preflight(REPOSITORY_ROOT)

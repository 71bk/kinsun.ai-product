from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from rag_ingestion.v3_verified_candidate import (
    V3VerifiedCandidateError,
    build_owner_human_review_acceptance,
    build_verified_candidate,
    build_verified_preflight,
    validate_owner_human_review_acceptance,
    validate_verified_audit_snapshot,
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


def test_committed_verified_audit_snapshot_integrity() -> None:
    result = validate_verified_audit_snapshot(REPOSITORY_ROOT)

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


def test_candidate_validation_does_not_require_capture_time_code_bytes(monkeypatch) -> None:
    from rag_ingestion import v3_verified_candidate as candidate

    def fail_current_inputs(*args):
        raise AssertionError("historical code inputs must not gate candidate validation")

    monkeypatch.setattr(candidate, "_validation_input_entries", fail_current_inputs)
    assert candidate.validate_verified_candidate(REPOSITORY_ROOT)["verified_count"] == 726
    assert candidate.validate_verified_audit_snapshot(REPOSITORY_ROOT)["status"] == "PASS"


@pytest.mark.parametrize(
    "target", ["validation-input-inventory.json", "candidate-artifact-lock.json"]
)
def test_audit_snapshot_rejects_tampered_inventory_or_candidate_lock(tmp_path, target) -> None:
    from rag_ingestion import v3_verified_candidate as candidate

    package = tmp_path / "snapshot"
    shutil.copytree(REPOSITORY_ROOT / candidate.AUDIT_PREFLIGHT_PACKAGE, package)
    document_path = package / target
    document = json.loads(document_path.read_text(encoding="utf-8"))
    document["inventory_sha256"] = "0" * 64
    document_path.write_text(json.dumps(document) + "\n", encoding="utf-8", newline="\n")
    candidate._write_checksums(package)

    with pytest.raises(V3VerifiedCandidateError, match="immutable lock|snapshot inventory"):
        candidate.validate_verified_audit_snapshot(REPOSITORY_ROOT, package)

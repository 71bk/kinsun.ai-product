from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.source_family_policy_audit_v8 import (
    SourceFamilyPolicyAuditV8Error,
    build_source_family_policy_audit_v8,
    validate_source_family_policy_audit_v8,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_audit_v8_builder_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit-v008"
    summary = build_source_family_policy_audit_v8(REPOSITORY_ROOT, output_path=output)
    result = validate_source_family_policy_audit_v8(REPOSITORY_ROOT, output)

    assert summary.inventory_sha256 == result["inventory_sha256"]
    assert summary.prior_lock_sha256 == result["candidate_lock_sha256"]
    assert result["candidate_artifact_entry_count"] == 50
    assert result["inventory_entry_count"] == 74
    assert result["live_governance_validation"] == "ENFORCED"
    assert result["opensearch_transport_validation"] == "TLS_AND_CAPACITY_ENFORCED"
    with pytest.raises(SourceFamilyPolicyAuditV8Error, match="exists; refuse to overwrite"):
        build_source_family_policy_audit_v8(REPOSITORY_ROOT, output_path=output)


def test_committed_audit_v8_matches_current_runtime_governance() -> None:
    result = validate_source_family_policy_audit_v8(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["live_governance_validation"] == "ENFORCED"
    assert result["opensearch_transport_validation"] == "TLS_AND_CAPACITY_ENFORCED"
    assert result["external_sync"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False

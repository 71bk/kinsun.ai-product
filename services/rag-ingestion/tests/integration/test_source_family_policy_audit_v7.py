from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.source_family_policy_audit_v7 import (
    SourceFamilyPolicyAuditV7Error,
    build_source_family_policy_audit_v7,
    validate_source_family_policy_audit_v7,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_audit_v7_builder_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit-v007"
    summary = build_source_family_policy_audit_v7(REPOSITORY_ROOT, output_path=output)
    result = validate_source_family_policy_audit_v7(REPOSITORY_ROOT, output)

    assert summary.inventory_sha256 == result["inventory_sha256"]
    assert summary.prior_lock_sha256 == result["candidate_lock_sha256"]
    assert result["candidate_artifact_entry_count"] == 46
    assert result["inventory_entry_count"] == 67
    assert result["live_governance_validation"] == "ENFORCED"
    with pytest.raises(SourceFamilyPolicyAuditV7Error, match="exists; refuse to overwrite"):
        build_source_family_policy_audit_v7(REPOSITORY_ROOT, output_path=output)


def test_committed_audit_v7_remains_a_valid_frozen_predecessor() -> None:
    result = validate_source_family_policy_audit_v7(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["live_governance_validation"] == "ENFORCED"
    assert result["external_sync"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False

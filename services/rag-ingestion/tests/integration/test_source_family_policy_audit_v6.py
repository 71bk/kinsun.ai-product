from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.source_family_policy_audit_v6 import (
    SourceFamilyPolicyAuditV6Error,
    build_source_family_policy_audit_v6,
    validate_source_family_policy_audit_v6,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_audit_v6_builder_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit-v006"
    summary = build_source_family_policy_audit_v6(REPOSITORY_ROOT, output_path=output)
    result = validate_source_family_policy_audit_v6(REPOSITORY_ROOT, output)

    assert summary.inventory_sha256 == result["inventory_sha256"]
    assert summary.prior_lock_sha256 == result["candidate_lock_sha256"]
    assert result["candidate_artifact_entry_count"] == 42
    assert result["inventory_entry_count"] == 49
    assert result["purpose_verified_count"] == 32
    assert result["conditional_stop_count"] == 27
    assert result["conditional_stop_active_count"] == 0
    with pytest.raises(SourceFamilyPolicyAuditV6Error, match="exists; refuse to overwrite"):
        build_source_family_policy_audit_v6(REPOSITORY_ROOT, output_path=output)


def test_committed_audit_v6_is_valid() -> None:
    result = validate_source_family_policy_audit_v6(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["external_sync"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False

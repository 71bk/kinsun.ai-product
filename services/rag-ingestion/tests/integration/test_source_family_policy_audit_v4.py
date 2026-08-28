from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.source_family_policy_audit_v4 import (
    SourceFamilyPolicyAuditV4Error,
    build_source_family_policy_audit_v4,
    validate_source_family_policy_audit_v4,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_audit_v4_builder_is_deterministic_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "audit-v004"
    summary = build_source_family_policy_audit_v4(
        REPOSITORY_ROOT,
        output_path=output,
    )
    result = validate_source_family_policy_audit_v4(REPOSITORY_ROOT, output)

    assert summary.inventory_sha256 == result["inventory_sha256"]
    assert summary.prior_lock_sha256 == result["candidate_lock_sha256"]
    assert result["purpose_verified_count"] == 32
    assert result["conditional_stop_count"] == 27
    assert result["conditional_stop_active_count"] == 0
    with pytest.raises(SourceFamilyPolicyAuditV4Error, match="exists; refuse to overwrite"):
        build_source_family_policy_audit_v4(REPOSITORY_ROOT, output_path=output)


def test_committed_audit_v4_is_valid() -> None:
    with pytest.raises(SourceFamilyPolicyAuditV4Error, match="input mismatch"):
        validate_source_family_policy_audit_v4(REPOSITORY_ROOT)

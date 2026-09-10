from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.source_family_policy_audit_v9 import (
    SourceFamilyPolicyAuditV9Error,
    build_source_family_policy_audit_v9,
    validate_source_family_policy_audit_v9,
)

ROOT = Path(__file__).resolve().parents[4]


def test_audit_v9_build_validates_and_refuses_overwrite(tmp_path):
    destination = tmp_path / "audit-v009"
    summary = build_source_family_policy_audit_v9(ROOT, output_path=destination)
    result = validate_source_family_policy_audit_v9(ROOT, destination)
    assert result["status"] == "PASS"
    assert result["inventory_sha256"] == summary.inventory_sha256
    assert result["candidate_artifact_entry_count"] > 50
    assert result["inventory_entry_count"] > 74
    assert result["external_sync"] == "NOT_AUTHORIZED"
    assert result["production_approved"] is False
    with pytest.raises(SourceFamilyPolicyAuditV9Error, match="exists; refuse to overwrite"):
        build_source_family_policy_audit_v9(ROOT, output_path=destination)


def test_committed_audit_v9_matches_current_law_repair():
    assert validate_source_family_policy_audit_v9(ROOT)["status"] == "PASS"

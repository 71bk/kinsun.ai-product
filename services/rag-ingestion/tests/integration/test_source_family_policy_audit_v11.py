from pathlib import Path

import pytest

from rag_ingestion import source_family_policy_audit_v11 as audit
from rag_ingestion.source_family_policy_v2 import SourceFamilyPolicyV2Error

ROOT = Path(__file__).resolve().parents[4]


def test_current_v11_matches_runtime_and_quality_inputs():
    result = audit.validate(ROOT)
    assert result["status"] == "PASS"
    assert result["attestation_scope"] == "CURRENT_IMPLEMENTATION_BYTES"
    assert result["production_approved"] is False
    assert result["external_activation"] == "NOT_AUTHORIZED"


def test_builder_refuses_overwrite_and_validator_rejects_runtime_drift(tmp_path, monkeypatch):
    destination = tmp_path / "audit-v011"
    assert audit.build(ROOT, destination)["status"] == "PASS"
    with pytest.raises(SourceFamilyPolicyV2Error, match="refuse to overwrite"):
        audit.build(ROOT, destination)
    original = audit._file_entries

    def changed(root, paths, family):
        entries = original(root, paths, family)
        for entry in entries:
            if entry["path"].endswith("knowledge_router.py"):
                entry["sha256"] = "0" * 64
        return entries

    monkeypatch.setattr(audit, "_file_entries", changed)
    with pytest.raises(SourceFamilyPolicyV2Error, match="current inputs changed"):
        audit.validate(ROOT, destination)


def test_predecessor_byte_pin_is_enforced(monkeypatch):
    monkeypatch.setattr(audit, "PRIOR_SHA", "0" * 64)
    with pytest.raises(SourceFamilyPolicyV2Error, match="v010 bytes changed"):
        audit.documents(ROOT)

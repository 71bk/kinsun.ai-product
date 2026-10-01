from pathlib import Path

import pytest

from rag_ingestion import source_family_policy_audit_v13 as audit
from rag_ingestion.source_family_policy_v2 import SourceFamilyPolicyV2Error

ROOT = Path(__file__).resolve().parents[4]


def test_current_v13_binds_admission_evaluation_without_authorizing_activation():
    result = audit.validate(ROOT)
    assert result["status"] == "PASS"
    assert result["attestation_scope"] == "CURRENT_IMPLEMENTATION_BYTES"
    assert result["production_approved"] is False
    assert result["external_activation"] == "NOT_AUTHORIZED"


def test_builder_refuses_overwrite_and_validator_detects_evaluator_drift(tmp_path, monkeypatch):
    destination = tmp_path / "audit-v013"
    assert audit.build(ROOT, destination)["status"] == "PASS"
    with pytest.raises(SourceFamilyPolicyV2Error, match="refuse to overwrite"):
        audit.build(ROOT, destination)
    original = audit._file_entries

    def changed(root, paths, family):
        entries = original(root, paths, family)
        for entry in entries:
            if entry["path"].endswith("admission_quality.py"):
                entry["sha256"] = "0" * 64
        return entries

    monkeypatch.setattr(audit, "_file_entries", changed)
    assert audit.prior.validate(ROOT)["attestation_scope"] == "SEALED_HISTORICAL_INPUTS"
    with pytest.raises(SourceFamilyPolicyV2Error, match="current inputs changed"):
        audit.validate(ROOT, destination)


def test_predecessor_byte_pin_is_enforced(monkeypatch):
    monkeypatch.setattr(audit, "PRIOR_SHA", "0" * 64)
    with pytest.raises(SourceFamilyPolicyV2Error, match="v012 bytes changed"):
        audit.documents(ROOT)

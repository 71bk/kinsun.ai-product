from pathlib import Path

import pytest

from rag_ingestion.source_family_policy_audit_v10 import build, validate
from rag_ingestion.source_family_policy_v2 import SourceFamilyPolicyV2Error

ROOT = Path(__file__).resolve().parents[4]


def test_v10_build_validate_and_refuse_overwrite(tmp_path):
    output = tmp_path / "audit-v010"
    assert build(ROOT, output)["status"] == "PASS"
    assert validate(ROOT, output)["production_approved"] is False
    with pytest.raises(SourceFamilyPolicyV2Error, match="refuse to overwrite"):
        build(ROOT, output)


def test_committed_v10_matches_current_sync_inputs():
    assert validate(ROOT)["status"] == "PASS"

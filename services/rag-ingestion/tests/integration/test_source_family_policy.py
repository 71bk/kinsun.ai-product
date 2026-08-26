from __future__ import annotations

from pathlib import Path

import pytest

from rag_ingestion.source_family_policy import (
    SourceFamilyPolicyError,
    build_source_family_policy,
    prepare_source_family_policy_preflight,
    validate_source_family_policy,
    validate_source_family_policy_build_preflight_snapshot,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


def test_committed_source_family_policy_preflight_is_valid() -> None:
    result = validate_source_family_policy_build_preflight_snapshot(REPOSITORY_ROOT)

    assert result["status"] == "PASS_BUILD_SNAPSHOT"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["production_approved"] is False


def test_committed_source_family_policy_candidate_is_valid() -> None:
    result = validate_source_family_policy(REPOSITORY_ROOT)

    assert result["status"] == "PASS"
    assert result["source_count"] == 17
    assert result["chunk_count"] == 726
    assert result["production_approved"] is False


def test_high_unknown_and_research_routes_remain_blocked() -> None:
    package = REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/candidates/v001"
    import json

    policy = json.loads((package / "source-family-policy-map.json").read_text(encoding="utf-8"))
    summary = policy["summary"]
    assert (
        summary["risk_high_count"]
        + summary["risk_high_red_line_count"]
        + summary["risk_unclassified_count"]
        == 74
    )
    assert summary["official_raw_stop_normal_rag_true_count"] == 35
    assert summary["official_raw_non_current_count"] == 296
    assert summary["official_low_medium_stop_true_cohort_count"] == 27
    assert summary["official_low_medium_stop_false_non_current_cohort_count"] == 243
    for source in policy["source_policies"]:
        if not source["is_official_source"]:
            assert (
                source["policy_decision"]["ordinary_rag_source_status"]
                == "INDEPENDENT_RESEARCH_ROUTE_ONLY"
            )


def test_missing_license_evidence_never_enters_ordinary_rag() -> None:
    import json

    path = (
        REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/candidates/v001/"
        "source-family-policy-map.json"
    )
    policy = json.loads(path.read_text(encoding="utf-8"))
    for source in policy["source_policies"]:
        if not source["evidence"]["license_evidence_urls"]:
            assert (
                source["policy_decision"]["ordinary_rag_source_status"]
                != "CANDIDATE_WITH_CHUNK_GATES"
            )


def test_source_family_formal_outputs_refuse_overwrite() -> None:
    with pytest.raises(SourceFamilyPolicyError, match="refuse to overwrite"):
        prepare_source_family_policy_preflight(REPOSITORY_ROOT)
    with pytest.raises(SourceFamilyPolicyError, match="refuse to overwrite"):
        build_source_family_policy(REPOSITORY_ROOT)

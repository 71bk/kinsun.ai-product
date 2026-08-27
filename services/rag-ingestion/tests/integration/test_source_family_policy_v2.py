from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag_ingestion.source_family_policy_v2 import (
    RISK_DECISION_CHUNK_IDS,
    SourceFamilyPolicyV2Error,
    build_owner_source_family_policy_acceptance,
    build_source_family_policy_v2,
    build_source_family_policy_v2_audit_preflight,
    build_source_family_policy_v2_preflight,
    evaluate_ordinary_retrieval,
    validate_owner_source_family_policy_acceptance,
    validate_source_family_policy_v2,
    validate_source_family_policy_v2_audit_preflight,
    validate_source_family_policy_v2_build_preflight_snapshot,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
POLICY_ROOT = REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/candidates/v002"
POLICY_AUDIT_ROOT = (
    REPOSITORY_ROOT / "data/rag-v3/governance/source-family-policy/audits/v002/preflight"
)


def _policy() -> dict[str, object]:
    return json.loads((POLICY_ROOT / "source-family-policy-map.json").read_text(encoding="utf-8"))


def _records() -> dict[str, dict[str, object]]:
    result = {}
    root = REPOSITORY_ROOT / "data/rag-v3/candidates/v003/chunks"
    for path in root.glob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            result[record["identity"]["chunk_id"]] = record
    return result


def test_committed_policy_v2_packages_are_valid() -> None:
    acceptance = validate_owner_source_family_policy_acceptance(REPOSITORY_ROOT)
    preflight = validate_source_family_policy_v2_build_preflight_snapshot(REPOSITORY_ROOT)
    policy = validate_source_family_policy_v2(REPOSITORY_ROOT)
    audit = validate_source_family_policy_v2_audit_preflight(REPOSITORY_ROOT)

    assert acceptance["status"] == "PASS"
    assert preflight["status"] == "PASS_BUILD_SNAPSHOT"
    assert policy["status"] == "PASS"
    assert audit["status"] == "PASS"
    assert policy["ordinary_retrieval_chunk_candidate_count"] == 554
    assert policy["response_metadata_ready_count"] == 302
    assert policy["production_approved"] is False
    assert audit["candidate_artifact_entry_count"] == 19
    lock = json.loads((POLICY_AUDIT_ROOT / "candidate-artifact-lock.json").read_text("utf-8"))
    locked_paths = {entry["path"] for entry in lock["entries"]}
    assert {
        "data/rag-v3/governance/source-family-policy/audits/v001/preflight/README.md",
        "data/rag-v3/governance/source-family-policy/audits/v001/preflight/SHA256SUMS.txt",
        (
            "data/rag-v3/governance/source-family-policy/audits/v001/preflight/"
            "candidate-artifact-lock.json"
        ),
        (
            "data/rag-v3/governance/source-family-policy/audits/v001/preflight/"
            "validation-input-inventory.json"
        ),
    } <= locked_paths


def test_missing_license_url_is_not_an_automatic_source_block() -> None:
    policy = _policy()
    missing = [
        item for item in policy["source_policies"] if not item["evidence"]["license_evidence_urls"]
    ]

    assert len(missing) == 13
    assert all(
        item["project_use_authorization"]["status"] == "OWNER_REVIEWED_PUBLIC_USE"
        for item in missing
    )
    assert all(
        item["policy_decision"]["license_handling"]
        == "OWNER_PUBLIC_USE_REVIEW_MISSING_URL_NOT_AUTOMATIC_BLOCK"
        for item in missing
    )
    assert policy["summary"]["missing_license_url_blocked_source_count"] == 0


def test_five_owner_general_risk_decisions_map_to_low_overlay() -> None:
    policy = _policy()
    decisions = policy["chunk_risk_decisions"]
    records = _records()

    assert tuple(item["chunk_id"] for item in decisions) == RISK_DECISION_CHUNK_IDS
    assert all(item["prior_risk_level"] is None for item in decisions)
    assert all(item["effective_risk_level"] == "low" for item in decisions)
    assert all(
        records[item["chunk_id"]]["retrieval_policy"]["risk_level"] is None for item in decisions
    )
    assert policy["summary"]["risk_unclassified_effective_count"] == 0


def test_all_roles_can_search_official_candidates_but_response_gate_still_applies() -> None:
    policy = _policy()
    records = _records()
    source = next(
        item
        for item in policy["source_policies"]
        if item["source_id"] == "mohw_home_care_service_supervisor_manual_forms_appendix_20260529"
    )
    risk_decisions = {
        item["chunk_id"]: item["effective_risk_level"] for item in policy["chunk_risk_decisions"]
    }
    record = records[RISK_DECISION_CHUNK_IDS[0]]

    for role in ("elder", "family_caregiver", "care_professional", "system_admin"):
        result = evaluate_ordinary_retrieval(
            record,
            source,
            risk_decisions,
            actor_role=role,
            purpose="form_reference",
        )
        assert result["retrieval_allowed"] is True
        assert result["response_allowed"] is False
        assert "assessment_policy_incomplete" in result["response_block_reasons"]


def test_high_stop_noncurrent_and_research_chunks_fail_closed() -> None:
    policy = _policy()
    records = _records()
    policies = {item["source_id"]: item for item in policy["source_policies"]}
    risk_decisions = {
        item["chunk_id"]: item["effective_risk_level"] for item in policy["chunk_risk_decisions"]
    }
    probes = {
        "risk_level_not_allowed": next(
            row for row in records.values() if row["retrieval_policy"]["risk_level"] == "high"
        ),
        "stop_normal_rag": next(
            row
            for row in records.values()
            if row["retrieval_policy"]["risk_level"] in {"low", "medium"}
            and row["retrieval_policy"]["stop_normal_rag"] is True
        ),
        "current_status_not_current": next(
            row for row in records.values() if row["governance"]["current_status"] != "current"
        ),
        "independent_research_route_required": next(
            row for row in records.values() if row["provenance"]["is_official_source"] is False
        ),
    }

    for reason, record in probes.items():
        result = evaluate_ordinary_retrieval(
            record,
            policies[record["identity"]["source_id"]],
            risk_decisions,
            actor_role="elder",
            purpose="source_lookup",
        )
        assert result["retrieval_allowed"] is False
        assert reason in result["retrieval_block_reasons"]


def test_policy_v2_formal_outputs_refuse_overwrite() -> None:
    builders = (
        build_owner_source_family_policy_acceptance,
        build_source_family_policy_v2_preflight,
        build_source_family_policy_v2,
        build_source_family_policy_v2_audit_preflight,
    )
    for builder in builders:
        with pytest.raises(SourceFamilyPolicyV2Error, match="refuse to overwrite"):
            builder(REPOSITORY_ROOT)

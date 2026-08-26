"""Build and validate the governed RAG v003 source-family policy map."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from rag_ingestion.v3_public_retrieval_preflight import (
    validate_v3_owner_public_use_acceptance,
    validate_v3_preflight,
    validate_v3_preflight_build_snapshot,
)

HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"
CANONICAL_HASH_MODE = "sha256_canonical_json_v1"
SOURCE_MANIFEST_PATH = Path("data/rag-v2/candidates/v002/manifests/source-manifest-v002.json")
CHUNK_ROOT = Path("data/rag-v2/candidates/v002/chunks")
OWNER_ACCEPTANCE_PATH = Path("data/rag-v3/review/acceptance/v001/owner-public-use-acceptance.json")
V3_PREFLIGHT_ROOT = Path("data/rag-v3/preflight/v001")
POLICY_ROOT = Path("data/rag-v3/governance/source-family-policy")
AUDIT_PREFLIGHT_PATH = POLICY_ROOT / "preflight/v001"
POLICY_PACKAGE_PATH = POLICY_ROOT / "candidates/v001"
POLICY_SCHEMA_PATH = Path("contracts/schemas/rag/rag-source-family-policy-map-v1.schema.json")
AUDIT_INPUT_PATHS = (
    Path("config/rag/staging-filters.yaml"),
    Path("contracts/schemas/rag/rag-chunk-v2.1.schema.json"),
    Path("contracts/schemas/rag/rag-chunk-v3.schema.json"),
    POLICY_SCHEMA_PATH,
    SOURCE_MANIFEST_PATH,
    Path("data/rag-v2/candidates/v002/governance/enum-evidence-v002.json"),
    OWNER_ACCEPTANCE_PATH,
    Path("docs/project/rag-v3-public-retrieval-plan.md"),
    Path("scripts/rag/build_source_family_policy.py"),
    Path("scripts/rag/validate_source_family_policy.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_policy.py"),
    Path("services/rag-ingestion/tests/integration/test_source_family_policy.py"),
)
PRIOR_POLICY_INPUT_ROOTS = (
    Path("data/rag-v3/review/acceptance/v001"),
    V3_PREFLIGHT_ROOT,
)
OFFICIAL_PUBLIC_AUDIENCES = [
    "elder",
    "family_caregiver",
    "care_professional",
    "system_admin",
]
PROFESSIONAL_AUDIENCES = ["care_professional", "system_admin"]
PURPOSES_BY_SOURCE_TYPE: dict[str, list[str]] = {
    "law": ["general_information", "legal_reference", "source_lookup"],
    "service_guide": ["general_information", "resource_navigation", "source_lookup"],
    "health_education": ["general_information", "health_education", "source_lookup"],
    "care_manual": [
        "care_record",
        "care_summary",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ],
    "care_manual_appendix": ["form_reference", "manual_review", "source_lookup"],
    "risk_rule": ["manual_review", "safety_routing", "source_lookup"],
    "assessment_scale": [
        "human_administered_assessment_design",
        "research_reference",
        "scale_explanation",
    ],
    "research_article": ["explainable_evidence", "research_reference"],
}
PROFESSIONAL_SOURCE_TYPES = {
    "assessment_scale",
    "care_manual",
    "care_manual_appendix",
    "research_article",
    "risk_rule",
}
RESEARCH_SOURCE_TYPES = {"assessment_scale", "research_article"}


class SourceFamilyPolicyError(ValueError):
    """Raised when policy evidence, types, or deterministic gates diverge."""


@dataclass(frozen=True)
class SourceFamilyPolicySummary:
    artifact: str
    output_path: Path
    source_count: int
    chunk_count: int
    inventory_sha256: str | None = None
    prior_lock_sha256: str | None = None
    family_policy_candidate_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "chunk_count": self.chunk_count,
            "family_policy_candidate_count": self.family_policy_candidate_count,
            "inventory_sha256": self.inventory_sha256,
            "output_path": self.output_path.as_posix(),
            "prior_lock_sha256": self.prior_lock_sha256,
            "production_approved": False,
            "source_count": self.source_count,
            "status": "PASS",
        }


def prepare_source_family_policy_preflight(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> SourceFamilyPolicySummary:
    """Freeze policy audit inputs before reading any chunk metadata values."""

    root = repository_root.resolve()
    destination = (
        output_path.resolve()
        if output_path is not None
        else (root / AUDIT_PREFLIGHT_PATH).resolve()
    )
    if destination.exists():
        raise SourceFamilyPolicyError("source-family policy preflight exists; refuse to overwrite")
    validate_v3_owner_public_use_acceptance(root)
    validate_v3_preflight(root)
    prior_entries = _entries_for_roots(root, PRIOR_POLICY_INPUT_ROOTS, "rag_v3_prior_governance")
    input_entries = _audit_input_entries(root)
    prior_lock = _inventory_document(
        "source_family_policy_prior_artifact_lock",
        prior_entries,
        "immutable v003 acceptance and preflight v001 bytes",
    )
    input_inventory = _inventory_document(
        "source_family_policy_validation_input_inventory",
        input_entries,
        "17 v002 chunk files plus selected schemas, config, policy code, tests, and evidence",
    )
    staged = _new_staging_directory(root, "source-policy-preflight")
    try:
        _write_json(staged / "prior-artifact-lock.json", prior_lock)
        _write_json(staged / "validation-input-inventory.json", input_inventory)
        _write_text(staged / "README.md", _preflight_readme(prior_lock, input_inventory))
        _write_checksums(staged)
        validate_source_family_policy_preflight(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return SourceFamilyPolicySummary(
        artifact="source_family_policy_preflight",
        output_path=destination,
        source_count=17,
        chunk_count=726,
        inventory_sha256=input_inventory["inventory_sha256"],
        prior_lock_sha256=prior_lock["inventory_sha256"],
    )


def validate_source_family_policy_preflight(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Reject any selected input or prior-governance byte drift."""

    root = repository_root.resolve()
    package = (
        package_path.resolve()
        if package_path is not None
        else (root / AUDIT_PREFLIGHT_PATH).resolve()
    )
    validate_v3_owner_public_use_acceptance(root)
    validate_v3_preflight(root)
    _validate_package_checksums(package)
    prior_lock = _read_json(package / "prior-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        "source_family_policy_prior_artifact_lock",
        _entries_for_roots(root, PRIOR_POLICY_INPUT_ROOTS, "rag_v3_prior_governance"),
        "immutable v003 acceptance and preflight v001 bytes",
    )
    expected_inventory = _inventory_document(
        "source_family_policy_validation_input_inventory",
        _audit_input_entries(root),
        "17 v002 chunk files plus selected schemas, config, policy code, tests, and evidence",
    )
    if prior_lock != expected_lock:
        raise SourceFamilyPolicyError("source-family policy prior artifact lock mismatch")
    if inventory != expected_inventory:
        raise SourceFamilyPolicyError("source-family policy validation input inventory mismatch")
    return {
        "chunk_count": 726,
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "prior_artifact_entry_count": prior_lock["entry_count"],
        "prior_lock_sha256": prior_lock["inventory_sha256"],
        "production_approved": False,
        "source_count": 17,
        "status": "PASS",
    }


def validate_source_family_policy_build_preflight_snapshot(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate immutable v001 build evidence after successor inputs advance."""

    root = repository_root.resolve()
    package = (
        package_path.resolve()
        if package_path is not None
        else (root / AUDIT_PREFLIGHT_PATH).resolve()
    )
    validate_v3_owner_public_use_acceptance(root)
    validate_v3_preflight_build_snapshot(root)
    _validate_package_checksums(package)
    prior_lock = _read_json(package / "prior-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        "source_family_policy_prior_artifact_lock",
        _entries_for_roots(root, PRIOR_POLICY_INPUT_ROOTS, "rag_v3_prior_governance"),
        "immutable v003 acceptance and preflight v001 bytes",
    )
    if prior_lock != expected_lock:
        raise SourceFamilyPolicyError(
            "source-family policy build snapshot prior artifact lock mismatch"
        )
    if inventory["inventory_sha256"] != _canonical_sha256(inventory["entries"]):
        raise SourceFamilyPolicyError(
            "source-family policy build snapshot stored inventory digest mismatch"
        )
    return {
        "chunk_count": 726,
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "prior_artifact_entry_count": prior_lock["entry_count"],
        "prior_lock_sha256": prior_lock["inventory_sha256"],
        "production_approved": False,
        "source_count": 17,
        "status": "PASS_BUILD_SNAPSHOT",
    }


def build_source_family_policy(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> SourceFamilyPolicySummary:
    """Scan frozen public metadata and generate one conservative policy per source."""

    root = repository_root.resolve()
    destination = (
        output_path.resolve() if output_path is not None else (root / POLICY_PACKAGE_PATH).resolve()
    )
    if destination.exists():
        raise SourceFamilyPolicyError("source-family policy candidate exists; refuse to overwrite")
    preflight = validate_source_family_policy_preflight(root)
    records_by_source = _load_chunk_records(root)
    manifest = _read_json(root / SOURCE_MANIFEST_PATH)
    policy = _policy_document(root, manifest, records_by_source, preflight)
    worksheet = _remaining_review_worksheet(records_by_source, policy["source_policies"])
    _validate_policy_document(root, policy)
    _validate_policy_semantics(policy, worksheet)
    report = _validation_report(policy, worksheet)

    staged = _new_staging_directory(root, "source-policy-candidate")
    try:
        _write_json(staged / "source-family-policy-map.json", policy)
        _write_jsonl(staged / "remaining-review-worksheet.jsonl", worksheet)
        _write_json(staged / "validation-report.json", report)
        _write_text(staged / "README.md", _candidate_readme(policy))
        _write_checksums(staged)
        validate_source_family_policy(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return SourceFamilyPolicySummary(
        artifact="source_family_policy_candidate",
        output_path=destination,
        source_count=17,
        chunk_count=726,
        inventory_sha256=preflight["inventory_sha256"],
        prior_lock_sha256=preflight["prior_lock_sha256"],
        family_policy_candidate_count=policy["summary"]["family_policy_candidate_count"],
    )


def validate_source_family_policy(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Rebuild the deterministic policy and compare it with the candidate bytes."""

    root = repository_root.resolve()
    package = (
        package_path.resolve()
        if package_path is not None
        else (root / POLICY_PACKAGE_PATH).resolve()
    )
    preflight = validate_source_family_policy_build_preflight_snapshot(root)
    _validate_package_checksums(package)
    policy = _read_json(package / "source-family-policy-map.json")
    worksheet = _read_jsonl(package / "remaining-review-worksheet.jsonl")
    expected_policy = _policy_document(
        root,
        _read_json(root / SOURCE_MANIFEST_PATH),
        _load_chunk_records(root),
        preflight,
    )
    expected_worksheet = _remaining_review_worksheet(
        _load_chunk_records(root),
        expected_policy["source_policies"],
    )
    if policy != expected_policy:
        raise SourceFamilyPolicyError("source-family policy map is not reproducible")
    if worksheet != expected_worksheet:
        raise SourceFamilyPolicyError("remaining-review worksheet is not reproducible")
    _validate_policy_document(root, policy)
    _validate_policy_semantics(policy, worksheet)
    report = _read_json(package / "validation-report.json")
    if report != _validation_report(policy, worksheet):
        raise SourceFamilyPolicyError("source-family policy validation report mismatch")
    return {
        "chunk_count": 726,
        "family_policy_candidate_count": policy["summary"]["family_policy_candidate_count"],
        "license_evidence_missing_source_count": policy["summary"][
            "license_evidence_missing_source_count"
        ],
        "policy_sha256": _sha256_file(package / "source-family-policy-map.json"),
        "production_approved": False,
        "source_count": 17,
        "status": "PASS",
        "worksheet_sha256": _sha256_file(package / "remaining-review-worksheet.jsonl"),
    }


def _policy_document(
    root: Path,
    manifest: Mapping[str, Any],
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    source_policies = []
    for source in sorted(manifest["sources"], key=lambda item: item["source_id"]):
        source_id = source["source_id"]
        records = records_by_source.get(source_id)
        if records is None:
            raise SourceFamilyPolicyError(f"source manifest has no chunk file: {source_id}")
        source_policies.append(_source_policy(root, source, records))
    summary = _policy_summary(source_policies)
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "policy_map_version": "v001",
        "status": "STAGING_NEEDS_REVIEW",
        "acceptance_binding": {
            "path": OWNER_ACCEPTANCE_PATH.as_posix(),
            "sha256": _sha256_file(root / OWNER_ACCEPTANCE_PATH),
            "acceptance_version": "v001",
            "scope": "STAGING_PUBLIC_RETRIEVAL_POLICY",
        },
        "audit_preflight_binding": {
            "inventory_path": (AUDIT_PREFLIGHT_PATH / "validation-input-inventory.json").as_posix(),
            "inventory_sha256": preflight["inventory_sha256"],
            "prior_lock_path": (AUDIT_PREFLIGHT_PATH / "prior-artifact-lock.json").as_posix(),
            "prior_lock_sha256": preflight["prior_lock_sha256"],
        },
        "source_manifest_binding": {
            "path": SOURCE_MANIFEST_PATH.as_posix(),
            "sha256": _sha256_file(root / SOURCE_MANIFEST_PATH),
            "source_count": 17,
            "chunk_count": 726,
        },
        "global_policy": {
            "owner_approved_public_audiences": OFFICIAL_PUBLIC_AUDIENCES,
            "ordinary_rag_current_status": "current",
            "ordinary_rag_risk_levels": ["low", "medium"],
            "ordinary_rag_stop_normal_rag": False,
            "ordinary_rag_retrieval_eligible": True,
            "assessment_null_handling": "DENY",
            "license_evidence_required": True,
            "high_or_unknown_normal_rag": "DENY",
            "research_route": "INDEPENDENT_RESEARCH_REVIEW_REQUIRED",
            "runtime_safety_from_embedding_similarity": False,
            "automatic_official_assessment": False,
            "automatic_professional_assessment": False,
            "formal_item_review_required": True,
            "production_approved": False,
        },
        "source_policies": source_policies,
        "summary": summary,
        "gates": {
            "environment": "STAGING",
            "review_status": "needs_review",
            "external_sync": "NOT_AUTHORIZED",
            "supabase_release": "NOT_CREATED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _source_policy(
    root: Path,
    source: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    source_id = str(source["source_id"])
    source_type = str(source["source_type"])
    official = source["is_official_source"] is True
    chunk_path = CHUNK_ROOT / f"{source_id}.rag-chunk-v2.v002.jsonl"
    license_urls = sorted(set(source["license_evidence_urls"]))
    if not official:
        source_status = "INDEPENDENT_RESEARCH_ROUTE_ONLY"
    elif source_type in PROFESSIONAL_SOURCE_TYPES:
        source_status = "PROFESSIONAL_ROUTE_ONLY"
    elif not license_urls:
        source_status = "BLOCKED_LICENSE_EVIDENCE_MISSING"
    else:
        source_status = "CANDIDATE_WITH_CHUNK_GATES"
    audiences = (
        PROFESSIONAL_AUDIENCES
        if source_type in PROFESSIONAL_SOURCE_TYPES
        else OFFICIAL_PUBLIC_AUDIENCES
    )
    summary = _observed_summary(records, source_status, PURPOSES_BY_SOURCE_TYPE[source_type])
    requirements = ["FORMAL_ITEM_SOURCE_FIDELITY_NOT_RECORDED"]
    if not license_urls:
        requirements.append("LICENSE_EVIDENCE_MISSING")
    if summary["risk_counts"]["unclassified"]:
        requirements.append("RISK_CLASSIFICATION_REQUIRED")
    if (
        summary["stop_normal_rag_counts"]["true_count"]
        or summary["stop_normal_rag_counts"]["null_count"]
    ):
        requirements.append("STOP_NORMAL_RAG_REVIEW_REQUIRED")
    if (
        summary["current_status_counts"]["superseded"]
        or summary["current_status_counts"]["unknown"]
    ):
        requirements.append("SOURCE_VERSION_REVIEW_REQUIRED")
    if (
        summary["assessment_null_counts"]["official"]
        or summary["assessment_null_counts"]["professional"]
    ):
        requirements.append("ASSESSMENT_BOOLEAN_REVIEW_REQUIRED")
    if not official:
        requirements.append("INDEPENDENT_RESEARCH_ROUTE_REQUIRED")
    if source_type in {"risk_rule", "assessment_scale"}:
        requirements.append("PROFESSIONAL_POLICY_REVIEW_REQUIRED")
    return {
        "source_id": source_id,
        "title": source["title"],
        "source_type": source_type,
        "is_official_source": official,
        "distribution_scope": "public_knowledge" if official else "research_evidence",
        "storage_strategy": "rag_only",
        "evidence": {
            "chunk_file_path": chunk_path.as_posix(),
            "chunk_file_sha256": _sha256_file(root / chunk_path),
            "source_manifest_path": SOURCE_MANIFEST_PATH.as_posix(),
            "direct_source_urls": sorted(set(source["direct_source_urls"])),
            "official_source_page_urls": sorted(set(source["official_source_page_urls"])),
            "license_evidence_urls": license_urls,
            "storage_urls": sorted(set(source["storage_urls"])),
            "local_raw_source_bytes_available": False,
        },
        "policy_decision": {
            "allowed_audiences": audiences,
            "allowed_purposes": PURPOSES_BY_SOURCE_TYPE[source_type],
            "ordinary_rag_source_status": source_status,
            "purpose_handling": "INTERSECT_SOURCE_AND_CHUNK_PURPOSES",
            "assessment_handling": "PRESERVE_CHUNK_BOOLEANS_NULL_DENIES",
            "risk_handling": "LOW_MEDIUM_ONLY_HIGH_UNKNOWN_DENY",
            "stop_normal_rag_handling": "FALSE_ONLY_TRUE_OR_NULL_DENY",
            "license_handling": (
                "RECORDED_EVIDENCE_REVIEW_REQUIRED" if license_urls else "MISSING_EVIDENCE_BLOCK"
            ),
            "requires_human_review": True,
        },
        "observed_summary": summary,
        "review_requirements": sorted(set(requirements)),
        "review_status": "needs_review",
        "production_approved": False,
    }


def _observed_summary(
    records: Sequence[Mapping[str, Any]],
    source_status: str,
    source_purposes: Sequence[str],
) -> dict[str, Any]:
    risk = Counter(_risk_key(record["retrieval_policy"]["risk_level"]) for record in records)
    current = Counter(record["governance"]["current_status"] for record in records)
    stop = Counter(
        _nullable_bool_key(record["retrieval_policy"]["stop_normal_rag"]) for record in records
    )
    license_counts = Counter(record["governance"]["license_status"] for record in records)
    eligible = Counter(bool(record["retrieval_policy"]["retrieval_eligible"]) for record in records)
    audiences = sorted(
        {value for record in records for value in record["retrieval_policy"]["allowed_audiences"]}
    )
    purposes = sorted(
        {value for record in records for value in record["retrieval_policy"]["allowed_purposes"]}
    )
    metadata_cohort = [record for record in records if _metadata_cohort_eligible(record)]
    low_medium_stop_true_cohort = [
        record
        for record in records
        if record["retrieval_policy"]["risk_level"] in {"low", "medium"}
        and record["retrieval_policy"]["stop_normal_rag"] is True
    ]
    low_medium_stop_false_non_current_cohort = [
        record
        for record in records
        if record["governance"]["current_status"] != "current"
        and record["retrieval_policy"]["risk_level"] in {"low", "medium"}
        and record["retrieval_policy"]["stop_normal_rag"] is False
    ]
    complete_gate = [record for record in records if _complete_chunk_gate_eligible(record)]
    family_gate = [
        record
        for record in complete_gate
        if source_status == "CANDIDATE_WITH_CHUNK_GATES"
        and bool(set(record["retrieval_policy"]["allowed_purposes"]) & set(source_purposes))
    ]
    return {
        "chunk_count": len(records),
        "risk_counts": {
            "low": risk["low"],
            "medium": risk["medium"],
            "high": risk["high"],
            "high_red_line": risk["high_red_line"],
            "unclassified": risk["unclassified"],
        },
        "current_status_counts": {
            "current": current["current"],
            "superseded": current["superseded"],
            "unknown": current["unknown"],
        },
        "stop_normal_rag_counts": {
            "true_count": stop["true"],
            "false_count": stop["false"],
            "null_count": stop["null"],
        },
        "assessment_null_counts": {
            "official": sum(
                record["retrieval_policy"]["requires_official_assessment"] is None
                for record in records
            ),
            "professional": sum(
                record["retrieval_policy"]["requires_professional_assessment"] is None
                for record in records
            ),
        },
        "license_status_counts": {
            "approved": license_counts["approved"],
            "open": license_counts["open"],
            "permission_required": license_counts["permission_required"],
            "unknown": license_counts["unknown"],
        },
        "retrieval_eligible_counts": {
            "true_count": eligible[True],
            "false_count": eligible[False],
        },
        "observed_allowed_audiences": audiences,
        "observed_allowed_purposes": purposes,
        "low_medium_stop_true_cohort_count": len(low_medium_stop_true_cohort),
        "low_medium_stop_false_non_current_cohort_count": len(
            low_medium_stop_false_non_current_cohort
        ),
        "metadata_cohort_candidate_count": len(metadata_cohort),
        "complete_chunk_gate_candidate_count": len(complete_gate),
        "family_policy_candidate_count": len(family_gate),
    }


def _policy_summary(source_policies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summaries = [policy["observed_summary"] for policy in source_policies]
    official_summaries = [
        policy["observed_summary"] for policy in source_policies if policy["is_official_source"]
    ]
    return {
        "source_count": len(source_policies),
        "chunk_count": sum(item["chunk_count"] for item in summaries),
        "official_source_count": sum(policy["is_official_source"] for policy in source_policies),
        "research_source_count": sum(
            not policy["is_official_source"] for policy in source_policies
        ),
        "risk_high_count": sum(item["risk_counts"]["high"] for item in official_summaries),
        "risk_high_red_line_count": sum(
            item["risk_counts"]["high_red_line"] for item in official_summaries
        ),
        "risk_unclassified_count": sum(
            item["risk_counts"]["unclassified"] for item in official_summaries
        ),
        "official_raw_stop_normal_rag_true_count": sum(
            item["stop_normal_rag_counts"]["true_count"] for item in official_summaries
        ),
        "official_raw_non_current_count": sum(
            item["current_status_counts"]["superseded"] + item["current_status_counts"]["unknown"]
            for item in official_summaries
        ),
        "official_low_medium_stop_true_cohort_count": sum(
            item["low_medium_stop_true_cohort_count"] for item in official_summaries
        ),
        "official_low_medium_stop_false_non_current_cohort_count": sum(
            item["low_medium_stop_false_non_current_cohort_count"] for item in official_summaries
        ),
        "metadata_cohort_candidate_count": sum(
            item["metadata_cohort_candidate_count"] for item in official_summaries
        ),
        "complete_chunk_gate_candidate_count": sum(
            item["complete_chunk_gate_candidate_count"] for item in official_summaries
        ),
        "family_policy_candidate_count": sum(
            item["family_policy_candidate_count"] for item in summaries
        ),
        "license_evidence_missing_source_count": sum(
            not policy["evidence"]["license_evidence_urls"] for policy in source_policies
        ),
        "ordinary_rag_source_candidate_count": sum(
            policy["policy_decision"]["ordinary_rag_source_status"] == "CANDIDATE_WITH_CHUNK_GATES"
            for policy in source_policies
        ),
    }


def _remaining_review_worksheet(
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    source_policies: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for policy in source_policies:
        source_id = policy["source_id"]
        records = records_by_source[source_id]
        rows.append(
            {
                "schema_version": "1.0.0",
                "artifact_version": "v003",
                "policy_map_version": "v001",
                "source_id": source_id,
                "source_type": policy["source_type"],
                "chunk_file_path": policy["evidence"]["chunk_file_path"],
                "review_status": "needs_review",
                "decisions_required": policy["review_requirements"],
                "risk_unclassified_chunk_ids": _chunk_ids(
                    records,
                    lambda record: record["retrieval_policy"]["risk_level"] is None,
                ),
                "risk_high_chunk_ids": _chunk_ids(
                    records,
                    lambda record: record["retrieval_policy"]["risk_level"] == "high",
                ),
                "risk_high_red_line_chunk_ids": _chunk_ids(
                    records,
                    lambda record: record["retrieval_policy"]["risk_level"] == "high_red_line",
                ),
                "stop_normal_rag_review_chunk_ids": _chunk_ids(
                    records,
                    lambda record: record["retrieval_policy"]["stop_normal_rag"] is not False,
                ),
                "non_current_chunk_ids": _chunk_ids(
                    records,
                    lambda record: record["governance"]["current_status"] != "current",
                ),
                "assessment_null_chunk_ids": _chunk_ids(
                    records,
                    lambda record: (
                        record["retrieval_policy"]["requires_official_assessment"] is None
                        or record["retrieval_policy"]["requires_professional_assessment"] is None
                    ),
                ),
                "license_evidence_missing": not bool(policy["evidence"]["license_evidence_urls"]),
                "production_approved": False,
            }
        )
    return rows


def _validation_report(
    policy: Mapping[str, Any],
    worksheet: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = policy["summary"]
    checks = [
        "policy_schema_valid",
        "source_ids_unique_and_complete",
        "source_and_chunk_counts_match_manifest",
        "high_and_unknown_chunks_fail_closed",
        "all_audience_never_bypasses_chunk_gates",
        "research_sources_use_independent_route",
        "missing_license_evidence_blocks_ordinary_rag",
        "assessment_null_denies",
        "runtime_safety_not_started_from_similarity",
        "formal_assessment_not_automated",
        "worksheet_covers_all_sources",
        "external_sync_not_authorized",
        "production_blocked",
    ]
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "policy_map_version": "v001",
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "source_count": summary["source_count"],
        "chunk_count": summary["chunk_count"],
        "worksheet_row_count": len(worksheet),
        "risk_high_or_unknown_count": (
            summary["risk_high_count"]
            + summary["risk_high_red_line_count"]
            + summary["risk_unclassified_count"]
        ),
        "official_raw_stop_normal_rag_true_count": summary[
            "official_raw_stop_normal_rag_true_count"
        ],
        "official_raw_non_current_count": summary["official_raw_non_current_count"],
        "official_low_medium_stop_true_cohort_count": summary[
            "official_low_medium_stop_true_cohort_count"
        ],
        "official_low_medium_stop_false_non_current_cohort_count": summary[
            "official_low_medium_stop_false_non_current_cohort_count"
        ],
        "family_policy_candidate_count": summary["family_policy_candidate_count"],
        "review_status": "needs_review",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validate_policy_semantics(
    policy: Mapping[str, Any],
    worksheet: Sequence[Mapping[str, Any]],
) -> None:
    policies = policy["source_policies"]
    source_ids = [item["source_id"] for item in policies]
    if len(source_ids) != 17 or len(set(source_ids)) != 17:
        raise SourceFamilyPolicyError("source-family policy must contain 17 unique sources")
    if len(worksheet) != 17 or {row["source_id"] for row in worksheet} != set(source_ids):
        raise SourceFamilyPolicyError("remaining-review worksheet source coverage mismatch")
    summary = policy["summary"]
    if summary["chunk_count"] != 726:
        raise SourceFamilyPolicyError("source-family policy chunk count mismatch")
    if (
        summary["risk_high_count"]
        + summary["risk_high_red_line_count"]
        + summary["risk_unclassified_count"]
        != 74
    ):
        raise SourceFamilyPolicyError("planned high-or-unknown cohort must remain 74")
    if summary["risk_unclassified_count"] != 5:
        raise SourceFamilyPolicyError("planned unclassified risk cohort must remain 5")
    if summary["official_raw_stop_normal_rag_true_count"] != 35:
        raise SourceFamilyPolicyError("raw official stop_normal_rag=true count must remain 35")
    if summary["official_raw_non_current_count"] != 296:
        raise SourceFamilyPolicyError("raw official non-current count must remain 296")
    if summary["official_low_medium_stop_true_cohort_count"] != 27:
        raise SourceFamilyPolicyError("planned stop_normal_rag=true cohort must remain 27")
    if summary["official_low_medium_stop_false_non_current_cohort_count"] != 243:
        raise SourceFamilyPolicyError("planned non-current cohort must remain 243")
    for item in policies:
        decision = item["policy_decision"]
        if (
            not item["is_official_source"]
            and decision["ordinary_rag_source_status"] != "INDEPENDENT_RESEARCH_ROUTE_ONLY"
        ):
            raise SourceFamilyPolicyError("research source entered ordinary RAG")
        if (
            not item["evidence"]["license_evidence_urls"]
            and decision["ordinary_rag_source_status"] == "CANDIDATE_WITH_CHUNK_GATES"
        ):
            raise SourceFamilyPolicyError("missing license evidence did not block ordinary RAG")
        if item["production_approved"] is not False:
            raise SourceFamilyPolicyError("source-family policy approved Production")


def _validate_policy_document(root: Path, policy: Mapping[str, Any]) -> None:
    schema = _read_json(root / POLICY_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(policy), key=lambda error: list(error.absolute_path))
    if errors:
        raise SourceFamilyPolicyError(f"source-family policy schema failed: {errors[0].message}")


def _metadata_cohort_eligible(record: Mapping[str, Any]) -> bool:
    policy = record["retrieval_policy"]
    governance = record["governance"]
    return (
        governance["current_status"] == "current"
        and policy["risk_level"] in {"low", "medium"}
        and policy["stop_normal_rag"] is False
    )


def _complete_chunk_gate_eligible(record: Mapping[str, Any]) -> bool:
    policy = record["retrieval_policy"]
    governance = record["governance"]
    return (
        _metadata_cohort_eligible(record)
        and policy["retrieval_eligible"] is True
        and isinstance(policy["requires_official_assessment"], bool)
        and isinstance(policy["requires_professional_assessment"], bool)
        and bool(policy["allowed_audiences"])
        and bool(policy["allowed_purposes"])
        and governance["license_status"] in {"approved", "open"}
    )


def _load_chunk_records(root: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((root / CHUNK_ROOT).glob("*.jsonl")):
        records = _read_jsonl(path)
        if not records:
            raise SourceFamilyPolicyError(f"chunk file is empty: {path.name}")
        source_ids = {record["identity"]["source_id"] for record in records}
        if len(source_ids) != 1:
            raise SourceFamilyPolicyError(f"chunk file has mixed source IDs: {path.name}")
        source_id = next(iter(source_ids))
        if source_id in result:
            raise SourceFamilyPolicyError(f"duplicate source chunk file: {source_id}")
        indexes = [record["identity"]["chunk_index"] for record in records]
        if indexes != list(range(1, len(records) + 1)):
            raise SourceFamilyPolicyError(f"chunk indexes are not continuous: {source_id}")
        result[source_id] = records
    if len(result) != 17 or sum(len(records) for records in result.values()) != 726:
        raise SourceFamilyPolicyError("frozen chunk corpus must contain 17 sources and 726 chunks")
    return result


def _chunk_ids(
    records: Sequence[Mapping[str, Any]],
    predicate: Any,
) -> list[str]:
    return [record["identity"]["chunk_id"] for record in records if predicate(record)]


def _risk_key(value: Any) -> str:
    return "unclassified" if value is None else str(value)


def _nullable_bool_key(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "null"


def _audit_input_entries(root: Path) -> list[dict[str, Any]]:
    paths = [root / relative for relative in AUDIT_INPUT_PATHS]
    paths.extend(sorted((root / CHUNK_ROOT).glob("*.jsonl")))
    return _file_entries(root, paths, "source_family_policy_audit")


def _entries_for_roots(
    root: Path,
    relative_roots: Sequence[Path],
    logical_family: str,
) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for relative in relative_roots:
        absolute = root / relative
        if not absolute.is_dir():
            raise SourceFamilyPolicyError(f"prior artifact root missing: {relative.as_posix()}")
        paths.extend(path for path in absolute.rglob("*") if path.is_file())
    return _file_entries(root, paths, logical_family)


def _file_entries(
    root: Path,
    paths: Sequence[Path],
    logical_family: str,
) -> list[dict[str, Any]]:
    entries = []
    seen: set[str] = set()
    for path in sorted(set(paths), key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file():
            raise SourceFamilyPolicyError(
                f"audit input missing: {path.relative_to(root).as_posix()}"
            )
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            raise SourceFamilyPolicyError(f"duplicate audit input: {relative}")
        seen.add(relative)
        raw = _read_lf_utf8_bytes(path)
        source_id = "rag-v3-policy"
        if path.parent.name == "chunks":
            source_id = path.name.split(".rag-chunk", 1)[0]
        entries.append(
            {
                "path": relative,
                "artifact_kind": _artifact_kind(path),
                "source_id": source_id,
                "logical_family": logical_family,
                "version": _version_from_path(path),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "hash_mode": HASH_MODE,
            }
        )
    return entries


def _inventory_document(
    kind: str, entries: Sequence[Mapping[str, Any]], scope: str
) -> dict[str, Any]:
    payload = list(entries)
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "policy_map_version": "v001",
        "kind": kind,
        "scope": scope,
        "hash_mode": HASH_MODE,
        "inventory_hash_mode": CANONICAL_HASH_MODE,
        "entry_count": len(entries),
        "inventory_sha256": _canonical_sha256(payload),
        "entries": payload,
        "review_status": "needs_review",
        "production_approved": False,
    }


def _artifact_kind(path: Path) -> str:
    if path.suffix.casefold() == ".jsonl":
        return "chunk_jsonl"
    if path.suffix.casefold() == ".json":
        return "schema_or_governance_json"
    if path.suffix.casefold() in {".yaml", ".yml"}:
        return "configuration"
    if path.suffix.casefold() == ".py":
        return "implementation_or_test"
    if path.suffix.casefold() == ".md":
        return "policy_document"
    if path.name == "SHA256SUMS.txt":
        return "checksum_manifest"
    return "formal_artifact"


def _version_from_path(path: Path) -> str:
    return next(
        (part for part in reversed(path.parts) if re.fullmatch(r"v\d{3}", part)),
        "none",
    )


def _preflight_readme(lock: Mapping[str, Any], inventory: Mapping[str, Any]) -> str:
    return (
        "# Source-family policy audit preflight v001\n\n"
        "This package freezes the 17 v002 chunk files and the selected schema, config, policy, "
        "test, acceptance, and governance inputs before any metadata values are scanned. The "
        "v003 acceptance and preflight v001 packages remain immutable and Production remains "
        "blocked.\n\n"
        f"- Audit inputs: `{inventory['entry_count']}`\n"
        f"- Audit inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Prior artifacts: `{lock['entry_count']}`\n"
        f"- Prior lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- Review status: `needs_review`\n"
        "- External sync: not authorized\n"
        "- Production: blocked\n"
    )


def _candidate_readme(policy: Mapping[str, Any]) -> str:
    summary = policy["summary"]
    return (
        "# RAG v003 source-family policy candidate v001\n\n"
        "This candidate records one evidence-bound policy per source. It never replaces "
        "chunk-level purpose, assessment, risk, stop, current-status, license, or review gates. "
        "Research sources remain on an independent review route, missing license evidence blocks "
        "ordinary RAG, and runtime crisis handling is never triggered by embedding similarity.\n\n"
        f"- Sources/chunks: `{summary['source_count']}` / `{summary['chunk_count']}`\n"
        f"- Metadata cohort candidates before complete gates: "
        f"`{summary['metadata_cohort_candidate_count']}`\n"
        f"- Complete chunk-gate candidates: `{summary['complete_chunk_gate_candidate_count']}`\n"
        f"- Candidates after source-family policy: `{summary['family_policy_candidate_count']}`\n"
        f"- Sources missing license evidence: "
        f"`{summary['license_evidence_missing_source_count']}`\n"
        "- Review status: `needs_review`\n"
        "- Supabase release: not created\n"
        "- External sync: not authorized\n"
        "- Production: blocked\n"
    )


def _new_staging_directory(root: Path, label: str) -> Path:
    parent = root.parent.resolve()
    staged = Path(tempfile.mkdtemp(prefix=f".kinsun-{label}-", dir=parent)).resolve()
    if staged.parent != parent or not staged.name.startswith(f".kinsun-{label}-"):
        raise SourceFamilyPolicyError("unsafe source-family policy staging directory")
    return staged


def _publish_directory(staged: Path, destination: Path) -> None:
    if destination.exists():
        raise SourceFamilyPolicyError("source-family policy destination appeared before publish")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(destination)


def _cleanup_staging_directory(root: Path, staged: Path) -> None:
    resolved = staged.resolve()
    if not resolved.exists():
        return
    parent = root.parent.resolve()
    if resolved.parent != parent or not resolved.name.startswith(".kinsun-source-policy-"):
        raise SourceFamilyPolicyError("refuse to clean unsafe source-family staging directory")
    shutil.rmtree(resolved)


def _write_checksums(root: Path) -> None:
    entries = [
        f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
        if path.is_file() and path.name != "SHA256SUMS.txt"
    ]
    _write_text(root / "SHA256SUMS.txt", "\n".join(entries) + "\n")


def _validate_package_checksums(root: Path) -> None:
    checksums = _parse_checksums(root / "SHA256SUMS.txt")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    if set(checksums) != actual:
        raise SourceFamilyPolicyError("source-family package checksum inventory mismatch")
    for relative, digest in checksums.items():
        if _sha256_file(root / relative) != digest:
            raise SourceFamilyPolicyError(f"source-family package checksum mismatch: {relative}")


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in _read_lf_utf8_bytes(path).decode("utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        candidate = Path(relative)
        if (
            separator != "  "
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or candidate.is_absolute()
            or ".." in candidate.parts
            or relative in result
        ):
            raise SourceFamilyPolicyError(f"invalid checksum entry: {line}")
        result[relative] = digest
    if not result:
        raise SourceFamilyPolicyError("source-family checksum file is empty")
    return result


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_jsonl(path: Path, records: Sequence[Mapping[str, Any]]) -> None:
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    _write_text(path, "\n".join(lines) + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        _read_lf_utf8_bytes(path).decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(value, dict):
        raise SourceFamilyPolicyError(f"JSON object required: {path.as_posix()}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = _read_lf_utf8_bytes(path).decode("utf-8")
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise SourceFamilyPolicyError(f"JSONL blank line or empty file: {path.as_posix()}")
    records = []
    for line in lines:
        value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(value, dict):
            raise SourceFamilyPolicyError(f"JSONL object required: {path.as_posix()}")
        records.append(value)
    return records


def _read_lf_utf8_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise SourceFamilyPolicyError(f"text must be UTF-8 LF without BOM: {path.as_posix()}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceFamilyPolicyError(f"invalid UTF-8: {path.as_posix()}") from exc
    return raw


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourceFamilyPolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

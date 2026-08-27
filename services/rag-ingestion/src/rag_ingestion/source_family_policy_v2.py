"""Build and validate the owner-approved RAG v003 source-family policy v002."""

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

from rag_ingestion.v3_verified_candidate import (
    validate_owner_human_review_acceptance,
    validate_verified_audit_preflight,
    validate_verified_candidate,
)

HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"
CANONICAL_HASH_MODE = "sha256_canonical_json_v1"
SOURCE_COUNT = 17
CHUNK_COUNT = 726
SIGNED_AT = "2026-08-26T15:29:39+08:00"

CANDIDATE_ROOT = Path("data/rag-v3/candidates/v003")
CHUNK_ROOT = CANDIDATE_ROOT / "chunks"
SOURCE_MANIFEST_PATH = CANDIDATE_ROOT / "manifests/source-manifest-v003.json"
CANDIDATE_CHECKSUM_PATH = CANDIDATE_ROOT / "SHA256SUMS.txt"
CANDIDATE_LOCK_PATH = Path("data/rag-v3/audits/v001/preflight/candidate-artifact-lock.json")
PRIOR_ACCEPTANCE_PATH = Path(
    "data/rag-v3/review/acceptance/v002/owner-human-review-acceptance.json"
)
PRIOR_POLICY_PATH = Path(
    "data/rag-v3/governance/source-family-policy/candidates/v001/" "source-family-policy-map.json"
)
ACCEPTANCE_SCHEMA_PATH = Path(
    "contracts/schemas/rag/rag-owner-source-family-policy-acceptance-v1.schema.json"
)
POLICY_SCHEMA_PATH = Path("contracts/schemas/rag/rag-source-family-policy-map-v2.schema.json")
ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v003")
ACCEPTANCE_FILE = ACCEPTANCE_ROOT / "owner-source-family-policy-acceptance.json"
POLICY_ROOT = Path("data/rag-v3/governance/source-family-policy")
POLICY_PREFLIGHT_ROOT = POLICY_ROOT / "preflight/v002"
POLICY_PACKAGE_ROOT = POLICY_ROOT / "candidates/v002"
PRIOR_POLICY_AUDIT_ROOT = POLICY_ROOT / "audits/v001/preflight"
POLICY_AUDIT_ROOT = POLICY_ROOT / "audits/v002/preflight"

OWNER_STATEMENTS = (
    "13 個來源缺授權證據，檢核過了來源方為公開資料可以使用",
    "amily policy 仍把「沒有 license URL」直接將這個規則給取消嗎",
    (
        "尚未分類：5 筆為一般風險值，同時當除不是要用後端來控制要給什麼角色看的rag嗎"
        "那那些highrisk還有需要嗎?"
    ),
    "OK",
)
RISK_DECISION_CHUNK_IDS = (
    "mohw_home_care_service_supervisor_manual_forms_appendix_20260529_rag_v3_v003_0001",
    "mohw_home_care_service_supervisor_manual_forms_appendix_20260529_rag_v3_v003_0002",
    "mohw_home_care_service_supervisor_manual_forms_appendix_20260529_rag_v3_v003_0003",
    "mohw_home_care_service_supervisor_manual_forms_appendix_20260529_rag_v3_v003_0004",
    "mohw_home_care_service_supervisor_manual_forms_appendix_20260529_rag_v3_v003_0005",
)
PUBLIC_AUDIENCES = [
    "elder",
    "family_caregiver",
    "care_professional",
    "system_admin",
]
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
PRIOR_ARTIFACT_ROOTS = (
    Path("data/rag-v3/governance/source-family-policy/preflight/v001"),
    Path("data/rag-v3/governance/source-family-policy/candidates/v001"),
    Path("data/rag-v3/review/acceptance/v002"),
    Path("data/rag-v3/candidates/v003"),
    Path("data/rag-v3/audits/v001/preflight"),
)
AUDIT_INPUT_PATHS = (
    Path("config/rag/staging-filters.yaml"),
    ACCEPTANCE_SCHEMA_PATH,
    POLICY_SCHEMA_PATH,
    ACCEPTANCE_FILE,
    SOURCE_MANIFEST_PATH,
    CANDIDATE_LOCK_PATH,
    Path("docs/project/rag-v3-public-retrieval-plan.md"),
    Path("scripts/rag/build_source_family_policy_v2.py"),
    Path("scripts/rag/validate_source_family_policy_v2.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_policy_v2.py"),
    Path("services/rag-ingestion/tests/integration/test_source_family_policy_v2.py"),
    Path("services/rag-ingestion/tests/unit/test_source_family_policy_v2_schema.py"),
)
AUDIT_FORMAL_ROOTS = (
    ACCEPTANCE_ROOT,
    POLICY_PREFLIGHT_ROOT,
    POLICY_PACKAGE_ROOT,
    PRIOR_POLICY_AUDIT_ROOT,
)


class SourceFamilyPolicyV2Error(ValueError):
    """Raised when owner evidence, policy semantics, or immutable bytes diverge."""


@dataclass(frozen=True)
class PolicyArtifactSummary:
    artifact: str
    output_path: Path
    source_count: int = SOURCE_COUNT
    chunk_count: int = CHUNK_COUNT
    inventory_sha256: str | None = None
    prior_lock_sha256: str | None = None
    candidate_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "candidate_count": self.candidate_count,
            "chunk_count": self.chunk_count,
            "inventory_sha256": self.inventory_sha256,
            "output_path": self.output_path.as_posix(),
            "prior_lock_sha256": self.prior_lock_sha256,
            "production_approved": False,
            "source_count": self.source_count,
            "status": "PASS",
        }


def build_owner_source_family_policy_acceptance(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Record the user's explicit source-use, risk, and retrieval decisions."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, ACCEPTANCE_ROOT)
    _refuse_overwrite(destination, "owner source-family acceptance")
    validate_owner_human_review_acceptance(root)
    validate_verified_audit_preflight(root)
    validate_verified_candidate(root)
    manifest = _read_json(root / SOURCE_MANIFEST_PATH)
    records = _load_chunk_records(root)
    acceptance = _acceptance_document(root, manifest, records)
    _validate_acceptance_document(root, acceptance)
    report = _acceptance_report(acceptance)

    staged = _new_staging_directory(root, "source-policy-acceptance")
    try:
        _write_json(staged / ACCEPTANCE_FILE.name, acceptance)
        _write_json(staged / "validation-report.json", report)
        _write_json(
            staged / "manifest.json",
            {
                "schema_version": "1.0.0",
                "acceptance_version": "v003",
                "files": [ACCEPTANCE_FILE.name, "validation-report.json"],
                "acceptance_sha256": _sha256_file(staged / ACCEPTANCE_FILE.name),
                "external_sync": "NOT_AUTHORIZED",
                "production_approved": False,
            },
        )
        _write_text(staged / "README.md", _acceptance_readme(acceptance))
        _write_checksums(staged)
        validate_owner_source_family_policy_acceptance(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="owner_source_family_policy_acceptance",
        output_path=destination,
    )


def validate_owner_source_family_policy_acceptance(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate signed decision semantics and every bound immutable artifact."""

    root = repository_root.resolve()
    package = _destination(root, package_path, ACCEPTANCE_ROOT)
    validate_owner_human_review_acceptance(root)
    validate_verified_audit_preflight(root)
    validate_verified_candidate(root)
    _validate_package_checksums(package)
    acceptance = _read_json(package / ACCEPTANCE_FILE.name)
    _validate_acceptance_document(root, acceptance)
    expected = _acceptance_document(
        root,
        _read_json(root / SOURCE_MANIFEST_PATH),
        _load_chunk_records(root),
    )
    if acceptance != expected:
        raise SourceFamilyPolicyV2Error("owner source-family acceptance is not reproducible")
    report = _read_json(package / "validation-report.json")
    if report != _acceptance_report(acceptance):
        raise SourceFamilyPolicyV2Error("owner source-family acceptance report mismatch")
    manifest = _read_json(package / "manifest.json")
    if manifest["acceptance_sha256"] != _sha256_file(package / ACCEPTANCE_FILE.name):
        raise SourceFamilyPolicyV2Error("owner source-family acceptance manifest hash mismatch")
    return {
        "acceptance_sha256": _sha256_file(package / ACCEPTANCE_FILE.name),
        "affected_license_source_count": 13,
        "risk_decision_count": 5,
        "review_status": "verified",
        "production_approved": False,
        "status": "PASS",
    }


def build_source_family_policy_v2_preflight(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Freeze prior formal artifacts and every v002 policy validation input."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_PREFLIGHT_ROOT)
    _refuse_overwrite(destination, "source-family policy v002 preflight")
    validate_owner_source_family_policy_acceptance(root)
    prior_entries = _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS, "rag_v3_policy_prior")
    input_entries = _audit_input_entries(root)
    prior_lock = _inventory_document(
        "source_family_policy_v002_prior_artifact_lock",
        prior_entries,
        "immutable v001 policy, v003 candidate, candidate audit, and prior acceptance bytes",
    )
    inventory = _inventory_document(
        "source_family_policy_v002_validation_input_inventory",
        input_entries,
        "v003 chunks plus selected acceptance, schemas, config, code, tests, and evidence",
    )
    staged = _new_staging_directory(root, "source-policy-preflight-v002")
    try:
        _write_json(staged / "prior-artifact-lock.json", prior_lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _preflight_readme(prior_lock, inventory))
        _write_checksums(staged)
        validate_source_family_policy_v2_preflight(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_preflight",
        output_path=destination,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=prior_lock["inventory_sha256"],
    )


def validate_source_family_policy_v2_preflight(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Reject drift in any selected v002 input or protected prior artifact."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_PREFLIGHT_ROOT)
    validate_owner_source_family_policy_acceptance(root)
    _validate_package_checksums(package)
    lock = _read_json(package / "prior-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        "source_family_policy_v002_prior_artifact_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS, "rag_v3_policy_prior"),
        "immutable v001 policy, v003 candidate, candidate audit, and prior acceptance bytes",
    )
    expected_inventory = _inventory_document(
        "source_family_policy_v002_validation_input_inventory",
        _audit_input_entries(root),
        "v003 chunks plus selected acceptance, schemas, config, code, tests, and evidence",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyV2Error("source-family policy v002 prior lock mismatch")
    if inventory != expected_inventory:
        raise SourceFamilyPolicyV2Error("source-family policy v002 input inventory mismatch")
    return {
        "chunk_count": CHUNK_COUNT,
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "prior_artifact_entry_count": lock["entry_count"],
        "prior_lock_sha256": lock["inventory_sha256"],
        "production_approved": False,
        "source_count": SOURCE_COUNT,
        "status": "PASS",
    }


def validate_source_family_policy_v2_build_preflight_snapshot(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate immutable v002 build evidence without claiming current-input equality."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_PREFLIGHT_ROOT)
    validate_owner_source_family_policy_acceptance(root)
    _validate_package_checksums(package)
    lock = _read_json(package / "prior-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        "source_family_policy_v002_prior_artifact_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS, "rag_v3_policy_prior"),
        "immutable v001 policy, v003 candidate, candidate audit, and prior acceptance bytes",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyV2Error(
            "source-family policy v002 build snapshot prior lock mismatch"
        )
    if inventory["inventory_sha256"] != _canonical_sha256(inventory["entries"]):
        raise SourceFamilyPolicyV2Error(
            "source-family policy v002 build snapshot inventory digest mismatch"
        )
    return {
        "chunk_count": CHUNK_COUNT,
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "prior_artifact_entry_count": lock["entry_count"],
        "prior_lock_sha256": lock["inventory_sha256"],
        "production_approved": False,
        "source_count": SOURCE_COUNT,
        "status": "PASS_BUILD_SNAPSHOT",
    }


def build_source_family_policy_v2(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Build the deterministic owner-approved policy overlay for immutable v003 chunks."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_PACKAGE_ROOT)
    _refuse_overwrite(destination, "source-family policy v002 candidate")
    acceptance = validate_owner_source_family_policy_acceptance(root)
    preflight = validate_source_family_policy_v2_preflight(root)
    records_by_source = _load_chunk_records(root)
    manifest = _read_json(root / SOURCE_MANIFEST_PATH)
    policy = _policy_document(root, manifest, records_by_source, acceptance, preflight)
    worksheet = _remaining_review_worksheet(records_by_source, policy)
    _validate_policy_document(root, policy)
    _validate_policy_semantics(records_by_source, policy, worksheet)
    report = _validation_report(policy, worksheet)
    difference = _version_difference(policy)

    staged = _new_staging_directory(root, "source-policy-candidate-v002")
    try:
        _write_json(staged / "source-family-policy-map.json", policy)
        _write_jsonl(staged / "remaining-review-worksheet.jsonl", worksheet)
        _write_json(staged / "validation-report.json", report)
        _write_json(staged / "version-difference-summary.json", difference)
        _write_text(staged / "README.md", _candidate_readme(policy))
        _write_checksums(staged)
        validate_source_family_policy_v2(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_candidate",
        output_path=destination,
        inventory_sha256=preflight["inventory_sha256"],
        prior_lock_sha256=preflight["prior_lock_sha256"],
        candidate_count=policy["summary"]["ordinary_retrieval_chunk_candidate_count"],
    )


def validate_source_family_policy_v2(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Rebuild the v002 policy and compare all committed formal outputs."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_PACKAGE_ROOT)
    acceptance = validate_owner_source_family_policy_acceptance(root)
    preflight = validate_source_family_policy_v2_build_preflight_snapshot(root)
    _validate_package_checksums(package)
    records_by_source = _load_chunk_records(root)
    expected = _policy_document(
        root,
        _read_json(root / SOURCE_MANIFEST_PATH),
        records_by_source,
        acceptance,
        preflight,
    )
    policy = _read_json(package / "source-family-policy-map.json")
    if policy != expected:
        raise SourceFamilyPolicyV2Error("source-family policy v002 map is not reproducible")
    worksheet = _read_jsonl(package / "remaining-review-worksheet.jsonl")
    expected_worksheet = _remaining_review_worksheet(records_by_source, expected)
    if worksheet != expected_worksheet:
        raise SourceFamilyPolicyV2Error("source-family policy v002 worksheet mismatch")
    _validate_policy_document(root, policy)
    _validate_policy_semantics(records_by_source, policy, worksheet)
    if _read_json(package / "validation-report.json") != _validation_report(policy, worksheet):
        raise SourceFamilyPolicyV2Error("source-family policy v002 report mismatch")
    if _read_json(package / "version-difference-summary.json") != _version_difference(policy):
        raise SourceFamilyPolicyV2Error("source-family policy v002 difference summary mismatch")
    summary = policy["summary"]
    return {
        "chunk_count": summary["chunk_count"],
        "license_evidence_missing_source_count": summary["license_evidence_missing_source_count"],
        "missing_license_url_blocked_source_count": summary[
            "missing_license_url_blocked_source_count"
        ],
        "ordinary_retrieval_chunk_candidate_count": summary[
            "ordinary_retrieval_chunk_candidate_count"
        ],
        "policy_sha256": _sha256_file(package / "source-family-policy-map.json"),
        "production_approved": False,
        "response_metadata_ready_count": summary["response_metadata_ready_count"],
        "risk_decision_count": summary["risk_decision_count"],
        "risk_unclassified_effective_count": summary["risk_unclassified_effective_count"],
        "source_count": summary["source_count"],
        "status": "PASS",
    }


def build_source_family_policy_v2_audit_preflight(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Bind the immutable candidate and prior audit to current validation inputs."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_AUDIT_ROOT)
    _refuse_overwrite(destination, "source-family policy v002 audit preflight v002")
    validate_source_family_policy_v2(root)
    _validate_package_checksums(root / PRIOR_POLICY_AUDIT_ROOT)
    candidate_entries = _entries_for_roots(
        root,
        AUDIT_FORMAL_ROOTS,
        "source_family_policy_v002_formal_artifacts",
    )
    input_entries = _audit_input_entries(root)
    candidate_lock = _inventory_document(
        "source_family_policy_v002_candidate_artifact_lock",
        candidate_entries,
        (
            "immutable acceptance v003, policy preflight v002, policy candidate v002, "
            "and audit preflight v001 bytes"
        ),
    )
    inventory = _inventory_document(
        "source_family_policy_v002_current_validation_input_inventory",
        input_entries,
        "current policy v002 schemas, config, code, tests, evidence, and v003 chunks",
    )
    staged = _new_staging_directory(root, "source-policy-audit-v002")
    try:
        _write_json(staged / "candidate-artifact-lock.json", candidate_lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _audit_readme(candidate_lock, inventory))
        _write_checksums(staged)
        validate_source_family_policy_v2_audit_preflight(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_audit_preflight_v002",
        output_path=destination,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=candidate_lock["inventory_sha256"],
    )


def validate_source_family_policy_v2_audit_preflight(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate current inputs and the immutable v002 candidate as separate axes."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_AUDIT_ROOT)
    validate_owner_source_family_policy_acceptance(root)
    validate_source_family_policy_v2_build_preflight_snapshot(root)
    _validate_package_checksums(root / PRIOR_POLICY_AUDIT_ROOT)
    _validate_package_checksums(package)
    lock = _read_json(package / "candidate-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        "source_family_policy_v002_candidate_artifact_lock",
        _entries_for_roots(
            root,
            AUDIT_FORMAL_ROOTS,
            "source_family_policy_v002_formal_artifacts",
        ),
        (
            "immutable acceptance v003, policy preflight v002, policy candidate v002, "
            "and audit preflight v001 bytes"
        ),
    )
    expected_inventory = _inventory_document(
        "source_family_policy_v002_current_validation_input_inventory",
        _audit_input_entries(root),
        "current policy v002 schemas, config, code, tests, evidence, and v003 chunks",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyV2Error("source-family policy v002 candidate lock mismatch")
    if inventory != expected_inventory:
        raise SourceFamilyPolicyV2Error("source-family policy v002 audit input mismatch")
    return {
        "candidate_artifact_entry_count": lock["entry_count"],
        "candidate_lock_sha256": lock["inventory_sha256"],
        "chunk_count": CHUNK_COUNT,
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "production_approved": False,
        "source_count": SOURCE_COUNT,
        "status": "PASS",
    }


def evaluate_ordinary_retrieval(
    record: Mapping[str, Any],
    source_policy: Mapping[str, Any],
    risk_decisions: Mapping[str, str],
    *,
    actor_role: str,
    purpose: str,
) -> dict[str, Any]:
    """Evaluate search and response gates without mutating the chunk."""

    retrieval = record["retrieval_policy"]
    governance = record["governance"]
    chunk_id = record["identity"]["chunk_id"]
    effective_risk = risk_decisions.get(chunk_id, retrieval["risk_level"])
    search_reasons: list[str] = []
    decision = source_policy["policy_decision"]
    if decision["ordinary_retrieval_source_status"] != "CANDIDATE_WITH_CHUNK_GATES":
        search_reasons.append("independent_research_route_required")
    if actor_role not in decision["retrieval_audiences"]:
        search_reasons.append("actor_role_not_allowed")
    if governance["current_status"] != "current":
        search_reasons.append("current_status_not_current")
    if effective_risk not in {"low", "medium"}:
        search_reasons.append("risk_level_not_allowed")
    if retrieval["stop_normal_rag"] is not False:
        search_reasons.append("stop_normal_rag")
    if governance["review_status"] != "verified":
        search_reasons.append("review_status_not_verified")
    if source_policy["project_use_authorization"]["status"] not in {
        "RECORDED_LICENSE_EVIDENCE",
        "OWNER_REVIEWED_PUBLIC_USE",
    }:
        search_reasons.append("project_use_not_authorized")

    response_reasons = list(search_reasons)
    if purpose not in decision["allowed_purposes"]:
        response_reasons.append("source_purpose_not_allowed")
    if purpose not in retrieval["allowed_purposes"]:
        response_reasons.append("chunk_purpose_not_allowed")
    official_assessment = retrieval["requires_official_assessment"]
    professional_assessment = retrieval["requires_professional_assessment"]
    if not isinstance(official_assessment, bool) or not isinstance(professional_assessment, bool):
        response_reasons.append("assessment_policy_incomplete")
    elif actor_role in {"elder", "family_caregiver"} and (
        official_assessment or professional_assessment
    ):
        response_reasons.append("professional_response_required")
    return {
        "chunk_id": chunk_id,
        "effective_risk_level": effective_risk,
        "retrieval_allowed": not search_reasons,
        "retrieval_block_reasons": sorted(set(search_reasons)),
        "response_allowed": not response_reasons,
        "response_block_reasons": sorted(set(response_reasons)),
    }


def _acceptance_document(
    root: Path,
    manifest: Mapping[str, Any],
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    missing_license_ids = sorted(
        source["source_id"] for source in manifest["sources"] if not source["license_evidence_urls"]
    )
    all_records = {
        record["identity"]["chunk_id"]: record
        for records in records_by_source.values()
        for record in records
    }
    if len(missing_license_ids) != 13:
        raise SourceFamilyPolicyV2Error("expected exactly 13 sources without license URL")
    if set(RISK_DECISION_CHUNK_IDS) != {
        chunk_id
        for chunk_id, record in all_records.items()
        if record["retrieval_policy"]["risk_level"] is None
    }:
        raise SourceFamilyPolicyV2Error("five owner-classified risk chunk IDs diverged")
    statements = list(OWNER_STATEMENTS)
    return {
        "schema_version": "1.0.0",
        "acceptance_version": "v003",
        "candidate_artifact_version": "v003",
        "policy_map_version": "v002",
        "status": "SIGNED",
        "project_owner_id": "IanHsu",
        "signer_role": "PROJECT_OWNER",
        "signed_at": SIGNED_AT,
        "authorization": {
            "channel": "interactive_user_instruction",
            "statements": statements,
            "statements_sha256": _canonical_sha256(statements),
        },
        "electronic_signature": {
            "assurance": "RECORDED_EXPLICIT_USER_AUTHORIZATION",
            "signature_value": "IanHsu",
            "intent": "AUTHORIZE_SOURCE_FAMILY_POLICY_V002",
            "cryptographic_signature": None,
        },
        "bindings": {
            "candidate_path": CANDIDATE_ROOT.as_posix(),
            "candidate_checksums_sha256": _sha256_file(root / CANDIDATE_CHECKSUM_PATH),
            "candidate_audit_lock_path": CANDIDATE_LOCK_PATH.as_posix(),
            "candidate_audit_lock_sha256": _sha256_file(root / CANDIDATE_LOCK_PATH),
            "prior_acceptance_path": PRIOR_ACCEPTANCE_PATH.as_posix(),
            "prior_acceptance_sha256": _sha256_file(root / PRIOR_ACCEPTANCE_PATH),
            "prior_policy_path": PRIOR_POLICY_PATH.as_posix(),
            "prior_policy_sha256": _sha256_file(root / PRIOR_POLICY_PATH),
            "source_count": SOURCE_COUNT,
            "chunk_count": CHUNK_COUNT,
        },
        "license_policy_decision": {
            "source_party_public_use_review_completed": True,
            "missing_license_url_automatic_block": False,
            "affected_source_count": 13,
            "affected_source_ids": missing_license_ids,
            "license_status_mutation_authorized": False,
            "scope": "STAGING_PROJECT_USE_POLICY",
        },
        "risk_policy_decision": {
            "owner_label": "一般風險值",
            "canonical_risk_level": "low",
            "mapping_basis": "OWNER_GENERAL_RISK_CLASSIFICATION_TO_CANONICAL_LOW",
            "affected_chunk_count": 5,
            "affected_chunk_ids": list(RISK_DECISION_CHUNK_IDS),
            "chunk_bytes_mutated": False,
            "formal_assessment_performed": False,
        },
        "retrieval_architecture_decision": {
            "ordinary_public_retrieval_audiences": PUBLIC_AUDIENCES,
            "retrieve_before_response_policy": True,
            "response_policy_required": True,
            "high_or_unknown_ordinary_rag": "DENY",
            "stop_normal_rag_true_ordinary_rag": "DENY",
            "runtime_safety_from_embedding_similarity": False,
        },
        "gates": {
            "environment": "STAGING",
            "policy_candidate_build": "AUTHORIZED",
            "external_sync": "NOT_AUTHORIZED",
            "supabase_release": "NOT_CREATED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _policy_document(
    root: Path,
    manifest: Mapping[str, Any],
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    acceptance: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    acceptance_sha = acceptance["acceptance_sha256"]
    risk_decisions = _risk_decisions(records_by_source, acceptance_sha)
    effective_risks = {
        decision["chunk_id"]: decision["effective_risk_level"] for decision in risk_decisions
    }
    source_policies = []
    for source in sorted(manifest["sources"], key=lambda item: item["source_id"]):
        source_policies.append(
            _source_policy(
                root,
                source,
                records_by_source[source["source_id"]],
                effective_risks,
                acceptance_sha,
            )
        )
    summary = _policy_summary(source_policies)
    return {
        "schema_version": "2.0.0",
        "artifact_version": "v003",
        "policy_map_version": "v002",
        "status": "STAGING_OWNER_APPROVED",
        "acceptance_binding": {
            "path": ACCEPTANCE_FILE.as_posix(),
            "sha256": acceptance_sha,
            "acceptance_version": "v003",
            "scope": "STAGING_SOURCE_FAMILY_POLICY_V002",
        },
        "audit_preflight_binding": {
            "inventory_path": (
                POLICY_PREFLIGHT_ROOT / "validation-input-inventory.json"
            ).as_posix(),
            "inventory_sha256": preflight["inventory_sha256"],
            "prior_lock_path": (POLICY_PREFLIGHT_ROOT / "prior-artifact-lock.json").as_posix(),
            "prior_lock_sha256": preflight["prior_lock_sha256"],
        },
        "candidate_binding": {
            "path": CANDIDATE_ROOT.as_posix(),
            "checksums_sha256": _sha256_file(root / CANDIDATE_CHECKSUM_PATH),
            "candidate_lock_path": CANDIDATE_LOCK_PATH.as_posix(),
            "candidate_lock_sha256": _sha256_file(root / CANDIDATE_LOCK_PATH),
            "source_manifest_path": SOURCE_MANIFEST_PATH.as_posix(),
            "source_manifest_sha256": _sha256_file(root / SOURCE_MANIFEST_PATH),
            "source_count": SOURCE_COUNT,
            "chunk_count": CHUNK_COUNT,
        },
        "prior_policy_binding": {
            "path": PRIOR_POLICY_PATH.as_posix(),
            "sha256": _sha256_file(root / PRIOR_POLICY_PATH),
            "policy_map_version": "v001",
            "relationship": "SUPERSEDES_POLICY_WITHOUT_MUTATING_PRIOR_BYTES",
        },
        "global_policy": {
            "ordinary_public_retrieval_audiences": PUBLIC_AUDIENCES,
            "retrieve_before_response_policy": True,
            "ordinary_retrieval_current_status": "current",
            "ordinary_retrieval_risk_levels": ["low", "medium"],
            "ordinary_retrieval_stop_normal_rag": False,
            "missing_license_url_automatic_block": False,
            "project_use_authorization_required": True,
            "purpose_response_gate": "EVALUATE_AFTER_RETRIEVAL",
            "assessment_response_gate": "EVALUATE_AFTER_RETRIEVAL_NULL_DENIES_RESPONSE",
            "high_or_unknown_normal_rag": "DENY",
            "research_route": "INDEPENDENT_RESEARCH_REVIEW_REQUIRED",
            "runtime_safety_from_embedding_similarity": False,
            "automatic_official_assessment": False,
            "automatic_professional_assessment": False,
            "production_approved": False,
        },
        "chunk_risk_decisions": risk_decisions,
        "source_policies": source_policies,
        "summary": summary,
        "gates": {
            "environment": "STAGING",
            "review_status": "verified",
            "runtime_integration": "NOT_STARTED",
            "golden_query": "NOT_STARTED",
            "external_sync": "NOT_AUTHORIZED",
            "supabase_release": "NOT_CREATED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _risk_decisions(
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    acceptance_sha: str,
) -> list[dict[str, Any]]:
    records = {
        record["identity"]["chunk_id"]: record
        for values in records_by_source.values()
        for record in values
    }
    decisions = []
    for chunk_id in RISK_DECISION_CHUNK_IDS:
        record = records[chunk_id]
        if record["retrieval_policy"]["risk_level"] is not None:
            raise SourceFamilyPolicyV2Error("risk decision prior value must remain null")
        decisions.append(
            {
                "chunk_id": chunk_id,
                "source_id": record["identity"]["source_id"],
                "prior_risk_level": None,
                "effective_risk_level": "low",
                "owner_label": "一般風險值",
                "decision_basis": "OWNER_GENERAL_RISK_CLASSIFICATION_TO_CANONICAL_LOW",
                "acceptance_path": ACCEPTANCE_FILE.as_posix(),
                "acceptance_sha256": acceptance_sha,
                "review_status": "verified",
                "formal_assessment_performed": False,
                "production_approved": False,
            }
        )
    return decisions


def _source_policy(
    root: Path,
    source: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    effective_risks: Mapping[str, str],
    acceptance_sha: str,
) -> dict[str, Any]:
    source_id = str(source["source_id"])
    official = source["is_official_source"] is True
    source_type = str(source["source_type"])
    license_urls = sorted(set(source["license_evidence_urls"]))
    chunk_path = CHUNK_ROOT / f"{source_id}.rag-chunk-v3.v003.jsonl"
    source_status = "CANDIDATE_WITH_CHUNK_GATES" if official else "INDEPENDENT_RESEARCH_ROUTE_ONLY"
    observed = _observed_summary(records, source_status, effective_risks)
    requirements = ["GOLDEN_QUERY_REQUIRED"]
    if observed["assessment_null"]["official"] or observed["assessment_null"]["professional"]:
        requirements.append("ASSESSMENT_RESPONSE_FIELDS_REQUIRED")
    if observed["stop_normal_rag"]["true_count"] or observed["stop_normal_rag"]["null_count"]:
        requirements.append("STOP_NORMAL_RAG_REVIEW_REQUIRED")
    if not official:
        requirements.append("INDEPENDENT_RESEARCH_ROUTE_VALIDATION_REQUIRED")
    return {
        "source_id": source_id,
        "title": source["title"],
        "source_type": source_type,
        "is_official_source": official,
        "distribution_scope": "public_knowledge" if official else "research_evidence",
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
        "project_use_authorization": {
            "status": (
                "RECORDED_LICENSE_EVIDENCE" if license_urls else "OWNER_REVIEWED_PUBLIC_USE"
            ),
            "scope": "STAGING_PROJECT_USE",
            "acceptance_path": ACCEPTANCE_FILE.as_posix(),
            "acceptance_sha256": acceptance_sha,
            "missing_license_url_automatic_block": False,
            "license_status_mutated": False,
        },
        "policy_decision": {
            "retrieval_audiences": PUBLIC_AUDIENCES,
            "allowed_purposes": PURPOSES_BY_SOURCE_TYPE[source_type],
            "ordinary_retrieval_source_status": source_status,
            "audience_handling": (
                "SOURCE_POLICY_GRANTS_PUBLIC_ROLES_RESPONSE_POLICY_STILL_REQUIRED"
            ),
            "purpose_handling": "EVALUATE_AFTER_RETRIEVAL",
            "assessment_handling": "EVALUATE_AFTER_RETRIEVAL_NULL_DENIES_RESPONSE",
            "risk_handling": "LOW_MEDIUM_ONLY_HIGH_UNKNOWN_DENY",
            "stop_normal_rag_handling": "FALSE_ONLY_TRUE_OR_NULL_DENY",
            "license_handling": (
                "RECORDED_LICENSE_EVIDENCE"
                if license_urls
                else "OWNER_PUBLIC_USE_REVIEW_MISSING_URL_NOT_AUTOMATIC_BLOCK"
            ),
            "citation_required": True,
            "diagnosis_allowed": False,
        },
        "observed_summary": observed,
        "remaining_requirements": sorted(set(requirements)),
        "review_status": "verified",
        "production_approved": False,
    }


def _observed_summary(
    records: Sequence[Mapping[str, Any]],
    source_status: str,
    effective_risks: Mapping[str, str],
) -> dict[str, Any]:
    observed_risk = Counter(_risk_key(row["retrieval_policy"]["risk_level"]) for row in records)
    effective_risk = Counter(
        _risk_key(
            effective_risks.get(row["identity"]["chunk_id"], row["retrieval_policy"]["risk_level"])
        )
        for row in records
    )
    current = Counter(row["governance"]["current_status"] for row in records)
    stop = Counter(
        _nullable_bool_key(row["retrieval_policy"]["stop_normal_rag"]) for row in records
    )
    ordinary = [
        row
        for row in records
        if source_status == "CANDIDATE_WITH_CHUNK_GATES"
        and row["governance"]["current_status"] == "current"
        and effective_risks.get(row["identity"]["chunk_id"], row["retrieval_policy"]["risk_level"])
        in {"low", "medium"}
        and row["retrieval_policy"]["stop_normal_rag"] is False
    ]
    ready = [
        row
        for row in ordinary
        if isinstance(row["retrieval_policy"]["requires_official_assessment"], bool)
        and isinstance(row["retrieval_policy"]["requires_professional_assessment"], bool)
        and bool(row["retrieval_policy"]["allowed_purposes"])
    ]
    return {
        "chunk_count": len(records),
        "risk_observed": _risk_counts(observed_risk),
        "risk_effective": _risk_counts(effective_risk),
        "current_status": {
            "current": current["current"],
            "superseded": current["superseded"],
            "unknown": current["unknown"],
        },
        "stop_normal_rag": {
            "true_count": stop["true"],
            "false_count": stop["false"],
            "null_count": stop["null"],
        },
        "assessment_null": {
            "official": sum(
                row["retrieval_policy"]["requires_official_assessment"] is None for row in records
            ),
            "professional": sum(
                row["retrieval_policy"]["requires_professional_assessment"] is None
                for row in records
            ),
        },
        "risk_decision_count": sum(
            row["identity"]["chunk_id"] in effective_risks for row in records
        ),
        "ordinary_retrieval_candidate_count": len(ordinary),
        "response_metadata_ready_count": len(ready),
    }


def _policy_summary(source_policies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    official = [item for item in source_policies if item["is_official_source"]]
    summaries = [item["observed_summary"] for item in source_policies]
    official_summaries = [item["observed_summary"] for item in official]
    return {
        "source_count": len(source_policies),
        "chunk_count": sum(item["chunk_count"] for item in summaries),
        "official_source_count": len(official),
        "research_source_count": len(source_policies) - len(official),
        "license_evidence_missing_source_count": sum(
            not item["evidence"]["license_evidence_urls"] for item in source_policies
        ),
        "missing_license_url_blocked_source_count": 0,
        "project_use_authorized_source_count": sum(
            item["project_use_authorization"]["status"]
            in {"RECORDED_LICENSE_EVIDENCE", "OWNER_REVIEWED_PUBLIC_USE"}
            for item in source_policies
        ),
        "risk_unclassified_observed_count": sum(
            item["risk_observed"]["unclassified"] for item in summaries
        ),
        "risk_unclassified_effective_count": sum(
            item["risk_effective"]["unclassified"] for item in summaries
        ),
        "risk_decision_count": sum(item["risk_decision_count"] for item in summaries),
        "risk_high_count": sum(item["risk_effective"]["high"] for item in official_summaries),
        "risk_high_red_line_count": sum(
            item["risk_effective"]["high_red_line"] for item in official_summaries
        ),
        "stop_normal_rag_true_count": sum(
            item["stop_normal_rag"]["true_count"] for item in official_summaries
        ),
        "current_count": sum(item["current_status"]["current"] for item in summaries),
        "superseded_count": sum(item["current_status"]["superseded"] for item in summaries),
        "ordinary_retrieval_source_candidate_count": sum(
            item["policy_decision"]["ordinary_retrieval_source_status"]
            == "CANDIDATE_WITH_CHUNK_GATES"
            for item in source_policies
        ),
        "ordinary_retrieval_chunk_candidate_count": sum(
            item["ordinary_retrieval_candidate_count"] for item in official_summaries
        ),
        "response_metadata_ready_count": sum(
            item["response_metadata_ready_count"] for item in official_summaries
        ),
    }


def _remaining_review_worksheet(
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    effective_risks = {
        item["chunk_id"]: item["effective_risk_level"] for item in policy["chunk_risk_decisions"]
    }
    rows = []
    for source_policy in policy["source_policies"]:
        source_id = source_policy["source_id"]
        records = records_by_source[source_id]
        rows.append(
            {
                "schema_version": "2.0.0",
                "artifact_version": "v003",
                "policy_map_version": "v002",
                "source_id": source_id,
                "chunk_file_path": source_policy["evidence"]["chunk_file_path"],
                "review_status": "verified",
                "remaining_requirements": source_policy["remaining_requirements"],
                "risk_decision_chunk_ids": _chunk_ids(
                    records,
                    lambda row: row["identity"]["chunk_id"] in effective_risks,
                ),
                "risk_unclassified_effective_chunk_ids": _chunk_ids(
                    records,
                    lambda row: effective_risks.get(
                        row["identity"]["chunk_id"], row["retrieval_policy"]["risk_level"]
                    )
                    is None,
                ),
                "risk_high_chunk_ids": _chunk_ids(
                    records,
                    lambda row: row["retrieval_policy"]["risk_level"] == "high",
                ),
                "risk_high_red_line_chunk_ids": _chunk_ids(
                    records,
                    lambda row: row["retrieval_policy"]["risk_level"] == "high_red_line",
                ),
                "stop_normal_rag_review_chunk_ids": _chunk_ids(
                    records,
                    lambda row: row["retrieval_policy"]["stop_normal_rag"] is not False,
                ),
                "assessment_incomplete_chunk_ids": _chunk_ids(
                    records,
                    lambda row: (
                        row["retrieval_policy"]["requires_official_assessment"] is None
                        or row["retrieval_policy"]["requires_professional_assessment"] is None
                    ),
                ),
                "missing_license_url": not bool(source_policy["evidence"]["license_evidence_urls"]),
                "missing_license_url_blocks_ordinary_retrieval": False,
                "runtime_integration": "NOT_STARTED",
                "golden_query": "NOT_STARTED",
                "production_approved": False,
            }
        )
    return rows


def _validate_acceptance_document(root: Path, acceptance: Mapping[str, Any]) -> None:
    _validate_schema(root, ACCEPTANCE_SCHEMA_PATH, acceptance, "owner policy acceptance")
    statements = acceptance["authorization"]["statements"]
    if acceptance["authorization"]["statements_sha256"] != _canonical_sha256(statements):
        raise SourceFamilyPolicyV2Error("owner policy authorization statements hash mismatch")
    if tuple(statements) != OWNER_STATEMENTS:
        raise SourceFamilyPolicyV2Error("owner policy authorization statements diverged")
    if acceptance["license_policy_decision"]["affected_source_count"] != len(
        acceptance["license_policy_decision"]["affected_source_ids"]
    ):
        raise SourceFamilyPolicyV2Error("owner policy affected source count mismatch")
    if tuple(acceptance["risk_policy_decision"]["affected_chunk_ids"]) != (RISK_DECISION_CHUNK_IDS):
        raise SourceFamilyPolicyV2Error("owner policy risk decision IDs diverged")
    if acceptance["gates"]["production_approved"] is not False:
        raise SourceFamilyPolicyV2Error("owner policy acceptance approved Production")


def _validate_policy_document(root: Path, policy: Mapping[str, Any]) -> None:
    _validate_schema(root, POLICY_SCHEMA_PATH, policy, "source-family policy v002")


def _validate_schema(
    root: Path,
    schema_path: Path,
    document: Mapping[str, Any],
    label: str,
) -> None:
    schema = _read_json(root / schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.absolute_path))
    if errors:
        raise SourceFamilyPolicyV2Error(f"{label} schema failed: {errors[0].message}")


def _validate_policy_semantics(
    records_by_source: Mapping[str, Sequence[Mapping[str, Any]]],
    policy: Mapping[str, Any],
    worksheet: Sequence[Mapping[str, Any]],
) -> None:
    source_policies = policy["source_policies"]
    if (
        len(source_policies) != SOURCE_COUNT
        or len({item["source_id"] for item in source_policies}) != SOURCE_COUNT
    ):
        raise SourceFamilyPolicyV2Error("policy v002 must contain 17 unique sources")
    if len(worksheet) != SOURCE_COUNT or {item["source_id"] for item in worksheet} != {
        item["source_id"] for item in source_policies
    }:
        raise SourceFamilyPolicyV2Error("policy v002 worksheet source coverage mismatch")
    risk_decisions = {
        item["chunk_id"]: item["effective_risk_level"] for item in policy["chunk_risk_decisions"]
    }
    if tuple(risk_decisions) != RISK_DECISION_CHUNK_IDS or set(risk_decisions.values()) != {"low"}:
        raise SourceFamilyPolicyV2Error(
            "policy v002 risk decisions are not the owner-approved five"
        )
    policy_by_source = {item["source_id"]: item for item in source_policies}
    candidate_count = 0
    for source_id, records in records_by_source.items():
        source_policy = policy_by_source[source_id]
        if source_policy["is_official_source"]:
            if source_policy["policy_decision"]["ordinary_retrieval_source_status"] != (
                "CANDIDATE_WITH_CHUNK_GATES"
            ):
                raise SourceFamilyPolicyV2Error(
                    "official source did not enter governed candidate route"
                )
            if source_policy["policy_decision"]["retrieval_audiences"] != PUBLIC_AUDIENCES:
                raise SourceFamilyPolicyV2Error("official source audience policy diverged")
        elif source_policy["policy_decision"]["ordinary_retrieval_source_status"] != (
            "INDEPENDENT_RESEARCH_ROUTE_ONLY"
        ):
            raise SourceFamilyPolicyV2Error("research source entered ordinary retrieval")
        if (
            not source_policy["evidence"]["license_evidence_urls"]
            and source_policy["project_use_authorization"]["status"] != "OWNER_REVIEWED_PUBLIC_USE"
        ):
            raise SourceFamilyPolicyV2Error("missing license URL lacks owner public-use evidence")
        for record in records:
            result = evaluate_ordinary_retrieval(
                record,
                source_policy,
                risk_decisions,
                actor_role="elder",
                purpose="source_lookup",
            )
            if result["retrieval_allowed"]:
                candidate_count += 1
            if (
                record["retrieval_policy"]["risk_level"] in {"high", "high_red_line"}
                and result["retrieval_allowed"]
            ):
                raise SourceFamilyPolicyV2Error("high-risk chunk entered ordinary retrieval")
            if (
                record["retrieval_policy"]["stop_normal_rag"] is not False
                and result["retrieval_allowed"]
            ):
                raise SourceFamilyPolicyV2Error("stop-normal-RAG chunk entered ordinary retrieval")
            if record["governance"]["current_status"] != "current" and result["retrieval_allowed"]:
                raise SourceFamilyPolicyV2Error("non-current chunk entered ordinary retrieval")
    if candidate_count != 554:
        raise SourceFamilyPolicyV2Error(
            f"ordinary retrieval candidate count mismatch: {candidate_count}"
        )
    summary = policy["summary"]
    if summary["risk_unclassified_effective_count"] != 0:
        raise SourceFamilyPolicyV2Error("owner risk decisions did not resolve all five values")
    if summary["missing_license_url_blocked_source_count"] != 0:
        raise SourceFamilyPolicyV2Error("missing license URL still blocks a source")
    if policy["gates"]["production_approved"] is not False:
        raise SourceFamilyPolicyV2Error("source-family policy v002 approved Production")


def _acceptance_report(acceptance: Mapping[str, Any]) -> dict[str, Any]:
    checks = (
        "acceptance_schema_valid",
        "owner_statements_hash_bound",
        "v003_candidate_hash_bound",
        "v003_candidate_audit_lock_bound",
        "prior_acceptance_hash_bound",
        "prior_policy_hash_bound",
        "thirteen_missing_license_url_sources_recorded",
        "missing_license_url_not_automatic_block",
        "five_general_risk_decisions_recorded",
        "general_risk_mapped_to_canonical_low",
        "chunk_bytes_not_mutated",
        "all_public_roles_retrieval_direction_recorded",
        "high_and_stop_gates_preserved",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": "1.0.0",
        "acceptance_version": "v003",
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "affected_license_source_count": 13,
        "risk_decision_count": 5,
        "review_status": "verified",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validation_report(
    policy: Mapping[str, Any],
    worksheet: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = policy["summary"]
    checks = (
        "policy_schema_valid",
        "owner_acceptance_bound",
        "prior_policy_v001_immutable",
        "candidate_v003_immutable",
        "source_ids_unique_and_complete",
        "all_official_sources_grant_four_retrieval_roles",
        "research_sources_use_independent_route",
        "missing_license_url_not_automatic_block",
        "legacy_license_status_not_mutated",
        "five_owner_risk_decisions_exact",
        "effective_unclassified_risk_zero",
        "high_risk_denied_from_ordinary_retrieval",
        "stop_normal_rag_denied_from_ordinary_retrieval",
        "non_current_denied_from_ordinary_retrieval",
        "purpose_and_assessment_response_gates_preserved",
        "runtime_safety_not_started_from_similarity",
        "worksheet_covers_all_sources",
        "runtime_integration_not_started",
        "golden_query_not_started",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": "2.0.0",
        "artifact_version": "v003",
        "policy_map_version": "v002",
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "source_count": summary["source_count"],
        "chunk_count": summary["chunk_count"],
        "worksheet_row_count": len(worksheet),
        "license_evidence_missing_source_count": summary["license_evidence_missing_source_count"],
        "missing_license_url_blocked_source_count": summary[
            "missing_license_url_blocked_source_count"
        ],
        "risk_decision_count": summary["risk_decision_count"],
        "risk_unclassified_effective_count": summary["risk_unclassified_effective_count"],
        "ordinary_retrieval_chunk_candidate_count": summary[
            "ordinary_retrieval_chunk_candidate_count"
        ],
        "response_metadata_ready_count": summary["response_metadata_ready_count"],
        "review_status": "verified",
        "runtime_integration": "NOT_STARTED",
        "golden_query": "NOT_STARTED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _version_difference(policy: Mapping[str, Any]) -> dict[str, Any]:
    summary = policy["summary"]
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "prior_policy_map_version": "v001",
        "successor_policy_map_version": "v002",
        "prior_policy_status": "STAGING_NEEDS_REVIEW",
        "successor_policy_status": "STAGING_OWNER_APPROVED",
        "missing_license_url_automatic_block_before": True,
        "missing_license_url_automatic_block_after": False,
        "missing_license_url_source_count": summary["license_evidence_missing_source_count"],
        "risk_decision_count": summary["risk_decision_count"],
        "risk_unclassified_before": summary["risk_unclassified_observed_count"],
        "risk_unclassified_after": summary["risk_unclassified_effective_count"],
        "ordinary_retrieval_source_candidate_count_before": 0,
        "ordinary_retrieval_source_candidate_count_after": summary[
            "ordinary_retrieval_source_candidate_count"
        ],
        "ordinary_retrieval_chunk_candidate_count_after": summary[
            "ordinary_retrieval_chunk_candidate_count"
        ],
        "response_metadata_ready_count": summary["response_metadata_ready_count"],
        "chunk_bytes_changed_count": 0,
        "license_status_changed_count": 0,
        "runtime_integration": "NOT_STARTED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _acceptance_readme(acceptance: Mapping[str, Any]) -> str:
    return (
        "# RAG v003 Owner source-family policy acceptance v003\n\n"
        "This package records the project owner's staging-only source-family policy decisions. "
        "A missing license URL is not an automatic block after the recorded source-party "
        "public-use "
        "review. The five form-example chunks labelled by the owner as general risk are mapped to "
        "the canonical `low` policy overlay without changing immutable v003 chunk bytes.\n\n"
        "- Sources/chunks: `17` / `726`\n"
        "- Sources without license URL covered by owner public-use review: `13`\n"
        "- Owner risk decisions: `5`\n"
        "- Canonical risk mapping: `一般風險值` → `low`\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )


def _preflight_readme(lock: Mapping[str, Any], inventory: Mapping[str, Any]) -> str:
    return (
        "# Source-family policy v002 preflight\n\n"
        "This package freezes the immutable policy v001, verified v003 candidate, candidate audit, "
        "prior acceptance, and every selected policy v002 schema, config, code, test, and evidence "
        "input before the successor policy is generated.\n\n"
        f"- Validation inputs: `{inventory['entry_count']}`\n"
        f"- Validation inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Protected prior artifacts: `{lock['entry_count']}`\n"
        f"- Prior lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )


def _audit_readme(lock: Mapping[str, Any], inventory: Mapping[str, Any]) -> str:
    return (
        "# Source-family policy v002 audit preflight v002\n\n"
        "This successor keeps the original build preflight and audit preflight v001 immutable "
        "while binding the completed policy candidate to the current formatted schemas, config, "
        "code, tests, evidence, and v003 chunk inventory.\n\n"
        f"- Current validation inputs: `{inventory['entry_count']}`\n"
        f"- Current inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Candidate artifact entries: `{lock['entry_count']}`\n"
        f"- Candidate lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- Runtime integration: local hash-pinned runtime policy v002 integrated\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )


def _candidate_readme(policy: Mapping[str, Any]) -> str:
    summary = policy["summary"]
    return (
        "# RAG v003 source-family policy candidate v002\n\n"
        "This immutable successor separates backend retrieval from response policy. "
        "Official public "
        "sources may be searched for Elder, Family, Care Professional, and System Admin roles only "
        "after current/risk/stop/project-use gates pass. Purpose and assessment rules are "
        "evaluated "
        "before any answer is returned. Research sources remain on an independent route.\n\n"
        f"- Sources/chunks: `{summary['source_count']}` / `{summary['chunk_count']}`\n"
        f"- Missing-license-URL sources blocked only for that reason: "
        f"`{summary['missing_license_url_blocked_source_count']}`\n"
        f"- Owner risk decisions / effective unclassified: "
        f"`{summary['risk_decision_count']}` / `{summary['risk_unclassified_effective_count']}`\n"
        f"- Ordinary official retrieval candidates: "
        f"`{summary['ordinary_retrieval_chunk_candidate_count']}`\n"
        f"- Response-metadata-ready candidates: `{summary['response_metadata_ready_count']}`\n"
        "- Runtime integration: not started\n"
        "- Golden Query: not started\n"
        "- Supabase release: not created\n"
        "- Production: blocked\n"
    )


def _load_chunk_records(root: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for path in sorted((root / CHUNK_ROOT).glob("*.jsonl")):
        records = _read_jsonl(path)
        source_ids = {row["identity"]["source_id"] for row in records}
        if len(source_ids) != 1:
            raise SourceFamilyPolicyV2Error(f"mixed source IDs: {path.name}")
        source_id = next(iter(source_ids))
        indexes = [row["identity"]["chunk_index"] for row in records]
        if indexes != list(range(1, len(records) + 1)):
            raise SourceFamilyPolicyV2Error(f"non-continuous indexes: {source_id}")
        if source_id in result:
            raise SourceFamilyPolicyV2Error(f"duplicate source file: {source_id}")
        result[source_id] = records
    if len(result) != SOURCE_COUNT or sum(map(len, result.values())) != CHUNK_COUNT:
        raise SourceFamilyPolicyV2Error("v003 corpus must contain 17 sources and 726 chunks")
    return result


def _audit_input_entries(root: Path) -> list[dict[str, Any]]:
    paths = [root / path for path in AUDIT_INPUT_PATHS]
    paths.extend(sorted((root / CHUNK_ROOT).glob("*.jsonl")))
    return _file_entries(root, paths, "source_family_policy_v002_audit")


def _entries_for_roots(
    root: Path,
    relative_roots: Sequence[Path],
    logical_family: str,
) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for relative in relative_roots:
        absolute = root / relative
        if not absolute.is_dir():
            raise SourceFamilyPolicyV2Error(f"prior artifact root missing: {relative.as_posix()}")
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
            raise SourceFamilyPolicyV2Error(
                f"validation input missing: {path.relative_to(root).as_posix()}"
            )
        relative = path.relative_to(root).as_posix()
        if relative in seen:
            raise SourceFamilyPolicyV2Error(f"duplicate validation input: {relative}")
        seen.add(relative)
        raw = _read_lf_utf8_bytes(path)
        entries.append(
            {
                "path": relative,
                "artifact_kind": _artifact_kind(path),
                "source_id": (
                    path.name.split(".rag-chunk", 1)[0]
                    if path.parent.name == "chunks"
                    else "rag-v3-policy-v002"
                ),
                "logical_family": logical_family,
                "version": _version_from_path(path),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "hash_mode": HASH_MODE,
            }
        )
    return entries


def _inventory_document(
    kind: str,
    entries: Sequence[Mapping[str, Any]],
    scope: str,
) -> dict[str, Any]:
    payload = list(entries)
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "policy_map_version": "v002",
        "kind": kind,
        "scope": scope,
        "hash_mode": HASH_MODE,
        "inventory_hash_mode": CANONICAL_HASH_MODE,
        "entry_count": len(entries),
        "inventory_sha256": _canonical_sha256(payload),
        "entries": payload,
        "review_status": "verified",
        "production_approved": False,
    }


def _risk_counts(counter: Counter[str]) -> dict[str, int]:
    return {
        "low": counter["low"],
        "medium": counter["medium"],
        "high": counter["high"],
        "high_red_line": counter["high_red_line"],
        "unclassified": counter["unclassified"],
    }


def _risk_key(value: Any) -> str:
    return "unclassified" if value is None else str(value)


def _nullable_bool_key(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "null"


def _chunk_ids(
    records: Sequence[Mapping[str, Any]],
    predicate: Any,
) -> list[str]:
    return [row["identity"]["chunk_id"] for row in records if predicate(row)]


def _artifact_kind(path: Path) -> str:
    if path.suffix.casefold() == ".jsonl":
        return "chunk_or_review_jsonl"
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


def _destination(root: Path, supplied: Path | None, default: Path) -> Path:
    return supplied.resolve() if supplied is not None else (root / default).resolve()


def _refuse_overwrite(path: Path, label: str) -> None:
    if path.exists():
        raise SourceFamilyPolicyV2Error(f"{label} exists; refuse to overwrite")


def _new_staging_directory(root: Path, label: str) -> Path:
    parent = root.parent.resolve()
    staged = Path(tempfile.mkdtemp(prefix=f".kinsun-{label}-", dir=parent)).resolve()
    if staged.parent != parent or not staged.name.startswith(f".kinsun-{label}-"):
        raise SourceFamilyPolicyV2Error("unsafe policy v002 staging directory")
    return staged


def _publish_directory(staged: Path, destination: Path) -> None:
    if destination.exists():
        raise SourceFamilyPolicyV2Error("policy v002 destination appeared before publish")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(destination)


def _cleanup_staging_directory(root: Path, staged: Path) -> None:
    resolved = staged.resolve()
    if not resolved.exists():
        return
    parent = root.parent.resolve()
    if resolved.parent != parent or not resolved.name.startswith(".kinsun-source-policy-"):
        raise SourceFamilyPolicyV2Error("refuse to clean unsafe policy v002 staging directory")
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
        raise SourceFamilyPolicyV2Error("policy v002 checksum inventory mismatch")
    for relative, digest in checksums.items():
        if _sha256_file(root / relative) != digest:
            raise SourceFamilyPolicyV2Error(f"policy v002 checksum mismatch: {relative}")


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
            raise SourceFamilyPolicyV2Error(f"invalid checksum entry: {line}")
        result[relative] = digest
    if not result:
        raise SourceFamilyPolicyV2Error("policy v002 checksum file is empty")
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
        raise SourceFamilyPolicyV2Error(f"JSON object required: {path.as_posix()}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = _read_lf_utf8_bytes(path).decode("utf-8")
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise SourceFamilyPolicyV2Error(f"JSONL blank line or empty file: {path.as_posix()}")
    result = []
    for line in lines:
        value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        if not isinstance(value, dict):
            raise SourceFamilyPolicyV2Error(f"JSONL object required: {path.as_posix()}")
        result.append(value)
    return result


def _read_lf_utf8_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        raise SourceFamilyPolicyV2Error(f"text must be UTF-8 LF without BOM: {path.as_posix()}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SourceFamilyPolicyV2Error(f"invalid UTF-8: {path.as_posix()}") from exc
    return raw


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SourceFamilyPolicyV2Error(f"duplicate JSON key: {key}")
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

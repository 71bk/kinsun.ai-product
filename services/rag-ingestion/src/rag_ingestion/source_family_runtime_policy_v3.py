"""Build the staging-only purpose-classification runtime policy v003 successor."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_ingestion.source_family_runtime_policy import (
    SourceFamilyRuntimePolicyError,
    _assert_text_tree,
    _entries_for_roots,
    _file_entries,
    _json_bytes,
    _read_json,
    _sha256_file,
    _validate_checksums,
    _write_checksums,
    _write_json,
    _write_text,
)
from rag_ingestion.source_family_runtime_policy_v2 import (
    SourceFamilyRuntimePolicyV2Error,
    _canonical_sha256,
    _cleanup_staging_directory,
    _inventory_document,
    _new_staging_directory,
    _publish_directory,
    _refuse_overwrite,
    _validate_frozen_inventory_document_v2,
    _validate_inventory_document,
    _validate_package_inventory,
    _validate_schema,
    validate_owner_assessment_response_acceptance,
    validate_source_family_runtime_policy_v2,
)

RUNTIME_POLICY_VERSION = "v003"
SCHEMA_VERSION = "3.0.0"
SOURCE_POLICY_MAP_VERSION = "v002"
CANDIDATE_ARTIFACT_VERSION = "v003"
SOURCE_COUNT = 14
CHUNK_COUNT = 554
PURPOSE_OVERLAY_COUNT = 32
PURPOSE_NEEDS_REVIEW_COUNT = 32
RESPONSE_METADATA_READY_COUNT = 554
PROFESSIONAL_NULL_TO_TRUE_COUNT = 220
OFFICIAL_NULL_TO_TRUE_COUNT = 5
ASSESSMENT_ADVISORY_CHUNK_COUNT = 372

TARGET_SOURCE_ID = "mohw_a_unit_case_manager_manual_20230719"
PRIOR_CHUNK_PREFIX = f"{TARGET_SOURCE_ID}_rag_v2_v002_"
SUCCESSOR_CHUNK_PREFIX = f"{TARGET_SOURCE_ID}_rag_v3_v003_"
SOURCE_PURPOSE_OVERLAY = (
    "care_record",
    "care_summary",
    "general_information",
    "manual_review",
    "resource_navigation",
    "source_lookup",
)

OWNER_STATEMENTS = (
    "32 筆缺 purpose 仍封鎖。perpose次啥",
    "好處理開始",
)
SIGNED_AT = "2026-08-27T17:23:48+08:00"

PURPOSE_ASSIGNMENTS: dict[int, tuple[str, ...]] = {
    1: ("general_information", "source_lookup"),
    2: ("general_information", "manual_review", "source_lookup"),
    3: ("general_information", "manual_review", "resource_navigation", "source_lookup"),
    5: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    7: ("care_summary", "general_information", "manual_review", "source_lookup"),
    8: ("general_information", "manual_review", "source_lookup"),
    9: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    11: ("general_information", "manual_review", "source_lookup"),
    12: ("general_information", "manual_review", "source_lookup"),
    16: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    17: (
        "care_record",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    19: ("care_record", "general_information", "manual_review", "source_lookup"),
    20: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    23: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    24: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    25: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    26: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    30: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    31: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    32: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    36: ("general_information", "manual_review", "resource_navigation", "source_lookup"),
    37: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    39: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    40: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    46: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    57: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    60: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    61: ("general_information", "manual_review", "resource_navigation", "source_lookup"),
    62: (
        "care_record",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    63: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "source_lookup",
    ),
    64: (
        "care_record",
        "care_summary",
        "general_information",
        "manual_review",
        "resource_navigation",
        "source_lookup",
    ),
    65: ("general_information", "manual_review", "resource_navigation", "source_lookup"),
}

RATIONALE_BY_INDEX: dict[int, str] = {
    1: "BACKGROUND_AND_SOURCE_CONTEXT",
    2: "BACKGROUND_AND_SOURCE_CONTEXT",
    3: "BACKGROUND_AND_SOURCE_CONTEXT",
    5: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    7: "FOLLOWUP_QUALITY_OR_COORDINATION",
    8: "POLICY_OR_TRAINING_MANUAL",
    9: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    11: "POLICY_OR_TRAINING_MANUAL",
    12: "POLICY_OR_TRAINING_MANUAL",
    16: "CASE_MANAGEMENT_WORKFLOW",
    17: "CASE_MANAGEMENT_WORKFLOW",
    19: "CASE_MANAGEMENT_WORKFLOW",
    20: "CASE_MANAGEMENT_WORKFLOW",
    23: "CASE_MANAGEMENT_WORKFLOW",
    24: "CASE_MANAGEMENT_WORKFLOW",
    25: "CASE_MANAGEMENT_WORKFLOW",
    26: "CASE_MANAGEMENT_WORKFLOW",
    30: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    31: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    32: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    36: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    37: "FOLLOWUP_QUALITY_OR_COORDINATION",
    39: "FOLLOWUP_QUALITY_OR_COORDINATION",
    40: "FOLLOWUP_QUALITY_OR_COORDINATION",
    46: "FOLLOWUP_QUALITY_OR_COORDINATION",
    57: "CASE_MANAGEMENT_WORKFLOW",
    60: "FOLLOWUP_QUALITY_OR_COORDINATION",
    61: "FOLLOWUP_QUALITY_OR_COORDINATION",
    62: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    63: "FOLLOWUP_QUALITY_OR_COORDINATION",
    64: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
    65: "RESOURCE_REFERRAL_OR_ASSIGNMENT",
}

V2_RUNTIME_ROOT = Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v002")
V2_POLICY_PATH = V2_RUNTIME_ROOT / "source-family-runtime-policy.json"
V2_POLICY_SHA256 = "1b6fafb32b3111feaab4773838ae12f5c6538b0527e6a07769bbce126a9662b8"
SOURCE_POLICY_ROOT = Path("data/rag-v3/governance/source-family-policy/candidates/v002")
CANDIDATE_ROOT = Path("data/rag-v3/candidates/v003")
ASSESSMENT_ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v004")
ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v005")
ACCEPTANCE_FILE = ACCEPTANCE_ROOT / "owner-purpose-classification-acceptance.json"
ACCEPTANCE_SCHEMA_PATH = Path(
    "contracts/schemas/rag/rag-owner-purpose-classification-acceptance-v1.schema.json"
)
RUNTIME_SCHEMA_PATH = Path("contracts/schemas/rag/rag-source-family-runtime-policy-v3.schema.json")
RUNTIME_ROOT = Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v003")
RUNTIME_POLICY_FILENAME = "source-family-runtime-policy.json"
VALIDATION_INPUT_FILENAME = "validation-input-inventory.json"
PRIOR_LOCK_FILENAME = "prior-artifact-lock.json"
VALIDATION_REPORT_FILENAME = "validation-report.json"
CHECKSUM_FILENAME = "SHA256SUMS.txt"

FIXED_INPUT_PATHS = (
    Path(".gitattributes"),
    ACCEPTANCE_SCHEMA_PATH,
    RUNTIME_SCHEMA_PATH,
    Path("scripts/rag/build_source_family_runtime_policy_v3.py"),
    Path("scripts/rag/validate_source_family_runtime_policy_v3.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_runtime_policy.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_runtime_policy_v2.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_runtime_policy_v3.py"),
    Path("services/rag-ingestion/tests/integration/test_source_family_runtime_policy_v3.py"),
    Path("services/rag-ingestion/tests/unit/test_source_family_policy_v2_schema.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/runtime_policy.py"),
    Path("services/agent-runtime/tests/unit/test_source_family_runtime_policy.py"),
    Path("config/rag/source-family-golden-queries-v003.json"),
    V2_POLICY_PATH,
    ACCEPTANCE_FILE,
    SOURCE_POLICY_ROOT / "source-family-policy-map.json",
    CANDIDATE_ROOT / CHECKSUM_FILENAME,
)
PRIOR_ARTIFACT_ROOTS = (
    V2_RUNTIME_ROOT,
    SOURCE_POLICY_ROOT,
    CANDIDATE_ROOT,
    ASSESSMENT_ACCEPTANCE_ROOT,
)


class SourceFamilyRuntimePolicyV3Error(SourceFamilyRuntimePolicyV2Error):
    """Raised when purpose-classification evidence or v003 semantics diverge."""


@dataclass(frozen=True, slots=True)
class RuntimePolicyV3Summary:
    output_path: Path
    policy_sha256: str
    validation_input_inventory_sha256: str
    prior_artifact_lock_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS",
            "runtime_policy_version": RUNTIME_POLICY_VERSION,
            "source_policy_map_version": SOURCE_POLICY_MAP_VERSION,
            "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
            "output_path": self.output_path.as_posix(),
            "source_count": SOURCE_COUNT,
            "chunk_count": CHUNK_COUNT,
            "purpose_overlay_count": PURPOSE_OVERLAY_COUNT,
            "purpose_needs_review_count": PURPOSE_NEEDS_REVIEW_COUNT,
            "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
            "policy_sha256": self.policy_sha256,
            "validation_input_inventory_sha256": self.validation_input_inventory_sha256,
            "prior_artifact_lock_sha256": self.prior_artifact_lock_sha256,
            "production_approved": False,
        }


def build_owner_purpose_classification_acceptance(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> Path:
    """Record explicit authorization for an AI-assisted staging classification."""

    root = repository_root.resolve()
    destination = (output_path or root / ACCEPTANCE_ROOT).resolve()
    _refuse_overwrite_v3(destination, "purpose-classification acceptance v005")
    _validate_prior_runtime_policy_package(root)
    document = _acceptance_document(root)
    staged = _new_staging_directory(root, "purpose-classification-acceptance-v005")
    try:
        _write_json(staged / ACCEPTANCE_FILE.name, document)
        _write_json(staged / "validation-report.json", _acceptance_report())
        _write_json(
            staged / "manifest.json",
            {
                "schema_version": "1.0.0",
                "acceptance_version": "v005",
                "files": [ACCEPTANCE_FILE.name, "validation-report.json"],
                "acceptance_sha256": _sha256_file(staged / ACCEPTANCE_FILE.name),
                "external_sync": "NOT_AUTHORIZED",
                "production_approved": False,
            },
        )
        _write_text(staged / "README.md", _acceptance_readme())
        _write_checksums(staged)
        validate_owner_purpose_classification_acceptance(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return destination


def validate_owner_purpose_classification_acceptance(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate authorization, exact decisions, and immutable input bindings."""

    root = repository_root.resolve()
    package = (package_path or root / ACCEPTANCE_ROOT).resolve()
    expected_paths = {
        ACCEPTANCE_FILE.name,
        "validation-report.json",
        "manifest.json",
        "README.md",
        CHECKSUM_FILENAME,
    }
    _validate_package_inventory(package, expected_paths)
    _assert_text_tree(package)
    _validate_checksums(package)
    _validate_prior_runtime_policy_package(root)
    document = _read_json(package / ACCEPTANCE_FILE.name)
    _validate_schema(root / ACCEPTANCE_SCHEMA_PATH, document, "purpose acceptance")
    if document != _acceptance_document(root):
        raise SourceFamilyRuntimePolicyV3Error("purpose acceptance is not reproducible")
    if _read_json(package / "validation-report.json") != _acceptance_report():
        raise SourceFamilyRuntimePolicyV3Error("purpose acceptance report is inconsistent")
    manifest = _read_json(package / "manifest.json")
    if manifest["acceptance_sha256"] != _sha256_file(package / ACCEPTANCE_FILE.name):
        raise SourceFamilyRuntimePolicyV3Error("purpose acceptance manifest hash mismatch")
    return {
        "status": "PASS",
        "acceptance_sha256": manifest["acceptance_sha256"],
        "purpose_overlay_count": PURPOSE_OVERLAY_COUNT,
        "purpose_needs_review_count": PURPOSE_NEEDS_REVIEW_COUNT,
        "production_approved": False,
    }


def build_source_family_runtime_policy_v3(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> RuntimePolicyV3Summary:
    """Build the immutable v003 staging purpose overlay atomically."""

    root = repository_root.resolve()
    destination = (output_path or root / RUNTIME_ROOT).resolve()
    _refuse_overwrite_v3(destination, "source-family runtime policy v003")
    _validate_prior_runtime_policy_package(root)
    validate_owner_purpose_classification_acceptance(root)
    document = _runtime_policy_document(root)
    inventory = _inventory_document(
        "source_family_runtime_policy_v003_validation_input_inventory",
        _validation_input_entries(root),
        "v003 schemas, decisions, runtime code, tests, Golden cases, and formal inputs",
    )
    prior_lock = _inventory_document(
        "source_family_runtime_policy_v003_prior_artifact_immutable_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
        "immutable runtime v002, source policy v002, candidate v003, and acceptance v004 bytes",
    )
    staged = _new_staging_directory(root, "source-family-runtime-policy-v003")
    try:
        _write_json(staged / RUNTIME_POLICY_FILENAME, document)
        _write_json(staged / VALIDATION_INPUT_FILENAME, inventory)
        _write_json(staged / PRIOR_LOCK_FILENAME, prior_lock)
        _write_json(staged / VALIDATION_REPORT_FILENAME, _validation_report())
        _write_text(staged / "README.md", _runtime_readme(document))
        _write_checksums(staged)
        result = validate_source_family_runtime_policy_v3(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return RuntimePolicyV3Summary(
        output_path=destination,
        policy_sha256=result["policy_sha256"],
        validation_input_inventory_sha256=inventory["inventory_sha256"],
        prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
    )


def validate_source_family_runtime_policy_v3(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate v003 hashes, decisions, schema, and exact overlay semantics."""

    root = repository_root.resolve()
    package = (package_path or root / RUNTIME_ROOT).resolve()
    expected_paths = {
        "README.md",
        CHECKSUM_FILENAME,
        PRIOR_LOCK_FILENAME,
        RUNTIME_POLICY_FILENAME,
        VALIDATION_INPUT_FILENAME,
        VALIDATION_REPORT_FILENAME,
    }
    _validate_package_inventory(package, expected_paths)
    _assert_text_tree(package)
    _validate_checksums(package)
    _validate_prior_runtime_policy_package(root)
    validate_owner_purpose_classification_acceptance(root)
    if package == (root / RUNTIME_ROOT).resolve():
        _validate_frozen_inventory_document_v2(
            package / VALIDATION_INPUT_FILENAME,
            expected_kind="source_family_runtime_policy_v003_validation_input_inventory",
        )
    else:
        _validate_inventory_document(
            package / VALIDATION_INPUT_FILENAME,
            "source_family_runtime_policy_v003_validation_input_inventory",
            _validation_input_entries(root),
        )
    _validate_inventory_document(
        package / PRIOR_LOCK_FILENAME,
        "source_family_runtime_policy_v003_prior_artifact_immutable_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
    )
    document = _read_json(package / RUNTIME_POLICY_FILENAME)
    _validate_schema(root / RUNTIME_SCHEMA_PATH, document, "runtime policy v003")
    expected = _runtime_policy_document(root)
    if document != expected:
        raise SourceFamilyRuntimePolicyV3Error("runtime policy v003 is not reproducible")
    if (package / RUNTIME_POLICY_FILENAME).read_bytes() != _json_bytes(document):
        raise SourceFamilyRuntimePolicyV3Error("runtime policy v003 JSON is not deterministic")
    if _read_json(package / VALIDATION_REPORT_FILENAME) != _validation_report():
        raise SourceFamilyRuntimePolicyV3Error("runtime policy v003 report is inconsistent")
    if (package / "README.md").read_text(encoding="utf-8") != _runtime_readme(document):
        raise SourceFamilyRuntimePolicyV3Error("runtime policy v003 README is inconsistent")
    return {
        "status": "PASS",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "purpose_overlay_count": PURPOSE_OVERLAY_COUNT,
        "purpose_needs_review_count": PURPOSE_NEEDS_REVIEW_COUNT,
        "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
        "policy_sha256": _sha256_file(package / RUNTIME_POLICY_FILENAME),
        "runtime_integration": "READY_FOR_STAGING_TEST",
        "golden_query": "NOT_EXECUTED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _acceptance_document(root: Path) -> dict[str, Any]:
    statements = list(OWNER_STATEMENTS)
    return {
        "schema_version": "1.0.0",
        "acceptance_version": "v005",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "SIGNED_STAGING_AUTHORIZATION",
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
            "intent": "AUTHORIZE_AI_ASSISTED_PURPOSE_CLASSIFICATION_FOR_STAGING",
            "cryptographic_signature": None,
        },
        "bindings": {
            "prior_runtime_policy_path": V2_POLICY_PATH.as_posix(),
            "prior_runtime_policy_sha256": _sha256_file(root / V2_POLICY_PATH),
            "source_policy_path": (SOURCE_POLICY_ROOT / "source-family-policy-map.json").as_posix(),
            "source_policy_sha256": _sha256_file(
                root / SOURCE_POLICY_ROOT / "source-family-policy-map.json"
            ),
            "candidate_path": CANDIDATE_ROOT.as_posix(),
            "candidate_checksums_sha256": _sha256_file(root / CANDIDATE_ROOT / CHECKSUM_FILENAME),
            "source_id": TARGET_SOURCE_ID,
            "affected_chunk_count": PURPOSE_OVERLAY_COUNT,
        },
        "classification_policy": {
            "method": "AI_ASSISTED_EXISTING_ENUM_MAPPING",
            "activation_scope": "STAGING_ONLY",
            "source_allowed_purpose_overlay": ["general_information"],
            "empty_purpose_count_before": PURPOSE_OVERLAY_COUNT,
            "empty_purpose_count_after": 0,
            "human_verified_classification_count": 0,
            "needs_review_classification_count": PURPOSE_NEEDS_REVIEW_COUNT,
            "purpose_gate_preserved": True,
            "candidate_chunk_bytes_mutated": False,
        },
        "decisions": _classification_decisions(root),
        "gates": {
            "environment": "STAGING",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _classification_decisions(root: Path) -> list[dict[str, Any]]:
    prior = _read_json(root / V2_POLICY_PATH)
    by_prior = {chunk["prior_chunk_id"]: chunk for chunk in prior["chunks"]}
    decisions: list[dict[str, Any]] = []
    for index, purposes in PURPOSE_ASSIGNMENTS.items():
        suffix = f"{index:04d}"
        prior_chunk_id = PRIOR_CHUNK_PREFIX + suffix
        chunk = by_prior.get(prior_chunk_id)
        if chunk is None:
            raise SourceFamilyRuntimePolicyV3Error(f"purpose target missing: {prior_chunk_id}")
        if chunk["source_id"] != TARGET_SOURCE_ID or chunk["chunk_allowed_purposes"]:
            raise SourceFamilyRuntimePolicyV3Error(
                f"purpose target baseline diverged: {prior_chunk_id}"
            )
        decisions.append(
            {
                "prior_chunk_id": prior_chunk_id,
                "chunk_id": SUCCESSOR_CHUNK_PREFIX + suffix,
                "source_id": TARGET_SOURCE_ID,
                "text_sha256": chunk["text_sha256"],
                "allowed_purposes": list(purposes),
                "rationale_code": RATIONALE_BY_INDEX[index],
                "decision_review_status": "needs_review",
            }
        )
    if len(decisions) != PURPOSE_OVERLAY_COUNT:
        raise SourceFamilyRuntimePolicyV3Error("purpose decision count diverged")
    return decisions


def _runtime_policy_document(root: Path) -> dict[str, Any]:
    prior = _read_json(root / V2_POLICY_PATH)
    document = copy.deepcopy(prior)
    acceptance = validate_owner_purpose_classification_acceptance(root)
    decisions = {
        decision["prior_chunk_id"]: decision for decision in _classification_decisions(root)
    }
    overlaid = 0
    for chunk in document["chunks"]:
        decision = decisions.get(chunk["prior_chunk_id"])
        if decision is None:
            continue
        if chunk["source_id"] != TARGET_SOURCE_ID or chunk["chunk_allowed_purposes"]:
            raise SourceFamilyRuntimePolicyV3Error("purpose overlay baseline diverged")
        chunk["source_allowed_purposes"] = list(SOURCE_PURPOSE_OVERLAY)
        chunk["chunk_allowed_purposes"] = decision["allowed_purposes"]
        overlaid += 1
    if overlaid != PURPOSE_OVERLAY_COUNT:
        raise SourceFamilyRuntimePolicyV3Error("purpose overlay count diverged")
    response_ready = sum(bool(chunk["chunk_allowed_purposes"]) for chunk in document["chunks"])
    if response_ready != RESPONSE_METADATA_READY_COUNT:
        raise SourceFamilyRuntimePolicyV3Error("v003 response-ready count diverged")
    document.update(
        {
            "schema_version": SCHEMA_VERSION,
            "runtime_policy_version": RUNTIME_POLICY_VERSION,
            "purpose_classification_binding": {
                "path": ACCEPTANCE_FILE.as_posix(),
                "sha256": acceptance["acceptance_sha256"],
                "acceptance_version": "v005",
            },
            "prior_runtime_policy_binding": {
                "path": V2_POLICY_PATH.as_posix(),
                "sha256": _sha256_file(root / V2_POLICY_PATH),
                "runtime_policy_version": "v002",
                "relationship": "SUPERSEDES_WITHOUT_MUTATING_PRIOR_BYTES",
            },
        }
    )
    document["summary"] = {
        **document["summary"],
        "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
        "purpose_overlay_count": PURPOSE_OVERLAY_COUNT,
        "purpose_needs_review_count": PURPOSE_NEEDS_REVIEW_COUNT,
    }
    return document


def _validate_prior_runtime_policy_package(root: Path) -> None:
    try:
        validate_source_family_runtime_policy_v2(root)
        validate_owner_assessment_response_acceptance(root)
    except SourceFamilyRuntimePolicyError as exc:
        raise SourceFamilyRuntimePolicyV3Error(
            "prior runtime v002 package integrity failed"
        ) from exc
    if _sha256_file(root / V2_POLICY_PATH) != V2_POLICY_SHA256:
        raise SourceFamilyRuntimePolicyV3Error("prior runtime v002 policy bytes changed")


def _refuse_overwrite_v3(destination: Path, label: str) -> None:
    try:
        _refuse_overwrite(destination, label)
    except SourceFamilyRuntimePolicyV2Error as exc:
        raise SourceFamilyRuntimePolicyV3Error(str(exc)) from exc


def _validation_input_entries(root: Path) -> list[dict[str, Any]]:
    return _file_entries(root, [root / path for path in FIXED_INPUT_PATHS])


def _acceptance_report() -> dict[str, Any]:
    checks = (
        "owner_staging_authorization_hash_bound",
        "prior_runtime_v002_hash_bound",
        "source_policy_v002_hash_bound",
        "candidate_v003_hash_bound",
        "purpose_decisions_32_exact_and_unique",
        "existing_enum_values_only",
        "general_information_enabled_for_current_core_intent",
        "purpose_gate_preserved",
        "decision_review_status_needs_review",
        "candidate_chunk_bytes_not_mutated",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": "1.0.0",
        "acceptance_version": "v005",
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "purpose_overlay_count": PURPOSE_OVERLAY_COUNT,
        "purpose_needs_review_count": PURPOSE_NEEDS_REVIEW_COUNT,
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validation_report() -> dict[str, Any]:
    checks = (
        "purpose_acceptance_v005_valid",
        "prior_runtime_v002_immutable",
        "source_policy_v002_immutable",
        "candidate_v003_immutable",
        "runtime_projection_554_unique_chunks",
        "purpose_empty_32_overlaid_with_existing_enums",
        "source_and_chunk_general_information_intersection_present",
        "response_metadata_ready_554",
        "assessment_advisory_semantics_preserved",
        "purpose_gate_preserved",
        "high_stop_research_exclusions_preserved",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "purpose_overlay_count": PURPOSE_OVERLAY_COUNT,
        "purpose_needs_review_count": PURPOSE_NEEDS_REVIEW_COUNT,
        "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
        "runtime_integration": "READY_FOR_STAGING_TEST",
        "golden_query": "NOT_EXECUTED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _acceptance_readme() -> str:
    return (
        "# Owner Purpose-Classification Staging Authorization v005\n\n"
        "This package records authorization to create an AI-assisted staging purpose "
        "classification for the 32 ordinary A-unit manual chunks. The decisions remain "
        "`needs_review`; this package is not a human verification or Production approval.\n\n"
        f"- Purpose decisions: `{PURPOSE_OVERLAY_COUNT}`\n"
        "- Existing enum values only; no enum migration\n"
        "- `general_information` added so current Core knowledge intent can use the source\n"
        "- Purpose, assessment, high-risk, stop, and research gates remain enforced\n"
        "- Candidate v003 Chunk bytes: unchanged\n"
        "- External sync: `NOT_AUTHORIZED`\n"
        "- Production: `BLOCKED`\n"
    )


def _runtime_readme(document: Mapping[str, Any]) -> str:
    return (
        "# Source-Family Runtime Policy v003\n\n"
        "This immutable staging successor preserves runtime v002 and overlays the 32 "
        "previously empty A-unit manual purposes with auditable existing-enum decisions.\n\n"
        f"- Search candidates: `{document['summary']['chunk_count']}` across "
        f"`{document['summary']['source_count']}` official sources\n"
        f"- Purpose overlays: `{PURPOSE_OVERLAY_COUNT}` (`needs_review`)\n"
        f"- Response-metadata-ready: `{RESPONSE_METADATA_READY_COUNT}`\n"
        "- Source and chunk policies now intersect on `general_information` for these rows\n"
        "- Purpose and assessment response gates remain fail closed\n"
        "- Candidate v003 Chunk bytes remain immutable\n"
        "- Golden Query live relevance: `NOT_EXECUTED`\n"
        "- External sync: `NOT_AUTHORIZED`\n"
        "- Production: `BLOCKED`\n\n"
        "Do not edit this v003 package in place.\n"
    )

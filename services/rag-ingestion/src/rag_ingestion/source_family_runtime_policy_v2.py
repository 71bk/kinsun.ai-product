"""Build the owner-authorized assessment-response runtime policy v002 successor."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

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

RUNTIME_POLICY_VERSION = "v002"
SCHEMA_VERSION = "2.0.0"
SOURCE_POLICY_MAP_VERSION = "v002"
CANDIDATE_ARTIFACT_VERSION = "v003"
SOURCE_COUNT = 14
CHUNK_COUNT = 554
PROFESSIONAL_NULL_TO_TRUE_COUNT = 220
OFFICIAL_NULL_TO_TRUE_COUNT = 5
RESPONSE_METADATA_READY_COUNT = 522
ASSESSMENT_ADVISORY_CHUNK_COUNT = 372
HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"

OWNER_STATEMENTS = (
    "確認完為true，還有其他欄位也是這樣的嗎",
    "應該是true的話要加詳細要問專業人士吧",
    "好那現在null幫我進行更改",
)
SIGNED_AT = "2026-08-27T11:44:29+08:00"

V1_RUNTIME_ROOT = Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v001")
V1_POLICY_PATH = V1_RUNTIME_ROOT / "source-family-runtime-policy.json"
V1_POLICY_SHA256 = "125b9d4c28371dc516610916bbe58ff43b2ab8c3843e02a5e439e1c2fc0f4c79"
V1_SCHEMA_PATH = Path("contracts/schemas/rag/rag-source-family-runtime-policy-v1.schema.json")
SOURCE_POLICY_ROOT = Path("data/rag-v3/governance/source-family-policy/candidates/v002")
CANDIDATE_ROOT = Path("data/rag-v3/candidates/v003")
PRIOR_ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v003")
ACCEPTANCE_ROOT = Path("data/rag-v3/review/acceptance/v004")
ACCEPTANCE_FILE = ACCEPTANCE_ROOT / "owner-assessment-response-policy-acceptance.json"
ACCEPTANCE_SCHEMA_PATH = Path(
    "contracts/schemas/rag/rag-owner-assessment-response-policy-acceptance-v1.schema.json"
)
RUNTIME_SCHEMA_PATH = Path("contracts/schemas/rag/rag-source-family-runtime-policy-v2.schema.json")
RUNTIME_ROOT = Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v002")
RUNTIME_POLICY_FILENAME = "source-family-runtime-policy.json"
VALIDATION_INPUT_FILENAME = "validation-input-inventory.json"
PRIOR_LOCK_FILENAME = "prior-artifact-lock.json"
VALIDATION_REPORT_FILENAME = "validation-report.json"
CHECKSUM_FILENAME = "SHA256SUMS.txt"

FIXED_INPUT_PATHS = (
    Path(".gitattributes"),
    ACCEPTANCE_SCHEMA_PATH,
    RUNTIME_SCHEMA_PATH,
    Path("scripts/rag/build_source_family_runtime_policy_v2.py"),
    Path("scripts/rag/validate_source_family_runtime_policy_v2.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_runtime_policy.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_runtime_policy_v2.py"),
    Path("services/rag-ingestion/tests/integration/" "test_source_family_runtime_policy_v2.py"),
    Path("services/rag-ingestion/tests/unit/test_source_family_policy_v2_schema.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/runtime_policy.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/models.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/retriever.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/citations.py"),
    Path("services/agent-runtime/src/agent_runtime/models/prompting.py"),
    Path("services/agent-runtime/src/agent_runtime/orchestration/orchestrator.py"),
    Path("services/agent-runtime/tests/unit/test_source_family_runtime_policy.py"),
    Path("services/agent-runtime/tests/unit/test_rag_agent_orchestration.py"),
    Path("services/agent-runtime/tests/unit/test_rag_citation_v2.py"),
    Path("services/agent-runtime/tests/unit/test_provider_and_contract.py"),
    Path("config/rag/source-family-golden-queries-v002.json"),
    V1_POLICY_PATH,
    ACCEPTANCE_FILE,
    SOURCE_POLICY_ROOT / "source-family-policy-map.json",
    CANDIDATE_ROOT / "SHA256SUMS.txt",
)
PRIOR_ARTIFACT_ROOTS = (
    V1_RUNTIME_ROOT,
    SOURCE_POLICY_ROOT,
    CANDIDATE_ROOT,
    PRIOR_ACCEPTANCE_ROOT,
)


class SourceFamilyRuntimePolicyV2Error(SourceFamilyRuntimePolicyError):
    """Raised when v002 acceptance, bytes, or response semantics diverge."""


@dataclass(frozen=True, slots=True)
class RuntimePolicyV2Summary:
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
            "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
            "professional_null_to_true_count": PROFESSIONAL_NULL_TO_TRUE_COUNT,
            "official_null_to_true_count": OFFICIAL_NULL_TO_TRUE_COUNT,
            "policy_sha256": self.policy_sha256,
            "validation_input_inventory_sha256": (self.validation_input_inventory_sha256),
            "prior_artifact_lock_sha256": self.prior_artifact_lock_sha256,
            "production_approved": False,
        }


def build_owner_assessment_response_acceptance(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> Path:
    """Record the owner's explicit null-to-true and mandatory-advisory decision."""

    root = repository_root.resolve()
    destination = (output_path or root / ACCEPTANCE_ROOT).resolve()
    _refuse_overwrite(destination, "assessment-response acceptance v004")
    _validate_prior_runtime_policy_package(root)
    acceptance = _acceptance_document(root)
    staged = _new_staging_directory(root, "assessment-response-acceptance-v004")
    try:
        _write_json(staged / ACCEPTANCE_FILE.name, acceptance)
        _write_json(staged / "validation-report.json", _acceptance_report())
        _write_json(
            staged / "manifest.json",
            {
                "schema_version": "1.0.0",
                "acceptance_version": "v004",
                "files": [ACCEPTANCE_FILE.name, "validation-report.json"],
                "acceptance_sha256": _sha256_file(staged / ACCEPTANCE_FILE.name),
                "external_sync": "NOT_AUTHORIZED",
                "production_approved": False,
            },
        )
        _write_text(staged / "README.md", _acceptance_readme())
        _write_checksums(staged)
        validate_owner_assessment_response_acceptance(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return destination


def validate_owner_assessment_response_acceptance(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate the recorded user statements and every immutable binding."""

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
    document = _read_json(package / ACCEPTANCE_FILE.name)
    _validate_schema(root / ACCEPTANCE_SCHEMA_PATH, document, "owner acceptance")
    if document != _acceptance_document(root):
        raise SourceFamilyRuntimePolicyV2Error("assessment-response acceptance is not reproducible")
    if _read_json(package / "validation-report.json") != _acceptance_report():
        raise SourceFamilyRuntimePolicyV2Error("acceptance report is inconsistent")
    manifest = _read_json(package / "manifest.json")
    if manifest["acceptance_sha256"] != _sha256_file(package / ACCEPTANCE_FILE.name):
        raise SourceFamilyRuntimePolicyV2Error("acceptance manifest hash mismatch")
    return {
        "status": "PASS",
        "acceptance_sha256": manifest["acceptance_sha256"],
        "professional_null_to_true_count": PROFESSIONAL_NULL_TO_TRUE_COUNT,
        "official_null_to_true_count": OFFICIAL_NULL_TO_TRUE_COUNT,
        "production_approved": False,
    }


def build_source_family_runtime_policy_v2(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> RuntimePolicyV2Summary:
    """Build the immutable runtime v002 assessment-response successor atomically."""

    root = repository_root.resolve()
    destination = (output_path or root / RUNTIME_ROOT).resolve()
    _refuse_overwrite(destination, "source-family runtime policy v002")
    _validate_prior_runtime_policy_package(root)
    validate_owner_assessment_response_acceptance(root)
    document = _runtime_policy_document(root)
    inventory = _inventory_document(
        "source_family_runtime_policy_v002_validation_input_inventory",
        _validation_input_entries(root),
        "v002 schema, owner decision, runtime code, tests, Golden cases, and formal inputs",
    )
    prior_lock = _inventory_document(
        "source_family_runtime_policy_v002_prior_artifact_immutable_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
        "immutable runtime v001, source policy v002, candidate v003, and acceptance v003 bytes",
    )
    staged = _new_staging_directory(root, "source-family-runtime-policy-v002")
    try:
        _write_json(staged / RUNTIME_POLICY_FILENAME, document)
        _write_json(staged / VALIDATION_INPUT_FILENAME, inventory)
        _write_json(staged / PRIOR_LOCK_FILENAME, prior_lock)
        _write_json(staged / VALIDATION_REPORT_FILENAME, _validation_report())
        _write_text(staged / "README.md", _runtime_readme(document))
        _write_checksums(staged)
        result = validate_source_family_runtime_policy_v2(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return RuntimePolicyV2Summary(
        output_path=destination,
        policy_sha256=result["policy_sha256"],
        validation_input_inventory_sha256=inventory["inventory_sha256"],
        prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
    )


def validate_source_family_runtime_policy_v2(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate v002 hashes, owner binding, schema, and exact successor semantics."""

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
    validate_owner_assessment_response_acceptance(root)
    if package == (root / RUNTIME_ROOT).resolve():
        _validate_frozen_inventory_document_v2(
            package / VALIDATION_INPUT_FILENAME,
            expected_kind="source_family_runtime_policy_v002_validation_input_inventory",
        )
    else:
        _validate_inventory_document(
            package / VALIDATION_INPUT_FILENAME,
            "source_family_runtime_policy_v002_validation_input_inventory",
            _validation_input_entries(root),
        )
    _validate_inventory_document(
        package / PRIOR_LOCK_FILENAME,
        "source_family_runtime_policy_v002_prior_artifact_immutable_lock",
        _entries_for_roots(root, PRIOR_ARTIFACT_ROOTS),
    )
    document = _read_json(package / RUNTIME_POLICY_FILENAME)
    _validate_schema(root / RUNTIME_SCHEMA_PATH, document, "runtime policy v002")
    expected = _runtime_policy_document(root)
    if document != expected:
        raise SourceFamilyRuntimePolicyV2Error("runtime policy v002 is not reproducible")
    if (package / RUNTIME_POLICY_FILENAME).read_bytes() != _json_bytes(document):
        raise SourceFamilyRuntimePolicyV2Error("runtime policy v002 JSON is not deterministic")
    if _read_json(package / VALIDATION_REPORT_FILENAME) != _validation_report():
        raise SourceFamilyRuntimePolicyV2Error("runtime policy v002 report is inconsistent")
    if (package / "README.md").read_text(encoding="utf-8") != _runtime_readme(document):
        raise SourceFamilyRuntimePolicyV2Error("runtime policy v002 README is inconsistent")
    return {
        "status": "PASS",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
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
        "acceptance_version": "v004",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
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
            "intent": "AUTHORIZE_ASSESSMENT_RESPONSE_POLICY_V002",
            "cryptographic_signature": None,
        },
        "bindings": {
            "prior_runtime_policy_path": V1_POLICY_PATH.as_posix(),
            "prior_runtime_policy_sha256": _sha256_file(root / V1_POLICY_PATH),
            "source_policy_path": (SOURCE_POLICY_ROOT / "source-family-policy-map.json").as_posix(),
            "source_policy_sha256": _sha256_file(
                root / SOURCE_POLICY_ROOT / "source-family-policy-map.json"
            ),
            "candidate_path": CANDIDATE_ROOT.as_posix(),
            "candidate_checksums_sha256": _sha256_file(root / CANDIDATE_ROOT / "SHA256SUMS.txt"),
            "source_count": SOURCE_COUNT,
            "chunk_count": CHUNK_COUNT,
        },
        "assessment_null_decision": {
            "requires_professional_assessment_null_value": True,
            "professional_affected_chunk_count": PROFESSIONAL_NULL_TO_TRUE_COUNT,
            "requires_official_assessment_null_value": True,
            "official_affected_chunk_count": OFFICIAL_NULL_TO_TRUE_COUNT,
            "scope": "ORDINARY_RUNTIME_CANDIDATES_ONLY",
            "candidate_chunk_bytes_mutated": False,
            "excluded_high_stop_research_rows_mutated": False,
        },
        "response_policy_decision": {
            "false_behavior": "ALLOW_GENERAL_INFORMATION",
            "true_behavior": "ALLOW_GENERAL_INFORMATION_WITH_MANDATORY_ADVISORY",
            "null_behavior": "DENY_RESPONSE",
            "personalized_diagnosis": "DENY",
            "personalized_eligibility_level_benefit_determination": "DENY",
            "empty_purpose_behavior": "DENY_RESPONSE",
            "advisory_delivery": "DETERMINISTIC_RUNTIME_APPEND",
        },
        "gates": {
            "environment": "STAGING",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _validate_prior_runtime_policy_package(root: Path) -> None:
    """Validate immutable v001 bytes without re-running its historical source inventory.

    The v001 validation input inventory intentionally pins the implementation that built
    v001. A successor must be able to change runtime code, so v002 verifies the prior
    package bytes and formal bindings instead of comparing current code to that historical
    inventory.
    """

    package = root / V1_RUNTIME_ROOT
    expected_paths = {
        "README.md",
        CHECKSUM_FILENAME,
        PRIOR_LOCK_FILENAME,
        RUNTIME_POLICY_FILENAME,
        VALIDATION_INPUT_FILENAME,
        VALIDATION_REPORT_FILENAME,
    }
    try:
        _validate_package_inventory(package, expected_paths)
        _assert_text_tree(package)
        _validate_checksums(package)
    except SourceFamilyRuntimePolicyError as exc:
        raise SourceFamilyRuntimePolicyV2Error(
            "prior runtime v001 package integrity failed"
        ) from exc
    if _sha256_file(root / V1_POLICY_PATH) != V1_POLICY_SHA256:
        raise SourceFamilyRuntimePolicyV2Error("prior runtime v001 policy bytes changed")
    document = _read_json(root / V1_POLICY_PATH)
    _validate_schema(root / V1_SCHEMA_PATH, document, "prior runtime policy v001")
    chunks = document["chunks"]
    if (
        len(chunks) != CHUNK_COUNT
        or len({chunk["prior_chunk_id"] for chunk in chunks}) != CHUNK_COUNT
        or len({chunk["chunk_id"] for chunk in chunks}) != CHUNK_COUNT
        or len({chunk["source_id"] for chunk in chunks}) != SOURCE_COUNT
        or document["summary"]["response_metadata_ready_count"] != 302
        or document["gates"]["production_approved"] is not False
    ):
        raise SourceFamilyRuntimePolicyV2Error("prior runtime v001 semantics changed")
    source_policy = document["source_policy_binding"]
    if source_policy["sha256"] != _sha256_file(root / source_policy["path"]):
        raise SourceFamilyRuntimePolicyV2Error("prior source policy binding changed")
    candidate = document["candidate_binding"]
    if candidate["checksums_sha256"] != _sha256_file(root / candidate["path"] / CHECKSUM_FILENAME):
        raise SourceFamilyRuntimePolicyV2Error("prior candidate checksum binding changed")
    if candidate["crosswalk_sha256"] != _sha256_file(root / candidate["crosswalk_path"]):
        raise SourceFamilyRuntimePolicyV2Error("prior candidate crosswalk binding changed")


def _runtime_policy_document(root: Path) -> dict[str, Any]:
    prior = _read_json(root / V1_POLICY_PATH)
    document = copy.deepcopy(prior)
    acceptance = validate_owner_assessment_response_acceptance(root)
    professional_count = 0
    official_count = 0
    for chunk in document["chunks"]:
        if chunk["requires_professional_assessment"] is None:
            chunk["requires_professional_assessment"] = True
            professional_count += 1
        if chunk["requires_official_assessment"] is None:
            chunk["requires_official_assessment"] = True
            official_count += 1
    if professional_count != PROFESSIONAL_NULL_TO_TRUE_COUNT:
        raise SourceFamilyRuntimePolicyV2Error("professional null overlay count diverged")
    if official_count != OFFICIAL_NULL_TO_TRUE_COUNT:
        raise SourceFamilyRuntimePolicyV2Error("official null overlay count diverged")
    response_ready = sum(bool(chunk["chunk_allowed_purposes"]) for chunk in document["chunks"])
    advisory_count = sum(
        chunk["requires_official_assessment"] or chunk["requires_professional_assessment"]
        for chunk in document["chunks"]
    )
    if response_ready != RESPONSE_METADATA_READY_COUNT:
        raise SourceFamilyRuntimePolicyV2Error("v002 response-ready count diverged")
    if advisory_count != ASSESSMENT_ADVISORY_CHUNK_COUNT:
        raise SourceFamilyRuntimePolicyV2Error("v002 advisory count diverged")
    document.update(
        {
            "schema_version": SCHEMA_VERSION,
            "runtime_policy_version": RUNTIME_POLICY_VERSION,
            "assessment_acceptance_binding": {
                "path": ACCEPTANCE_FILE.as_posix(),
                "sha256": acceptance["acceptance_sha256"],
                "acceptance_version": "v004",
            },
            "prior_runtime_policy_binding": {
                "path": V1_POLICY_PATH.as_posix(),
                "sha256": _sha256_file(root / V1_POLICY_PATH),
                "runtime_policy_version": "v001",
                "relationship": "SUPERSEDES_WITHOUT_MUTATING_PRIOR_BYTES",
            },
        }
    )
    document["global_policy"]["assessment_response_gate"] = (
        "ALLOW_GENERAL_INFORMATION_TRUE_REQUIRES_DETERMINISTIC_ADVISORY_NULL_DENIES"
    )
    document["summary"] = {
        **document["summary"],
        "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
        "professional_null_to_true_count": PROFESSIONAL_NULL_TO_TRUE_COUNT,
        "official_null_to_true_count": OFFICIAL_NULL_TO_TRUE_COUNT,
        "assessment_advisory_chunk_count": ASSESSMENT_ADVISORY_CHUNK_COUNT,
    }
    return document


def _validation_input_entries(root: Path) -> list[dict[str, Any]]:
    return _file_entries(root, [root / path for path in FIXED_INPUT_PATHS])


def _inventory_document(
    kind: str,
    entries: Sequence[Mapping[str, Any]],
    scope: str,
) -> dict[str, Any]:
    normalized = [dict(entry) for entry in entries]
    return {
        "schema_version": "1.0.0",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "kind": kind,
        "hash_mode": HASH_MODE,
        "entry_count": len(normalized),
        "inventory_sha256": _canonical_sha256(normalized),
        "entries": normalized,
        "scope": scope,
        "production_approved": False,
    }


def _validate_inventory_document(
    path: Path,
    expected_kind: str,
    current_entries: Sequence[Mapping[str, Any]],
) -> None:
    document = _read_json(path)
    expected = _inventory_document(expected_kind, current_entries, document.get("scope", ""))
    if document != expected or path.read_bytes() != _json_bytes(document):
        raise SourceFamilyRuntimePolicyV2Error(f"{expected_kind} changed after packaging")


def _validate_frozen_inventory_document_v2(path: Path, *, expected_kind: str) -> None:
    """Validate canonical v002 build inputs as sealed historical evidence."""

    document = _read_json(path)
    required_keys = {
        "schema_version",
        "runtime_policy_version",
        "kind",
        "hash_mode",
        "entry_count",
        "inventory_sha256",
        "entries",
        "scope",
        "production_approved",
    }
    entries = document.get("entries")
    if set(document) != required_keys or not isinstance(entries, list):
        raise SourceFamilyRuntimePolicyV2Error(f"{expected_kind} fields are invalid")
    expected = {
        **document,
        "schema_version": "1.0.0",
        "runtime_policy_version": RUNTIME_POLICY_VERSION,
        "kind": expected_kind,
        "hash_mode": HASH_MODE,
        "entry_count": len(entries),
        "inventory_sha256": _canonical_sha256(entries),
        "production_approved": False,
    }
    if document != expected:
        raise SourceFamilyRuntimePolicyV2Error(f"{expected_kind} sealed evidence is invalid")
    if any(
        not isinstance(entry, dict)
        or set(entry) != {"path", "bytes", "sha256"}
        or not isinstance(entry["path"], str)
        or not isinstance(entry["bytes"], int)
        or entry["bytes"] < 0
        or not isinstance(entry["sha256"], str)
        or len(entry["sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in entry["sha256"])
        for entry in entries
    ):
        raise SourceFamilyRuntimePolicyV2Error(f"{expected_kind} entry is invalid")
    paths = [entry["path"] for entry in entries]
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        raise SourceFamilyRuntimePolicyV2Error(f"{expected_kind} paths are invalid")
    if path.read_bytes() != _json_bytes(document):
        raise SourceFamilyRuntimePolicyV2Error(f"{expected_kind} is not deterministic JSON")


def _acceptance_report() -> dict[str, Any]:
    checks = (
        "owner_statements_hash_bound",
        "prior_runtime_v001_hash_bound",
        "source_policy_v002_hash_bound",
        "candidate_v003_hash_bound",
        "professional_null_220_authorized_true",
        "official_null_5_authorized_true",
        "true_requires_deterministic_advisory",
        "personalized_diagnosis_and_eligibility_denied",
        "chunk_bytes_not_mutated",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": "1.0.0",
        "acceptance_version": "v004",
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "professional_null_to_true_count": PROFESSIONAL_NULL_TO_TRUE_COUNT,
        "official_null_to_true_count": OFFICIAL_NULL_TO_TRUE_COUNT,
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validation_report() -> dict[str, Any]:
    checks = (
        "owner_acceptance_v004_valid",
        "prior_runtime_v001_immutable",
        "source_policy_v002_immutable",
        "candidate_v003_immutable",
        "runtime_projection_554_unique_chunks",
        "professional_null_220_overlaid_true",
        "official_null_5_overlaid_true",
        "assessment_null_count_zero",
        "empty_purpose_32_still_denied",
        "response_metadata_ready_522",
        "true_requires_deterministic_advisory",
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
        "response_metadata_ready_count": RESPONSE_METADATA_READY_COUNT,
        "professional_null_to_true_count": PROFESSIONAL_NULL_TO_TRUE_COUNT,
        "official_null_to_true_count": OFFICIAL_NULL_TO_TRUE_COUNT,
        "runtime_integration": "READY_FOR_STAGING_TEST",
        "golden_query": "NOT_EXECUTED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _acceptance_readme() -> str:
    return (
        "# Owner Assessment-Response Policy Acceptance v004\n\n"
        "This package records the project owner's explicit staging decision for "
        "assessment nulls and response behavior. It does not mutate v003 Chunk bytes.\n\n"
        f"- Professional null → true: `{PROFESSIONAL_NULL_TO_TRUE_COUNT}` runtime candidates\n"
        f"- Official null → true: `{OFFICIAL_NULL_TO_TRUE_COUNT}` runtime candidates\n"
        "- true: general information allowed with a deterministic advisory\n"
        "- Personalized diagnosis, eligibility, level, and benefit determination: denied\n"
        "- External sync: `NOT_AUTHORIZED`\n"
        "- Production: `BLOCKED`\n"
    )


def _runtime_readme(document: Mapping[str, Any]) -> str:
    return (
        "# Source-Family Runtime Policy v002\n\n"
        "This immutable staging successor preserves the v001 search pool and applies the "
        "owner-authorized assessment-response overlay.\n\n"
        f"- Search candidates: `{document['summary']['chunk_count']}` across "
        f"`{document['summary']['source_count']}` official sources\n"
        f"- Response-metadata-ready: `{RESPONSE_METADATA_READY_COUNT}`\n"
        f"- Professional null → true: `{PROFESSIONAL_NULL_TO_TRUE_COUNT}`\n"
        f"- Official null → true: `{OFFICIAL_NULL_TO_TRUE_COUNT}`\n"
        "- true permits general information and requires a deterministic advisory\n"
        "- null and empty purpose deny response; high/stop/research exclusions remain\n"
        "- Golden Query: `NOT_EXECUTED`\n"
        "- External sync: `NOT_AUTHORIZED`\n"
        "- Production: `BLOCKED`\n\n"
        "Do not edit this v002 package in place.\n"
    )


def _validate_schema(path: Path, document: Mapping[str, Any], label: str) -> None:
    schema = _read_json(path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "<root>"
        raise SourceFamilyRuntimePolicyV2Error(
            f"{label} schema failure at {location}: {first.message}"
        )


def _validate_package_inventory(package: Path, expected: set[str]) -> None:
    actual = {path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()}
    if actual != expected:
        raise SourceFamilyRuntimePolicyV2Error("package inventory is incomplete")


def _new_staging_directory(root: Path, prefix: str) -> Path:
    pending = root / "data/rag-v3/.pending"
    pending.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f"{prefix}-", dir=pending)).resolve()


def _cleanup_staging_directory(root: Path, staged: Path) -> None:
    pending = (root / "data/rag-v3/.pending").resolve()
    if staged.is_dir() and staged.is_relative_to(pending):
        shutil.rmtree(staged)
    if pending.is_dir() and not any(pending.iterdir()):
        pending.rmdir()


def _publish_directory(staged: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise SourceFamilyRuntimePolicyV2Error("destination appeared during publish")
    try:
        staged.replace(destination)
    except OSError as exc:
        if getattr(exc, "winerror", None) != 17:
            raise
        # pytest and Windows deployments can place the destination on another
        # volume. The staged package has already passed full validation.
        shutil.copytree(staged, destination)
        shutil.rmtree(staged)


def _refuse_overwrite(destination: Path, label: str) -> None:
    if destination.exists():
        raise SourceFamilyRuntimePolicyV2Error(f"{label} already exists; refuse to overwrite")


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

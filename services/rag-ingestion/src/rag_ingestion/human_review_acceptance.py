"""Build and validate an immutable project-owner human-review risk acceptance."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from rag_ingestion.human_review_package import (
    EXPECTED_CHUNK_COUNT,
    EXPECTED_SOURCE_COUNT,
    HumanReviewPackageError,
    _assert_text_tree,
    _cleanup_pending_directory,
    _file_entries,
    _load_schema,
    _publish_directory,
    _read_json,
    _sha256_file,
    _validate_checksums,
    _validate_schema,
    _write_checksums,
    _write_json,
    _write_text,
    validate_human_review_package,
)

ACCEPTANCE_VERSION = "v001"
ASSIGNMENT_PACKAGE_VERSION = "v001"
CANDIDATE_ARTIFACT_VERSION = "v002"
SCHEMA_VERSION = "1.0.0"
HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"

ASSIGNMENT_PACKAGE_PATH = Path("data/rag-v2/human-review/v001")
SCHEMA_PATH = Path("contracts/schemas/rag/human-review-owner-risk-acceptance-v1.schema.json")
ACCEPTANCE_FILENAME = "owner-risk-acceptance.json"
MANIFEST_FILENAME = "manifest.json"
VALIDATION_REPORT_FILENAME = "validation-report.json"
VALIDATION_INPUT_INVENTORY_FILENAME = "validation-input-inventory.json"
PRIOR_ARTIFACT_LOCK_FILENAME = "prior-artifact-lock.json"
CHECKSUM_FILENAME = "SHA256SUMS.txt"

_VALIDATION_FIXED_PATHS = (
    SCHEMA_PATH,
    Path("services/rag-ingestion/src/rag_ingestion/human_review_acceptance.py"),
    Path("services/rag-ingestion/tests/integration/test_human_review_acceptance.py"),
    Path("scripts/rag/build_human_review_acceptance.py"),
    Path("scripts/rag/validate_human_review_acceptance.py"),
)
_REQUIRED_PATHS = {
    "README.md",
    ACCEPTANCE_FILENAME,
    MANIFEST_FILENAME,
    VALIDATION_REPORT_FILENAME,
    VALIDATION_INPUT_INVENTORY_FILENAME,
    PRIOR_ARTIFACT_LOCK_FILENAME,
    CHECKSUM_FILENAME,
}


class HumanReviewAcceptanceError(HumanReviewPackageError):
    """Raised when a risk-acceptance receipt cannot be built or validated safely."""


@dataclass(frozen=True, slots=True)
class HumanReviewAcceptanceSummary:
    output_path: Path
    project_owner_id: str
    signed_at: str
    accepted_manifest_sha256: str
    accepted_checksums_sha256: str
    accepted_package_inventory_sha256: str
    validation_input_inventory_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "SIGNED",
            "acceptance_version": ACCEPTANCE_VERSION,
            "assignment_package_version": ASSIGNMENT_PACKAGE_VERSION,
            "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
            "output_path": self.output_path.as_posix(),
            "project_owner_id": self.project_owner_id,
            "signed_at": self.signed_at,
            "accepted_manifest_sha256": self.accepted_manifest_sha256,
            "accepted_checksums_sha256": self.accepted_checksums_sha256,
            "accepted_package_inventory_sha256": self.accepted_package_inventory_sha256,
            "validation_input_inventory_sha256": self.validation_input_inventory_sha256,
            "acceptance_scope": "INTERNAL_HUMAN_REVIEW_ONLY",
            "review_completion_status": "NOT_COMPLETED",
            "pending_chunk_assignments": EXPECTED_CHUNK_COUNT,
            "production_status": "BLOCKED",
            "production_approved": False,
        }


def build_human_review_acceptance(
    repository_root: Path,
    output_root: Path,
    *,
    project_owner_id: str,
    signed_at: str,
    authorization_statement: str,
) -> HumanReviewAcceptanceSummary:
    """Build a typed-name owner signature bound to the immutable assignment package."""

    root = repository_root.resolve()
    output_base = output_root.resolve()
    destination = output_base / ACCEPTANCE_VERSION
    if destination.exists():
        raise HumanReviewAcceptanceError(
            "human-review acceptance already exists; refuse to overwrite"
        )
    _validate_signature_inputs(project_owner_id, signed_at, authorization_statement)

    assignment_package = root / ASSIGNMENT_PACKAGE_PATH
    assignment_result = validate_human_review_package(root, assignment_package)
    if (
        assignment_result["source_assignment_count"] != EXPECTED_SOURCE_COUNT
        or assignment_result["chunk_assignment_count"] != EXPECTED_CHUNK_COUNT
        or assignment_result["review_completion_status"] != "NOT_COMPLETED"
        or assignment_result["production_approved"] is not False
    ):
        raise HumanReviewAcceptanceError("assignment package is not pending-only")

    schema = _load_schema(root / SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    prior_entries = _assignment_package_entries(root)
    prior_lock = _inventory_document(
        "human_review_acceptance_prior_artifact_immutable_lock",
        prior_entries,
    )
    input_entries = _file_entries(root, _VALIDATION_FIXED_PATHS)
    input_inventory = _inventory_document(
        "human_review_acceptance_validation_input_inventory",
        input_entries,
    )
    acceptance = _acceptance_document(
        root,
        project_owner_id=project_owner_id,
        signed_at=signed_at,
        authorization_statement=authorization_statement,
        package_inventory_sha256=prior_lock["inventory_sha256"],
    )
    _validate_acceptance_schema(validator, acceptance)

    output_base.mkdir(parents=True, exist_ok=True)
    pending_root = output_base / ".pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    temporary_prefix = f"human-review-acceptance-{ACCEPTANCE_VERSION}-"
    temporary_root = Path(tempfile.mkdtemp(prefix=temporary_prefix, dir=pending_root)).resolve()
    staged = temporary_root / ACCEPTANCE_VERSION
    staged.mkdir()
    try:
        _write_json(staged / ACCEPTANCE_FILENAME, acceptance)
        _write_json(staged / PRIOR_ARTIFACT_LOCK_FILENAME, prior_lock)
        _write_json(staged / VALIDATION_INPUT_INVENTORY_FILENAME, input_inventory)
        _write_text(staged / "README.md", _readme(acceptance))
        _write_json(
            staged / MANIFEST_FILENAME,
            _manifest(
                staged,
                acceptance,
                prior_lock_sha256=prior_lock["inventory_sha256"],
                validation_inventory_sha256=input_inventory["inventory_sha256"],
            ),
        )
        _write_json(staged / VALIDATION_REPORT_FILENAME, _validation_report())
        _write_checksums(staged)

        result = validate_human_review_acceptance(root, staged)
        _publish_directory(staged, destination)
        return HumanReviewAcceptanceSummary(
            output_path=destination,
            project_owner_id=result["project_owner_id"],
            signed_at=result["signed_at"],
            accepted_manifest_sha256=result["accepted_manifest_sha256"],
            accepted_checksums_sha256=result["accepted_checksums_sha256"],
            accepted_package_inventory_sha256=result["accepted_package_inventory_sha256"],
            validation_input_inventory_sha256=input_inventory["inventory_sha256"],
        )
    finally:
        _cleanup_pending_directory(
            temporary_root,
            pending_root,
            expected_prefix=temporary_prefix,
        )


def validate_human_review_acceptance(
    repository_root: Path,
    package: Path,
) -> dict[str, Any]:
    """Validate the owner identity, signature scope, hashes, and blocked gates."""

    root = repository_root.resolve()
    package_root = package.resolve()
    if not package_root.is_dir() or package_root.name != ACCEPTANCE_VERSION:
        raise HumanReviewAcceptanceError("human-review acceptance path/version is invalid")

    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != _REQUIRED_PATHS:
        raise HumanReviewAcceptanceError("human-review acceptance inventory is incomplete")
    _assert_text_tree(package_root)
    _validate_checksums(package_root)

    assignment_package = root / ASSIGNMENT_PACKAGE_PATH
    assignment_result = validate_human_review_package(root, assignment_package)
    if (
        assignment_result["review_completion_status"] != "NOT_COMPLETED"
        or assignment_result["project_owner_risk_acceptance"] != "NOT_SIGNED"
        or assignment_result["production_approved"] is not False
    ):
        raise HumanReviewAcceptanceError("base assignment package governance changed")

    prior_entries = _assignment_package_entries(root)
    _validate_inventory_document(
        package_root / PRIOR_ARTIFACT_LOCK_FILENAME,
        expected_kind="human_review_acceptance_prior_artifact_immutable_lock",
        current_entries=prior_entries,
    )
    input_entries = _file_entries(root, _VALIDATION_FIXED_PATHS)
    _validate_inventory_document(
        package_root / VALIDATION_INPUT_INVENTORY_FILENAME,
        expected_kind="human_review_acceptance_validation_input_inventory",
        current_entries=input_entries,
    )

    schema = _load_schema(root / SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    acceptance = _read_json(package_root / ACCEPTANCE_FILENAME)
    _validate_acceptance_schema(validator, acceptance)
    _validate_signature_inputs(
        acceptance["project_owner_id"],
        acceptance["signed_at"],
        acceptance["authorization"]["statement"],
    )
    prior_lock = _read_json(package_root / PRIOR_ARTIFACT_LOCK_FILENAME)
    expected_acceptance = _acceptance_document(
        root,
        project_owner_id=acceptance["project_owner_id"],
        signed_at=acceptance["signed_at"],
        authorization_statement=acceptance["authorization"]["statement"],
        package_inventory_sha256=prior_lock["inventory_sha256"],
    )
    if acceptance != expected_acceptance:
        raise HumanReviewAcceptanceError("owner risk acceptance semantics are inconsistent")

    input_inventory = _read_json(package_root / VALIDATION_INPUT_INVENTORY_FILENAME)
    expected_manifest = _manifest(
        package_root,
        acceptance,
        prior_lock_sha256=prior_lock["inventory_sha256"],
        validation_inventory_sha256=input_inventory["inventory_sha256"],
    )
    if _read_json(package_root / MANIFEST_FILENAME) != expected_manifest:
        raise HumanReviewAcceptanceError("owner risk acceptance manifest is inconsistent")
    if _read_json(package_root / VALIDATION_REPORT_FILENAME) != _validation_report():
        raise HumanReviewAcceptanceError("owner risk acceptance report is inconsistent")
    if (package_root / "README.md").read_text(encoding="utf-8") != _readme(acceptance):
        raise HumanReviewAcceptanceError("owner risk acceptance README is inconsistent")

    accepted = acceptance["accepted_artifacts"]
    return {
        "status": "PASS",
        "acceptance_status": "SIGNED",
        "acceptance_version": ACCEPTANCE_VERSION,
        "assignment_package_version": ASSIGNMENT_PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "project_owner_id": acceptance["project_owner_id"],
        "signed_at": acceptance["signed_at"],
        "electronic_signature_assurance": acceptance["electronic_signature"]["assurance"],
        "accepted_manifest_sha256": accepted["manifest_sha256"],
        "accepted_checksums_sha256": accepted["checksums_sha256"],
        "accepted_package_inventory_sha256": accepted["package_inventory_sha256"],
        "acceptance_scope": "INTERNAL_HUMAN_REVIEW_ONLY",
        "review_completion_status": "NOT_COMPLETED",
        "pending_source_assignments": EXPECTED_SOURCE_COUNT,
        "pending_chunk_assignments": EXPECTED_CHUNK_COUNT,
        "production_status": "BLOCKED",
        "production_approved": False,
        "external_access_performed": False,
    }


def _acceptance_document(
    root: Path,
    *,
    project_owner_id: str,
    signed_at: str,
    authorization_statement: str,
    package_inventory_sha256: str,
) -> dict[str, Any]:
    assignment_package = root / ASSIGNMENT_PACKAGE_PATH
    statement_sha256 = hashlib.sha256(authorization_statement.encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_version": ACCEPTANCE_VERSION,
        "assignment_package_version": ASSIGNMENT_PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "SIGNED",
        "project_owner_id": project_owner_id,
        "signer_role": "PROJECT_OWNER",
        "signed_at": signed_at,
        "authorization": {
            "channel": "interactive_user_instruction",
            "statement": authorization_statement,
            "statement_sha256": statement_sha256,
        },
        "electronic_signature": {
            "assurance": "RECORDED_EXPLICIT_USER_AUTHORIZATION",
            "signature_value": project_owner_id,
            "intent": "ACCEPT_INTERNAL_HUMAN_REVIEW_RISK",
            "cryptographic_signature": None,
        },
        "accepted_artifacts": {
            "manifest_path": "data/rag-v2/human-review/v001/manifest.json",
            "manifest_sha256": _sha256_file(assignment_package / MANIFEST_FILENAME),
            "checksums_path": "data/rag-v2/human-review/v001/SHA256SUMS.txt",
            "checksums_sha256": _sha256_file(assignment_package / CHECKSUM_FILENAME),
            "package_inventory_sha256": package_inventory_sha256,
        },
        "acceptance_scope": "INTERNAL_HUMAN_REVIEW_ONLY",
        "risk_acknowledgements": {
            "accepts_unreviewed_source_risk": True,
            "accepts_missing_local_source_files": True,
            "pending_source_assignments": EXPECTED_SOURCE_COUNT,
            "pending_chunk_assignments": EXPECTED_CHUNK_COUNT,
            "external_access_not_performed": True,
        },
        "verification_assertions": {
            "source_fidelity_verified": False,
            "exact_facts_verified": False,
            "source_version_verified": False,
            "license_verified": False,
        },
        "human_source_review": "NOT_COMPLETED",
        "review_status": "needs_review",
        "embedding_status": "NOT_STARTED",
        "indexing_status": "NOT_STARTED",
        "production_status": "BLOCKED",
        "production_approved": False,
        "external_access_performed": False,
    }


def _manifest(
    package: Path,
    acceptance: Mapping[str, Any],
    *,
    prior_lock_sha256: str,
    validation_inventory_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_version": ACCEPTANCE_VERSION,
        "assignment_package_version": ASSIGNMENT_PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "OWNER_RISK_ACCEPTANCE_SIGNED",
        "project_owner_id": acceptance["project_owner_id"],
        "signed_at": acceptance["signed_at"],
        "acceptance_path": ACCEPTANCE_FILENAME,
        "acceptance_sha256": _sha256_file(package / ACCEPTANCE_FILENAME),
        "prior_artifact_lock_sha256": prior_lock_sha256,
        "validation_input_inventory_sha256": validation_inventory_sha256,
        "acceptance_scope": "INTERNAL_HUMAN_REVIEW_ONLY",
        "review_completion_status": "NOT_COMPLETED",
        "pending_source_assignments": EXPECTED_SOURCE_COUNT,
        "pending_chunk_assignments": EXPECTED_CHUNK_COUNT,
        "external_access_performed": False,
        "production_status": "BLOCKED",
        "production_approved": False,
    }


def _validation_report() -> dict[str, Any]:
    checks = [
        {"name": "base_assignment_checksum_verified", "status": "PASS"},
        {"name": "base_assignment_prior_lock_matches", "status": "PASS"},
        {"name": "explicit_owner_authorization_recorded", "status": "PASS"},
        {"name": "typed_signature_identity_matches_owner", "status": "PASS"},
        {"name": "acceptance_scope_internal_review_only", "status": "PASS"},
        {"name": "pending_human_decisions_preserved", "status": "PASS"},
        {"name": "verification_not_asserted", "status": "PASS"},
        {"name": "production_remains_blocked", "status": "PASS"},
        {"name": "external_access_not_performed", "status": "PASS"},
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_version": ACCEPTANCE_VERSION,
        "assignment_package_version": ASSIGNMENT_PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "PASS",
        "pass_count": len(checks),
        "fail_count": 0,
        "checks": checks,
        "review_completion_status": "NOT_COMPLETED",
        "production_status": "BLOCKED",
        "production_approved": False,
    }


def _readme(acceptance: Mapping[str, Any]) -> str:
    return (
        "# Human-review owner risk acceptance v001\n\n"
        f"Project owner `{acceptance['project_owner_id']}` signed this acceptance at "
        f"`{acceptance['signed_at']}` through an explicit interactive instruction.\n\n"
        "This typed-name electronic signature accepts the risk of using the immutable "
        "v001 assignment package for internal human review only. It is not a "
        "cryptographic signature. It does not assert source fidelity, exact-fact, "
        "source-version, license, or human-review completion. All 726 chunk decisions "
        "remain pending, and embedding, indexing, and Production remain blocked.\n\n"
        "Do not edit this acceptance in place. Create a new version for any later "
        "acceptance, revocation, completed review, or Production decision.\n"
    )


def _assignment_package_entries(root: Path) -> list[dict[str, Any]]:
    package = root / ASSIGNMENT_PACKAGE_PATH
    paths = {path.relative_to(root) for path in package.rglob("*") if path.is_file()}
    return _file_entries(root, paths)


def _inventory_document(kind: str, entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ACCEPTANCE_VERSION,
        "kind": kind,
        "hash_mode": HASH_MODE,
        "entry_count": len(entries),
        "inventory_sha256": _inventory_sha256(entries),
        "entries": list(entries),
        "scope": (
            "immutable v001 assignment package bytes"
            if kind == "human_review_acceptance_prior_artifact_immutable_lock"
            else "owner acceptance schema, builder, validator, and tests"
        ),
        "production_approved": False,
    }


def _validate_inventory_document(
    path: Path,
    *,
    expected_kind: str,
    current_entries: Sequence[dict[str, Any]],
) -> None:
    expected = _inventory_document(expected_kind, current_entries)
    if _read_json(path) != expected:
        raise HumanReviewAcceptanceError(f"{expected_kind} changed after signing")


def _inventory_sha256(entries: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_acceptance_schema(
    validator: Draft202012Validator,
    acceptance: Mapping[str, Any],
) -> None:
    try:
        _validate_schema(validator, acceptance, "owner risk acceptance")
    except HumanReviewPackageError as exc:
        raise HumanReviewAcceptanceError(str(exc)) from exc


def _validate_signature_inputs(
    project_owner_id: str,
    signed_at: str,
    authorization_statement: str,
) -> None:
    if not project_owner_id or not authorization_statement:
        raise HumanReviewAcceptanceError("owner identity and authorization are required")
    try:
        parsed = datetime.fromisoformat(signed_at)
    except ValueError as exc:
        raise HumanReviewAcceptanceError("signed_at must be ISO 8601") from exc
    if parsed.utcoffset() != timedelta(hours=8):
        raise HumanReviewAcceptanceError("signed_at must use the Asia/Taipei +08:00 offset")

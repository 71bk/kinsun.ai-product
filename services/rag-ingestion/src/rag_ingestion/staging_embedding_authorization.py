"""Build and validate a fixed-hash staging document-embedding authorization."""

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

from rag_ingestion.human_review_acceptance import validate_human_review_acceptance
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
    _validate_candidate_checksums,
    _validate_checksums,
    _validate_schema,
    _write_checksums,
    _write_json,
    _write_text,
)

ACCEPTANCE_VERSION = "v002"
SUPERSEDES_ACCEPTANCE_VERSION = "v001"
ASSIGNMENT_PACKAGE_VERSION = "v001"
CANDIDATE_ARTIFACT_VERSION = "v002"
SCHEMA_VERSION = "2.0.0"
HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"

PRIOR_ACCEPTANCE_PATH = Path("data/rag-v2/human-review/acceptance/v001")
CANDIDATE_PATH = Path("data/rag-v2/candidates/v002")
ALLOWLIST_RELATIVE_PATH = Path("manifests/embedding-staging-allowlist-v003.json")
CHUNK_MANIFEST_RELATIVE_PATH = Path("manifests/chunk-file-manifest-v002.json")
CHECKSUM_RELATIVE_PATH = Path("SHA256SUMS.txt")
SCHEMA_PATH = Path("contracts/schemas/rag/human-review-owner-acceptance-v2.schema.json")

ACCEPTANCE_FILENAME = "owner-staging-embedding-acceptance.json"
MANIFEST_FILENAME = "manifest.json"
VALIDATION_REPORT_FILENAME = "validation-report.json"
VALIDATION_INPUT_INVENTORY_FILENAME = "validation-input-inventory.json"
PRIOR_ARTIFACT_LOCK_FILENAME = "prior-artifact-lock.json"
CHECKSUM_FILENAME = "SHA256SUMS.txt"

_VALIDATION_FIXED_PATHS = (
    SCHEMA_PATH,
    Path("services/rag-ingestion/src/rag_ingestion/staging_embedding_authorization.py"),
    Path("services/rag-ingestion/tests/integration/test_staging_embedding_authorization.py"),
    Path("scripts/rag/build_staging_embedding_authorization.py"),
    Path("scripts/rag/validate_staging_embedding_authorization.py"),
    Path("data/rag-v2/README.md"),
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


class StagingEmbeddingAuthorizationError(HumanReviewPackageError):
    """Raised when staging embedding authorization is incomplete or unsafe."""


@dataclass(frozen=True, slots=True)
class StagingEmbeddingAuthorizationSummary:
    output_path: Path
    project_owner_id: str
    signed_at: str
    allowlist_sha256: str
    prior_artifact_lock_sha256: str
    validation_input_inventory_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "STAGING_EMBEDDING_AUTHORIZED",
            "acceptance_version": ACCEPTANCE_VERSION,
            "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
            "output_path": self.output_path.as_posix(),
            "project_owner_id": self.project_owner_id,
            "signed_at": self.signed_at,
            "allowlist_sha256": self.allowlist_sha256,
            "source_count": EXPECTED_SOURCE_COUNT,
            "chunk_count": EXPECTED_CHUNK_COUNT,
            "required_document_input_type": "RETRIEVAL_DOCUMENT",
            "required_dimension": 1024,
            "prior_artifact_lock_sha256": self.prior_artifact_lock_sha256,
            "validation_input_inventory_sha256": self.validation_input_inventory_sha256,
            "review_status": "needs_review",
            "indexing_status": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        }


def build_staging_embedding_authorization(
    repository_root: Path,
    output_root: Path,
    *,
    project_owner_id: str,
    signed_at: str,
    authorization_statement: str,
) -> StagingEmbeddingAuthorizationSummary:
    """Build an immutable signature bound to the current candidate allowlist bytes."""

    root = repository_root.resolve()
    output_base = output_root.resolve()
    destination = output_base / ACCEPTANCE_VERSION
    if destination.exists():
        raise StagingEmbeddingAuthorizationError(
            "staging embedding authorization already exists; refuse to overwrite"
        )
    _validate_signature_inputs(project_owner_id, signed_at, authorization_statement)
    _validate_prior_acceptance(root)
    _validate_candidate_anchors(root)

    schema = _load_schema(root / SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    prior_entries = _prior_acceptance_entries(root)
    prior_lock = _inventory_document(
        "staging_embedding_authorization_prior_artifact_immutable_lock",
        prior_entries,
    )
    input_entries = _file_entries(root, _VALIDATION_FIXED_PATHS)
    input_inventory = _inventory_document(
        "staging_embedding_authorization_validation_input_inventory",
        input_entries,
    )
    acceptance = _acceptance_document(
        root,
        project_owner_id=project_owner_id,
        signed_at=signed_at,
        authorization_statement=authorization_statement,
    )
    _validate_authorization_schema(validator, acceptance)

    output_base.mkdir(parents=True, exist_ok=True)
    pending_root = output_base / ".pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    temporary_prefix = f"staging-embedding-authorization-{ACCEPTANCE_VERSION}-"
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
        _write_json(staged / VALIDATION_REPORT_FILENAME, _validation_report(acceptance))
        _write_checksums(staged)

        result = validate_staging_embedding_authorization(root, staged)
        _publish_directory(staged, destination)
        return StagingEmbeddingAuthorizationSummary(
            output_path=destination,
            project_owner_id=result["project_owner_id"],
            signed_at=result["signed_at"],
            allowlist_sha256=result["allowlist_sha256"],
            prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
            validation_input_inventory_sha256=input_inventory["inventory_sha256"],
        )
    finally:
        _cleanup_pending_directory(
            temporary_root,
            pending_root,
            expected_prefix=temporary_prefix,
        )


def validate_staging_embedding_authorization(
    repository_root: Path,
    package: Path,
) -> dict[str, Any]:
    """Validate owner identity, fixed hashes, immutable history, and blocked gates."""

    root = repository_root.resolve()
    package_root = package.resolve()
    if not package_root.is_dir() or package_root.name != ACCEPTANCE_VERSION:
        raise StagingEmbeddingAuthorizationError(
            "staging embedding authorization path/version is invalid"
        )
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != _REQUIRED_PATHS:
        raise StagingEmbeddingAuthorizationError(
            "staging embedding authorization inventory is incomplete"
        )
    _assert_text_tree(package_root)
    _validate_checksums(package_root)
    _validate_prior_acceptance(root)
    _validate_candidate_anchors(root)

    _validate_inventory_document(
        package_root / PRIOR_ARTIFACT_LOCK_FILENAME,
        expected_kind="staging_embedding_authorization_prior_artifact_immutable_lock",
        current_entries=_prior_acceptance_entries(root),
    )
    _validate_inventory_document(
        package_root / VALIDATION_INPUT_INVENTORY_FILENAME,
        expected_kind="staging_embedding_authorization_validation_input_inventory",
        current_entries=_file_entries(root, _VALIDATION_FIXED_PATHS),
    )

    schema = _load_schema(root / SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    acceptance = _read_json(package_root / ACCEPTANCE_FILENAME)
    _validate_authorization_schema(validator, acceptance)
    _validate_signature_inputs(
        acceptance["project_owner_id"],
        acceptance["signed_at"],
        acceptance["authorization"]["statement"],
    )
    expected_acceptance = _acceptance_document(
        root,
        project_owner_id=acceptance["project_owner_id"],
        signed_at=acceptance["signed_at"],
        authorization_statement=acceptance["authorization"]["statement"],
    )
    if acceptance != expected_acceptance:
        raise StagingEmbeddingAuthorizationError(
            "staging embedding authorization semantics are inconsistent"
        )

    prior_lock = _read_json(package_root / PRIOR_ARTIFACT_LOCK_FILENAME)
    input_inventory = _read_json(package_root / VALIDATION_INPUT_INVENTORY_FILENAME)
    expected_manifest = _manifest(
        package_root,
        acceptance,
        prior_lock_sha256=prior_lock["inventory_sha256"],
        validation_inventory_sha256=input_inventory["inventory_sha256"],
    )
    if _read_json(package_root / MANIFEST_FILENAME) != expected_manifest:
        raise StagingEmbeddingAuthorizationError(
            "staging embedding authorization manifest is inconsistent"
        )
    if _read_json(package_root / VALIDATION_REPORT_FILENAME) != _validation_report(acceptance):
        raise StagingEmbeddingAuthorizationError(
            "staging embedding authorization report is inconsistent"
        )
    if (package_root / "README.md").read_text(encoding="utf-8") != _readme(acceptance):
        raise StagingEmbeddingAuthorizationError(
            "staging embedding authorization README is inconsistent"
        )

    artifacts = acceptance["accepted_artifacts"]
    return {
        "status": "PASS",
        "authorization_status": "STAGING_EMBEDDING_AUTHORIZED",
        "acceptance_version": ACCEPTANCE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "project_owner_id": acceptance["project_owner_id"],
        "signed_at": acceptance["signed_at"],
        "allowlist_sha256": artifacts["allowlist_sha256"],
        "source_count": artifacts["source_count"],
        "chunk_count": artifacts["chunk_count"],
        "required_document_input_type": "RETRIEVAL_DOCUMENT",
        "required_dimension": 1024,
        "review_status": "needs_review",
        "indexing_status": "NOT_AUTHORIZED",
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
) -> dict[str, Any]:
    candidate = root / CANDIDATE_PATH
    prior = root / PRIOR_ACCEPTANCE_PATH
    statement_sha256 = hashlib.sha256(authorization_statement.encode("utf-8")).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_version": ACCEPTANCE_VERSION,
        "supersedes_acceptance_version": SUPERSEDES_ACCEPTANCE_VERSION,
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
            "intent": "AUTHORIZE_FIXED_HASH_STAGING_DOCUMENT_EMBEDDING",
            "cryptographic_signature": None,
        },
        "accepted_artifacts": {
            "prior_acceptance_manifest_path": (
                "data/rag-v2/human-review/acceptance/v001/manifest.json"
            ),
            "prior_acceptance_manifest_sha256": _sha256_file(prior / MANIFEST_FILENAME),
            "allowlist_path": (
                "data/rag-v2/candidates/v002/manifests/" "embedding-staging-allowlist-v003.json"
            ),
            "allowlist_sha256": _sha256_file(candidate / ALLOWLIST_RELATIVE_PATH),
            "allowlist_size_bytes": (candidate / ALLOWLIST_RELATIVE_PATH).stat().st_size,
            "chunk_manifest_path": (
                "data/rag-v2/candidates/v002/manifests/chunk-file-manifest-v002.json"
            ),
            "chunk_manifest_sha256": _sha256_file(candidate / CHUNK_MANIFEST_RELATIVE_PATH),
            "candidate_checksums_path": "data/rag-v2/candidates/v002/SHA256SUMS.txt",
            "candidate_checksums_sha256": _sha256_file(candidate / CHECKSUM_RELATIVE_PATH),
            "source_count": EXPECTED_SOURCE_COUNT,
            "chunk_count": EXPECTED_CHUNK_COUNT,
        },
        "acceptance_scope": "STAGING_DOCUMENT_EMBEDDING_ONLY",
        "review_assertions": {
            "owner_review_and_signature_statement_recorded": True,
            "formal_item_level_review_evidence": "NOT_RECORDED",
            "assignment_package_status": "PENDING_ONLY",
            "source_assignment_count": EXPECTED_SOURCE_COUNT,
            "chunk_assignment_count": EXPECTED_CHUNK_COUNT,
            "review_status": "needs_review",
        },
        "embedding_authorization": {
            "environment": "STAGING",
            "allowed_use": "INTERNAL_EMERGENCY_DEMO_ONLY",
            "required_document_input_type": "RETRIEVAL_DOCUMENT",
            "required_dimension": 1024,
            "provider_profile_binding_required": True,
            "mixed_embedding_profiles_allowed": False,
            "allowed_actions": [
                "HAND_OFF_FIXED_HASH_ALLOWLIST_TO_STAGING_EMBEDDING_JOB",
                "GENERATE_DOCUMENT_EMBEDDINGS",
                "WRITE_STAGING_EMBEDDINGS",
                "VERIFY_STAGING_EMBEDDINGS",
            ],
        },
        "gates": {
            "embedding_status": "AUTHORIZED_NOT_STARTED",
            "indexing_status": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
            "external_access_performed": False,
        },
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
        "supersedes_acceptance_version": SUPERSEDES_ACCEPTANCE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "STAGING_EMBEDDING_AUTHORIZED",
        "project_owner_id": acceptance["project_owner_id"],
        "signed_at": acceptance["signed_at"],
        "acceptance_path": ACCEPTANCE_FILENAME,
        "acceptance_sha256": _sha256_file(package / ACCEPTANCE_FILENAME),
        "allowlist_sha256": acceptance["accepted_artifacts"]["allowlist_sha256"],
        "source_count": EXPECTED_SOURCE_COUNT,
        "chunk_count": EXPECTED_CHUNK_COUNT,
        "required_document_input_type": "RETRIEVAL_DOCUMENT",
        "required_dimension": 1024,
        "prior_artifact_lock_sha256": prior_lock_sha256,
        "validation_input_inventory_sha256": validation_inventory_sha256,
        "review_status": "needs_review",
        "indexing_status": "NOT_AUTHORIZED",
        "production_status": "BLOCKED",
        "production_approved": False,
    }


def _validation_report(acceptance: Mapping[str, Any]) -> dict[str, Any]:
    checks = [
        {"name": "prior_acceptance_valid", "status": "PASS"},
        {"name": "prior_acceptance_bytes_locked", "status": "PASS"},
        {"name": "candidate_checksums_verified", "status": "PASS"},
        {"name": "allowlist_fixed_hash_bound", "status": "PASS"},
        {"name": "candidate_source_count_17", "status": "PASS"},
        {"name": "candidate_chunk_count_726", "status": "PASS"},
        {"name": "explicit_owner_authorization_recorded", "status": "PASS"},
        {"name": "typed_signature_identity_matches_owner", "status": "PASS"},
        {"name": "scope_staging_document_embedding_only", "status": "PASS"},
        {"name": "formal_item_review_not_inferred", "status": "PASS"},
        {"name": "indexing_not_authorized", "status": "PASS"},
        {"name": "production_remains_blocked", "status": "PASS"},
        {"name": "external_access_not_performed", "status": "PASS"},
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "acceptance_version": ACCEPTANCE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "PASS",
        "pass_count": len(checks),
        "fail_count": 0,
        "checks": checks,
        "allowlist_sha256": acceptance["accepted_artifacts"]["allowlist_sha256"],
        "source_count": EXPECTED_SOURCE_COUNT,
        "chunk_count": EXPECTED_CHUNK_COUNT,
        "review_status": "needs_review",
        "embedding_status": "AUTHORIZED_NOT_STARTED",
        "indexing_status": "NOT_AUTHORIZED",
        "production_status": "BLOCKED",
        "production_approved": False,
    }


def _readme(acceptance: Mapping[str, Any]) -> str:
    allowlist_sha256 = acceptance["accepted_artifacts"]["allowlist_sha256"]
    return (
        "# Owner staging document-embedding acceptance v002\n\n"
        f"Project owner `{acceptance['project_owner_id']}` signed this acceptance at "
        f"`{acceptance['signed_at']}` through an explicit interactive instruction.\n\n"
        "This typed-name electronic signature authorizes only the fixed-hash candidate "
        "v002 allowlist to be handed to a staging document-embedding job for the internal "
        "emergency demo. It is not a cryptographic signature.\n\n"
        f"- Allowlist SHA-256: `{allowlist_sha256}`\n"
        "- Scope: 17 sources and 726 chunks\n"
        "- Required input type: `RETRIEVAL_DOCUMENT`\n"
        "- Required dimension: `1024`\n"
        "- Formal item-level review evidence remains unrecorded; `review_status` remains "
        "`needs_review`.\n"
        "- Provider profile selection, indexing, retrieval activation, external access, "
        "and Production remain unauthorized.\n\n"
        "Do not edit this v002 acceptance in place. Create another version for revocation, "
        "provider approval, completed review evidence, indexing, or Production decisions.\n"
    )


def _validate_prior_acceptance(root: Path) -> None:
    result = validate_human_review_acceptance(root, root / PRIOR_ACCEPTANCE_PATH)
    if (
        result["status"] != "PASS"
        or result["project_owner_id"] != "IanHsu"
        or result["production_approved"] is not False
    ):
        raise StagingEmbeddingAuthorizationError("prior owner acceptance is invalid")


def _validate_candidate_anchors(root: Path) -> None:
    candidate = root / CANDIDATE_PATH
    _validate_candidate_checksums(candidate)
    allowlist = _read_json(candidate / ALLOWLIST_RELATIVE_PATH)
    if (
        allowlist.get("artifact_version") != CANDIDATE_ARTIFACT_VERSION
        or allowlist.get("source_count") != EXPECTED_SOURCE_COUNT
        or allowlist.get("chunk_count") != EXPECTED_CHUNK_COUNT
        or allowlist.get("status") != "DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE"
        or allowlist.get("allowed_use") != "INTERNAL_EMERGENCY_DEMO_ONLY"
        or allowlist.get("project_owner_risk_acceptance") != "NOT_SIGNED"
        or allowlist.get("human_source_review") != "NOT_COMPLETED"
        or allowlist.get("embedding_status") != "NOT_STARTED"
        or allowlist.get("opensearch_indexing_status") != "NOT_STARTED"
        or allowlist.get("production_status") != "BLOCKED"
    ):
        raise StagingEmbeddingAuthorizationError("candidate allowlist gates are invalid")
    chunk_manifest = _read_json(candidate / CHUNK_MANIFEST_RELATIVE_PATH)
    if (
        chunk_manifest.get("artifact_version") != CANDIDATE_ARTIFACT_VERSION
        or chunk_manifest.get("chunk_file_count") != EXPECTED_SOURCE_COUNT
        or chunk_manifest.get("chunk_count") != EXPECTED_CHUNK_COUNT
    ):
        raise StagingEmbeddingAuthorizationError("candidate chunk manifest is invalid")
    files = chunk_manifest.get("files")
    if not isinstance(files, list) or any(
        item.get("review_status") != "needs_review"
        or item.get("embedding_status") != "not_started"
        or item.get("production_approved") is not False
        for item in files
    ):
        raise StagingEmbeddingAuthorizationError("candidate chunk manifest governance changed")


def _prior_acceptance_entries(root: Path) -> list[dict[str, Any]]:
    package = root / PRIOR_ACCEPTANCE_PATH
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
            "immutable v001 owner acceptance package bytes"
            if kind == "staging_embedding_authorization_prior_artifact_immutable_lock"
            else "staging embedding authorization schema, builder, validator, tests, and README"
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
        raise StagingEmbeddingAuthorizationError(f"{expected_kind} changed after signing")


def _inventory_sha256(entries: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_authorization_schema(
    validator: Draft202012Validator,
    acceptance: Mapping[str, Any],
) -> None:
    try:
        _validate_schema(validator, acceptance, "staging embedding authorization")
    except HumanReviewPackageError as exc:
        raise StagingEmbeddingAuthorizationError(str(exc)) from exc


def _validate_signature_inputs(
    project_owner_id: str,
    signed_at: str,
    authorization_statement: str,
) -> None:
    if project_owner_id != "IanHsu" or not authorization_statement:
        raise StagingEmbeddingAuthorizationError(
            "project owner identity and authorization statement are required"
        )
    try:
        parsed = datetime.fromisoformat(signed_at)
    except ValueError as exc:
        raise StagingEmbeddingAuthorizationError("signed_at must be ISO 8601") from exc
    if parsed.utcoffset() != timedelta(hours=8):
        raise StagingEmbeddingAuthorizationError("signed_at must use the Asia/Taipei +08:00 offset")

"""Build and validate the owner-verified RAG v003 staging successor."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"
CANONICAL_JSON_HASH_MODE = "sha256_canonical_json_v1"
PRIOR_CANDIDATE = Path("data/rag-v2/candidates/v002")
PRIOR_CHUNK_ROOT = PRIOR_CANDIDATE / "chunks"
PRIOR_SOURCE_MANIFEST = PRIOR_CANDIDATE / "manifests/source-manifest-v002.json"
PRIOR_PUBLIC_ACCEPTANCE = Path(
    "data/rag-v3/review/acceptance/v001/owner-public-use-acceptance.json"
)
PRIOR_SOURCE_POLICY = Path(
    "data/rag-v3/governance/source-family-policy/candidates/v001/" "source-family-policy-map.json"
)
ACCEPTANCE_PACKAGE = Path("data/rag-v3/review/acceptance/v002")
ACCEPTANCE_FILE = ACCEPTANCE_PACKAGE / "owner-human-review-acceptance.json"
PREFLIGHT_PACKAGE = Path("data/rag-v3/preflight/v002")
CANDIDATE_PACKAGE = Path("data/rag-v3/candidates/v003")
AUDIT_PREFLIGHT_PACKAGE = Path("data/rag-v3/audits/v001/preflight")
ACCEPTANCE_SCHEMA = Path("contracts/schemas/rag/rag-owner-human-review-acceptance-v1.schema.json")
CHUNK_SCHEMA = Path("contracts/schemas/rag/rag-chunk-v3.1.schema.json")
V2_SCHEMA = Path("contracts/schemas/rag/rag-chunk-v2.1.schema.json")
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
SOURCE_COUNT = 17
CHUNK_COUNT = 726
OFFICIAL_SOURCE_COUNT = 14
OFFICIAL_CHUNK_COUNT = 651
RESEARCH_SOURCE_COUNT = 3
RESEARCH_CHUNK_COUNT = 75

PRIOR_FORMAL_ROOTS = (
    PRIOR_CANDIDATE,
    Path("data/rag-v2/human-review/v001"),
    Path("data/rag-v2/human-review/acceptance/v001"),
    Path("data/rag-v2/human-review/acceptance/v002"),
    Path("data/rag-v3/review/acceptance/v001"),
    Path("data/rag-v3/preflight/v001"),
    Path("data/rag-v3/governance/source-family-policy/preflight/v001"),
    Path("data/rag-v3/governance/source-family-policy/candidates/v001"),
)
VALIDATION_INPUTS = (
    Path("config/rag/embedding-google.yaml"),
    Path("config/rag/staging-filters.yaml"),
    ACCEPTANCE_SCHEMA,
    CHUNK_SCHEMA,
    V2_SCHEMA,
    ACCEPTANCE_FILE,
    Path("scripts/rag/build_v3_verified_candidate.py"),
    Path("scripts/rag/validate_v3_verified_candidate.py"),
    Path("services/rag-ingestion/src/rag_ingestion/v3_verified_candidate.py"),
    Path("services/rag-ingestion/tests/integration/test_v3_verified_candidate.py"),
    Path("services/rag-ingestion/tests/unit/test_rag_chunk_v3_verified_schema.py"),
)
AUDIT_FORMAL_ROOTS = (
    ACCEPTANCE_PACKAGE,
    PREFLIGHT_PACKAGE,
    CANDIDATE_PACKAGE,
)


class V3VerifiedCandidateError(ValueError):
    """Raised when owner evidence, lineage, or verified candidate validation fails."""


@dataclass(frozen=True)
class V3VerifiedSummary:
    artifact: str
    output_path: Path
    source_count: int = SOURCE_COUNT
    chunk_count: int = CHUNK_COUNT
    verified_count: int = CHUNK_COUNT
    inventory_sha256: str | None = None
    prior_lock_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "chunk_count": self.chunk_count,
            "external_sync": "NOT_AUTHORIZED",
            "inventory_sha256": self.inventory_sha256,
            "output_path": self.output_path.as_posix(),
            "prior_lock_sha256": self.prior_lock_sha256,
            "production_approved": False,
            "source_count": self.source_count,
            "status": "PASS",
            "verified_count": self.verified_count,
        }


def build_owner_human_review_acceptance(
    repository_root: Path,
    *,
    project_owner_id: str,
    signed_at: str,
    authorization_statements: Sequence[str],
    output_path: Path | None = None,
) -> V3VerifiedSummary:
    """Record the explicit manual-review decision without granting Production."""

    root = repository_root.resolve()
    package = _resolve_output(root, output_path, ACCEPTANCE_PACKAGE)
    _refuse_overwrite(package)
    statements = _validate_authorization_inputs(
        project_owner_id,
        signed_at,
        authorization_statements,
    )
    _validate_prior_candidate(root)
    acceptance = _acceptance_document(
        root,
        project_owner_id=project_owner_id,
        signed_at=signed_at,
        statements=statements,
    )
    _validate_schema(root / ACCEPTANCE_SCHEMA, acceptance)

    staged = _new_staging_directory(root, "verified-acceptance")
    try:
        _write_json(staged / ACCEPTANCE_FILE.name, acceptance)
        _write_text(staged / "README.md", _acceptance_readme(acceptance))
        acceptance_sha256 = _sha256_file(staged / ACCEPTANCE_FILE.name)
        report = {
            "schema_version": "1.0.0",
            "artifact_version": "v003",
            "acceptance_version": "v002",
            "status": "PASS",
            "checks": [
                {"name": name, "status": "PASS"}
                for name in (
                    "owner_acceptance_schema_valid",
                    "authorization_statements_hash_valid",
                    "prior_candidate_hash_bound",
                    "prior_public_use_acceptance_hash_bound",
                    "prior_source_family_policy_hash_bound",
                    "manual_review_covers_726_chunks",
                    "source_fidelity_verified_by_owner",
                    "exact_facts_verified_by_owner",
                    "source_versions_latest_confirmed_by_owner",
                    "missing_license_url_not_automatic_block",
                    "external_sync_not_authorized",
                    "production_blocked",
                )
            ],
            "pass_count": 12,
            "fail_count": 0,
            "review_status": "verified",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        }
        _write_json(staged / "validation-report.json", report)
        _write_json(
            staged / "manifest.json",
            {
                "schema_version": "1.0.0",
                "artifact_version": "v003",
                "acceptance_version": "v002",
                "acceptance_path": ACCEPTANCE_FILE.name,
                "acceptance_sha256": acceptance_sha256,
                "authorization_statements_sha256": acceptance["authorization"]["statements_sha256"],
                "source_count": SOURCE_COUNT,
                "chunk_count": CHUNK_COUNT,
                "review_status": "verified",
                "external_sync": "NOT_AUTHORIZED",
                "production_status": "BLOCKED",
                "production_approved": False,
            },
        )
        _write_checksums(staged)
        validate_owner_human_review_acceptance(root, staged)
        _publish_directory(staged, package)
    finally:
        _cleanup_staging_directory(root, staged)
    return V3VerifiedSummary("v003_owner_human_review_acceptance", package)


def validate_owner_human_review_acceptance(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    root = repository_root.resolve()
    package = _resolve_output(root, package_path, ACCEPTANCE_PACKAGE)
    _validate_package_checksums(package)
    acceptance_path = package / ACCEPTANCE_FILE.name
    acceptance = _read_json(acceptance_path)
    _validate_schema(root / ACCEPTANCE_SCHEMA, acceptance)
    _validate_prior_candidate(root)
    if acceptance["authorization"]["statements_sha256"] != _canonical_sha256(
        acceptance["authorization"]["statements"]
    ):
        raise V3VerifiedCandidateError("owner authorization statements hash mismatch")
    _assert_acceptance_anchors(root, acceptance)
    if acceptance["review_assertions"]["review_status"] != "verified":
        raise V3VerifiedCandidateError("owner acceptance does not authorize verified status")
    expected_gates = {
        "environment": "STAGING",
        "candidate_build": "AUTHORIZED",
        "external_sync": "NOT_AUTHORIZED",
        "production_status": "BLOCKED",
        "production_approved": False,
    }
    if acceptance["gates"] != expected_gates:
        raise V3VerifiedCandidateError("owner acceptance gates were broadened")
    manifest = _read_json(package / "manifest.json")
    if manifest["acceptance_sha256"] != _sha256_file(acceptance_path):
        raise V3VerifiedCandidateError("acceptance manifest hash mismatch")
    report = _read_json(package / "validation-report.json")
    if report.get("status") != "PASS" or report.get("fail_count") != 0:
        raise V3VerifiedCandidateError("acceptance validation report is not PASS")
    return {
        "acceptance_sha256": manifest["acceptance_sha256"],
        "authorization_statements_sha256": acceptance["authorization"]["statements_sha256"],
        "chunk_count": CHUNK_COUNT,
        "project_owner_id": acceptance["project_owner_id"],
        "review_status": "verified",
        "signed_at": acceptance["signed_at"],
        "source_count": SOURCE_COUNT,
        "status": "PASS",
    }


def build_verified_preflight(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> V3VerifiedSummary:
    """Freeze immutable prior artifacts and every selected verified-build input."""

    root = repository_root.resolve()
    package = _resolve_output(root, output_path, PREFLIGHT_PACKAGE)
    _refuse_overwrite(package)
    validate_owner_human_review_acceptance(root)
    prior_entries = _prior_artifact_entries(root)
    validation_entries = _validation_input_entries(root, prior_entries)
    prior_lock = _inventory_document(
        kind="rag_v3_verified_prior_artifact_lock",
        scope="immutable v002 and v003-v001 formal artifacts",
        entries=prior_entries,
    )
    inventory = _inventory_document(
        kind="rag_v3_verified_validation_input_inventory",
        scope="v003 verified schemas, acceptance, implementation, tests, config, and prior inputs",
        entries=validation_entries,
    )
    staged = _new_staging_directory(root, "verified-preflight")
    try:
        _write_json(staged / "prior-artifact-lock.json", prior_lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _preflight_readme(prior_lock, inventory))
        _write_checksums(staged)
        validate_verified_preflight(root, staged)
        _publish_directory(staged, package)
    finally:
        _cleanup_staging_directory(root, staged)
    return V3VerifiedSummary(
        "v003_verified_preflight",
        package,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=prior_lock["inventory_sha256"],
    )


def validate_verified_preflight(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    root = repository_root.resolve()
    package = _resolve_output(root, package_path, PREFLIGHT_PACKAGE)
    validate_owner_human_review_acceptance(root)
    _validate_package_checksums(package)
    stored_lock = _read_json(package / "prior-artifact-lock.json")
    stored_inventory = _read_json(package / "validation-input-inventory.json")
    prior_entries = _prior_artifact_entries(root)
    current_lock = _inventory_document(
        kind="rag_v3_verified_prior_artifact_lock",
        scope="immutable v002 and v003-v001 formal artifacts",
        entries=prior_entries,
    )
    current_inventory = _inventory_document(
        kind="rag_v3_verified_validation_input_inventory",
        scope="v003 verified schemas, acceptance, implementation, tests, config, and prior inputs",
        entries=_validation_input_entries(root, prior_entries),
    )
    if stored_lock != current_lock:
        raise V3VerifiedCandidateError("prior-artifact immutable lock mismatch")
    if stored_inventory != current_inventory:
        raise V3VerifiedCandidateError("verified validation input inventory mismatch")
    return {
        "chunk_count": CHUNK_COUNT,
        "inventory_entry_count": stored_inventory["entry_count"],
        "inventory_sha256": stored_inventory["inventory_sha256"],
        "prior_artifact_entry_count": stored_lock["entry_count"],
        "prior_lock_sha256": stored_lock["inventory_sha256"],
        "production_approved": False,
        "source_count": SOURCE_COUNT,
        "status": "PASS",
    }


def validate_verified_build_preflight_snapshot(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate the immutable build snapshot without claiming current-input equality."""

    root = repository_root.resolve()
    package = _resolve_output(root, package_path, PREFLIGHT_PACKAGE)
    validate_owner_human_review_acceptance(root)
    _validate_package_checksums(package)
    stored_lock = _read_json(package / "prior-artifact-lock.json")
    stored_inventory = _read_json(package / "validation-input-inventory.json")
    current_lock = _inventory_document(
        kind="rag_v3_verified_prior_artifact_lock",
        scope="immutable v002 and v003-v001 formal artifacts",
        entries=_prior_artifact_entries(root),
    )
    if stored_lock != current_lock:
        raise V3VerifiedCandidateError("build preflight prior-artifact lock mismatch")
    if stored_inventory["inventory_sha256"] != _canonical_sha256(stored_inventory["entries"]):
        raise V3VerifiedCandidateError("build preflight stored inventory digest mismatch")
    return {
        "chunk_count": CHUNK_COUNT,
        "inventory_entry_count": stored_inventory["entry_count"],
        "inventory_sha256": stored_inventory["inventory_sha256"],
        "prior_artifact_entry_count": stored_lock["entry_count"],
        "prior_lock_sha256": stored_lock["inventory_sha256"],
        "production_approved": False,
        "source_count": SOURCE_COUNT,
        "status": "PASS_BUILD_SNAPSHOT",
    }


def build_verified_audit_preflight(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> V3VerifiedSummary:
    """Freeze the immutable candidate and current validator inputs for audit renewal."""

    root = repository_root.resolve()
    package = _resolve_output(root, output_path, AUDIT_PREFLIGHT_PACKAGE)
    _refuse_overwrite(package)
    validate_verified_candidate(root, require_current_audit=False)
    candidate_entries = _artifact_entries(root, AUDIT_FORMAL_ROOTS)
    validation_entries = _validation_input_entries(root, candidate_entries)
    candidate_lock = _inventory_document(
        kind="rag_v3_verified_candidate_immutable_lock",
        scope="verified v003 candidate, owner acceptance, and build preflight",
        entries=candidate_entries,
    )
    inventory = _inventory_document(
        kind="rag_v3_verified_audit_validation_input_inventory",
        scope="current schemas, validator, tests, config, and immutable v003 candidate",
        entries=validation_entries,
    )
    staged = _new_staging_directory(root, "verified-audit-preflight")
    try:
        _write_json(staged / "candidate-artifact-lock.json", candidate_lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _audit_preflight_readme(candidate_lock, inventory))
        _write_checksums(staged)
        validate_verified_audit_preflight(root, staged)
        _publish_directory(staged, package)
    finally:
        _cleanup_staging_directory(root, staged)
    return V3VerifiedSummary(
        "v003_verified_audit_preflight",
        package,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=candidate_lock["inventory_sha256"],
    )


def validate_verified_audit_preflight(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    root = repository_root.resolve()
    package = _resolve_output(root, package_path, AUDIT_PREFLIGHT_PACKAGE)
    _validate_package_checksums(package)
    stored_lock = _read_json(package / "candidate-artifact-lock.json")
    stored_inventory = _read_json(package / "validation-input-inventory.json")
    candidate_entries = _artifact_entries(root, AUDIT_FORMAL_ROOTS)
    current_lock = _inventory_document(
        kind="rag_v3_verified_candidate_immutable_lock",
        scope="verified v003 candidate, owner acceptance, and build preflight",
        entries=candidate_entries,
    )
    current_inventory = _inventory_document(
        kind="rag_v3_verified_audit_validation_input_inventory",
        scope="current schemas, validator, tests, config, and immutable v003 candidate",
        entries=_validation_input_entries(root, candidate_entries),
    )
    if stored_lock != current_lock:
        raise V3VerifiedCandidateError("verified candidate immutable lock mismatch")
    if stored_inventory != current_inventory:
        raise V3VerifiedCandidateError("verified audit validation input inventory mismatch")
    return {
        "candidate_artifact_entry_count": stored_lock["entry_count"],
        "candidate_lock_sha256": stored_lock["inventory_sha256"],
        "chunk_count": CHUNK_COUNT,
        "inventory_entry_count": stored_inventory["entry_count"],
        "inventory_sha256": stored_inventory["inventory_sha256"],
        "production_approved": False,
        "source_count": SOURCE_COUNT,
        "status": "PASS",
    }


def build_verified_candidate(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> V3VerifiedSummary:
    """Create the 726-row verified v003 successor after acceptance and preflight pass."""

    root = repository_root.resolve()
    package = _resolve_output(root, output_path, CANDIDATE_PACKAGE)
    _refuse_overwrite(package)
    acceptance_result = validate_owner_human_review_acceptance(root)
    preflight_result = validate_verified_preflight(root)
    acceptance = _read_json(root / ACCEPTANCE_FILE)
    prior_manifest = _read_json(root / PRIOR_SOURCE_MANIFEST)
    validator = _chunk_validator(root)
    staged = _new_staging_directory(root, "verified-candidate")
    source_rows: dict[str, list[dict[str, Any]]] = {}
    review_rows: list[dict[str, Any]] = []
    crosswalk_rows: list[dict[str, Any]] = []
    prior_by_id: dict[str, dict[str, Any]] = {}
    try:
        for source in prior_manifest["sources"]:
            source_id = source["source_id"]
            prior_path = root / PRIOR_CHUNK_ROOT / f"{source_id}.rag-chunk-v2.v002.jsonl"
            prior_records = _read_jsonl(prior_path)
            successors: list[dict[str, Any]] = []
            for prior in prior_records:
                successor = promote_record(prior, acceptance, acceptance_result)
                errors = sorted(
                    validator.iter_errors(successor), key=lambda error: list(error.absolute_path)
                )
                if errors:
                    raise V3VerifiedCandidateError(
                        f"v003 chunk schema failed for {successor['identity']['chunk_id']}: "
                        f"{errors[0].message}"
                    )
                successors.append(successor)
                prior_id = prior["identity"]["chunk_id"]
                prior_by_id[prior_id] = prior
                review_rows.append(_review_row(successor, acceptance_result))
                crosswalk_rows.append(_crosswalk_row(prior, successor))
            source_rows[source_id] = successors
            output_name = f"{source_id}.rag-chunk-v3.v003.jsonl"
            _write_jsonl(staged / "chunks" / output_name, successors)

        _write_jsonl(staged / "review/human-review-decisions-v003.jsonl", review_rows)
        _write_jsonl(staged / "crosswalk/chunk-id-crosswalk-v003.jsonl", crosswalk_rows)
        source_manifest = _source_manifest(staged, prior_manifest, source_rows, acceptance_result)
        chunk_manifest = _chunk_file_manifest(staged, source_rows, acceptance_result)
        _write_json(staged / "manifests/source-manifest-v003.json", source_manifest)
        _write_json(staged / "manifests/chunk-file-manifest-v003.json", chunk_manifest)
        diff_summary = _version_difference_summary(source_rows, prior_by_id)
        _write_json(staged / "reports/version-difference-summary-v003.json", diff_summary)
        validation_report = _candidate_validation_report(
            source_rows,
            acceptance_result,
            preflight_result,
        )
        _write_json(staged / "reports/validation-report-v003.json", validation_report)
        _write_text(staged / "README.md", _candidate_readme(validation_report))
        _write_checksums(staged)
        validate_verified_candidate(
            root,
            staged,
            prior_by_id=prior_by_id,
            require_current_audit=False,
        )
        _publish_directory(staged, package)
    finally:
        _cleanup_staging_directory(root, staged)
    return V3VerifiedSummary("v003_verified_candidate", package)


def validate_verified_candidate(
    repository_root: Path,
    package_path: Path | None = None,
    *,
    prior_by_id: Mapping[str, Mapping[str, Any]] | None = None,
    require_current_audit: bool = True,
) -> dict[str, Any]:
    root = repository_root.resolve()
    package = _resolve_output(root, package_path, CANDIDATE_PACKAGE)
    acceptance = validate_owner_human_review_acceptance(root)
    preflight = validate_verified_build_preflight_snapshot(root)
    _validate_package_checksums(package)
    validator = _chunk_validator(root)
    prior_records = dict(prior_by_id or _prior_records_by_id(root))
    chunk_files = sorted((package / "chunks").glob("*.jsonl"))
    if len(chunk_files) != SOURCE_COUNT:
        raise V3VerifiedCandidateError("verified candidate must contain 17 chunk files")
    records: list[dict[str, Any]] = []
    for path in chunk_files:
        file_records = _read_jsonl(path)
        indexes = [record["identity"]["chunk_index"] for record in file_records]
        if indexes != list(range(1, len(file_records) + 1)):
            raise V3VerifiedCandidateError(f"non-continuous chunk indexes: {path.name}")
        for record in file_records:
            validator.validate(record)
            _validate_successor_record(record, prior_records, acceptance)
        records.extend(file_records)
    if len(records) != CHUNK_COUNT:
        raise V3VerifiedCandidateError("verified candidate must contain 726 chunks")
    chunk_ids = [record["identity"]["chunk_id"] for record in records]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise V3VerifiedCandidateError("duplicate v003 chunk IDs")
    if any(record["governance"]["review_status"] != "verified" for record in records):
        raise V3VerifiedCandidateError("not every v003 chunk is verified")
    if any(record["governance"]["production_approved"] is not False for record in records):
        raise V3VerifiedCandidateError("verified candidate broadened Production approval")

    reviews = _read_jsonl(package / "review/human-review-decisions-v003.jsonl")
    crosswalk = _read_jsonl(package / "crosswalk/chunk-id-crosswalk-v003.jsonl")
    if len(reviews) != CHUNK_COUNT or len(crosswalk) != CHUNK_COUNT:
        raise V3VerifiedCandidateError("review or crosswalk coverage is incomplete")
    if {row["chunk_id"] for row in reviews} != set(chunk_ids):
        raise V3VerifiedCandidateError("review decision IDs do not match chunks")
    if {row["successor_chunk_id"] for row in crosswalk} != set(chunk_ids):
        raise V3VerifiedCandidateError("crosswalk successor IDs do not match chunks")

    source_manifest = _read_json(package / "manifests/source-manifest-v003.json")
    chunk_manifest = _read_json(package / "manifests/chunk-file-manifest-v003.json")
    if (
        source_manifest["source_count"] != SOURCE_COUNT
        or source_manifest["chunk_count"] != CHUNK_COUNT
    ):
        raise V3VerifiedCandidateError("source manifest counts are invalid")
    if chunk_manifest["file_count"] != SOURCE_COUNT or chunk_manifest["chunk_count"] != CHUNK_COUNT:
        raise V3VerifiedCandidateError("chunk manifest counts are invalid")
    for item in chunk_manifest["files"]:
        chunk_path = package / item["path"]
        if _sha256_file(chunk_path) != item["sha256"]:
            raise V3VerifiedCandidateError(f"chunk manifest hash mismatch: {item['path']}")

    report = _read_json(package / "reports/validation-report-v003.json")
    if report.get("status") != "PASS" or report.get("fail_count") != 0:
        raise V3VerifiedCandidateError("candidate validation report is not PASS")
    if report.get("verified_chunk_count") != CHUNK_COUNT:
        raise V3VerifiedCandidateError("candidate validation report count mismatch")
    audit = (
        validate_verified_audit_preflight(root)
        if require_current_audit
        else {
            "inventory_sha256": None,
            "status": "NOT_REQUIRED_DURING_ATOMIC_CANDIDATE_BUILD",
        }
    )
    return {
        "audit_inventory_sha256": audit["inventory_sha256"],
        "chunk_count": CHUNK_COUNT,
        "current_chunk_count": sum(
            record["governance"]["current_status"] == "current" for record in records
        ),
        "production_approved": False,
        "review_status": "verified",
        "source_count": SOURCE_COUNT,
        "status": "PASS",
        "superseded_chunk_count": sum(
            record["governance"]["current_status"] == "superseded" for record in records
        ),
        "build_validation_inventory_sha256": preflight["inventory_sha256"],
        "verified_count": CHUNK_COUNT,
    }


def promote_record(
    prior: Mapping[str, Any],
    acceptance: Mapping[str, Any],
    acceptance_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply only the explicit owner-reviewed v003 metadata transition."""

    successor = copy.deepcopy(prior)
    identity = successor["identity"]
    governance = successor["governance"]
    provenance = successor["provenance"]
    policy = successor["retrieval_policy"]
    content = successor["content"]
    source_id = identity["source_id"]
    chunk_index = identity["chunk_index"]
    prior_chunk_id = identity["chunk_id"]
    prior_chunk_file_id = identity["chunk_file_id"]

    successor["schema_version"] = "3.1.0"
    successor["artifact_version"] = "v003"
    identity["prior_chunk_id"] = prior_chunk_id
    identity["prior_chunk_file_id"] = prior_chunk_file_id
    identity["chunk_id"] = f"{source_id}_rag_v3_v003_{chunk_index:04d}"
    identity["chunk_file_id"] = f"{source_id}_rag_v3_v003"

    is_official = provenance["is_official_source"] is True
    governance["review_status"] = "verified"
    if governance["current_status"] == "unknown":
        governance["current_status"] = "current"
    if is_official:
        governance["version_check_status"] = "verified_official_source"
    governance["embedding_status"] = "reuse_verified"
    governance["ingestion_status"] = "staging"
    governance["human_source_review"] = "owner_manual_review_completed"
    governance["production_gate"] = "blocked"
    governance["production_approved"] = False
    governance["data_classification"] = "public"
    governance["distribution_scope"] = "public_knowledge" if is_official else "research_evidence"
    governance["storage_target"] = "local_pending_upload"
    provenance["last_verified_at"] = acceptance["signed_at"][:10]

    blockers = list(policy["retrieval_block_reasons"])
    if governance["current_status"] == "current":
        blockers = [reason for reason in blockers if reason != "current_status_not_current"]
    elif "current_status_not_current" not in blockers:
        blockers.append("current_status_not_current")
    policy["retrieval_block_reasons"] = blockers
    policy["retrieval_eligible"] = not blockers

    successor["review_evidence"] = {
        "acceptance_id": "rag-v3-owner-human-review-v002",
        "acceptance_path": ACCEPTANCE_FILE.as_posix(),
        "acceptance_sha256": acceptance_result["acceptance_sha256"],
        "scope": "ALL_726_CHUNKS_HUMAN_REVIEW",
        "decision": "VERIFIED",
        "reviewer_id": acceptance["project_owner_id"],
        "reviewer_role": "PROJECT_OWNER",
        "reviewed_at": acceptance["signed_at"],
        "authorization_statements_sha256": acceptance_result["authorization_statements_sha256"],
        "source_fidelity": "VERIFIED_BY_PROJECT_OWNER",
        "exact_facts": "VERIFIED_BY_PROJECT_OWNER",
        "source_versions": "LATEST_AVAILABLE_CONFIRMED_BY_PROJECT_OWNER",
        "production_approved": False,
    }
    successor["embedding_reuse"] = {
        "status": "REUSE_VERIFIED",
        "source_release_id": "rag-v2-v002-bab68588963b",
        "source_artifact_version": "v002",
        "source_chunk_id": prior_chunk_id,
        "match_key": "embedding_text_sha256",
        "source_embedding_text_sha256": content["embedding_text_sha256"],
        "embedding_profile_id": "ep-google-00a12ec45096fa9d97d9e9b6",
        "provider": "google",
        "model_id": "gemini-embedding-001",
        "dimension": 1024,
        "document_task_type": "RETRIEVAL_DOCUMENT",
    }
    return successor


def _acceptance_document(
    root: Path,
    *,
    project_owner_id: str,
    signed_at: str,
    statements: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "acceptance_version": "v002",
        "candidate_artifact_version": "v003",
        "status": "SIGNED",
        "project_owner_id": project_owner_id,
        "signer_role": "PROJECT_OWNER",
        "signed_at": signed_at,
        "authorization": {
            "channel": "interactive_user_instruction",
            "statements": list(statements),
            "statements_sha256": _canonical_sha256(list(statements)),
        },
        "electronic_signature": {
            "assurance": "RECORDED_EXPLICIT_USER_AUTHORIZATION",
            "signature_value": project_owner_id,
            "intent": "AUTHORIZE_V003_726_CHUNK_HUMAN_REVIEW",
            "cryptographic_signature": None,
        },
        "accepted_artifacts": {
            "prior_candidate_path": PRIOR_CANDIDATE.as_posix(),
            "prior_candidate_checksums_sha256": _sha256_file(
                root / PRIOR_CANDIDATE / "SHA256SUMS.txt"
            ),
            "prior_public_use_acceptance_path": PRIOR_PUBLIC_ACCEPTANCE.as_posix(),
            "prior_public_use_acceptance_sha256": _sha256_file(root / PRIOR_PUBLIC_ACCEPTANCE),
            "prior_source_family_policy_path": PRIOR_SOURCE_POLICY.as_posix(),
            "prior_source_family_policy_sha256": _sha256_file(root / PRIOR_SOURCE_POLICY),
            "source_count": SOURCE_COUNT,
            "chunk_count": CHUNK_COUNT,
            "official_source_count": OFFICIAL_SOURCE_COUNT,
            "official_chunk_count": OFFICIAL_CHUNK_COUNT,
            "research_source_count": RESEARCH_SOURCE_COUNT,
            "research_chunk_count": RESEARCH_CHUNK_COUNT,
        },
        "review_assertions": {
            "review_method": "MANUAL_PROJECT_OWNER_REVIEW",
            "source_fidelity_verified": True,
            "exact_facts_verified": True,
            "source_versions_latest_confirmed": True,
            "reviewed_chunk_count": CHUNK_COUNT,
            "review_status": "verified",
        },
        "version_status_decision": {
            "promote_unknown_current_status": True,
            "preserve_explicit_superseded": True,
            "official_version_check_status": "verified_official_source",
            "research_version_check_status": "pending",
        },
        "license_policy_decision": {
            "source_party_public_use_review_completed": True,
            "missing_license_url_automatic_block": False,
            "affected_source_count": 13,
            "license_status_mutation_authorized": False,
        },
        "gates": {
            "environment": "STAGING",
            "candidate_build": "AUTHORIZED",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _validate_successor_record(
    record: Mapping[str, Any],
    prior_records: Mapping[str, Mapping[str, Any]],
    acceptance: Mapping[str, Any],
) -> None:
    prior_id = record["identity"]["prior_chunk_id"]
    prior = prior_records.get(prior_id)
    if prior is None:
        raise V3VerifiedCandidateError(f"missing prior chunk: {prior_id}")
    for field in ("content", "citation"):
        if record[field] != prior[field]:
            raise V3VerifiedCandidateError(f"source field changed for {prior_id}: {field}")
    prior_provenance = dict(prior["provenance"])
    successor_provenance = dict(record["provenance"])
    prior_provenance["last_verified_at"] = acceptance["signed_at"][:10]
    if successor_provenance != prior_provenance:
        raise V3VerifiedCandidateError(f"unexpected provenance change for {prior_id}")
    for field in (
        "allowed_audiences",
        "allowed_purposes",
        "risk_level",
        "requires_official_assessment",
        "requires_professional_assessment",
        "requires_human_review",
        "stop_normal_rag",
    ):
        if record["retrieval_policy"][field] != prior["retrieval_policy"][field]:
            raise V3VerifiedCandidateError(f"retrieval policy changed for {prior_id}: {field}")
    if record["governance"]["license_status"] != prior["governance"]["license_status"]:
        raise V3VerifiedCandidateError(f"license status changed without authorization: {prior_id}")
    if prior["governance"]["current_status"] == "superseded":
        if record["governance"]["current_status"] != "superseded":
            raise V3VerifiedCandidateError(f"superseded status was not preserved: {prior_id}")
    elif record["governance"]["current_status"] != "current":
        raise V3VerifiedCandidateError(f"owner-confirmed current status missing: {prior_id}")
    if record["content"]["char_count"] != len(record["content"]["text"]):
        raise V3VerifiedCandidateError(f"char_count mismatch: {prior_id}")
    if record["content"]["text_sha256"] != _sha256_text(record["content"]["text"]):
        raise V3VerifiedCandidateError(f"text hash mismatch: {prior_id}")
    if record["content"]["embedding_text_sha256"] != _sha256_text(
        record["content"]["embedding_text"]
    ):
        raise V3VerifiedCandidateError(f"embedding text hash mismatch: {prior_id}")
    if record["review_evidence"]["acceptance_sha256"] != acceptance["acceptance_sha256"]:
        raise V3VerifiedCandidateError(f"acceptance hash mismatch: {prior_id}")


def _source_manifest(
    staged: Path,
    prior_manifest: Mapping[str, Any],
    source_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    acceptance: Mapping[str, Any],
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = []
    for prior_source in prior_manifest["sources"]:
        source_id = prior_source["source_id"]
        rows = source_rows[source_id]
        path = staged / "chunks" / f"{source_id}.rag-chunk-v3.v003.jsonl"
        current_counts = Counter(row["governance"]["current_status"] for row in rows)
        version_counts = Counter(row["governance"]["version_check_status"] for row in rows)
        sources.append(
            {
                **prior_source,
                "artifact_version": "v003",
                "schema_version": "3.1.0",
                "prior_chunk_file_path": (
                    PRIOR_CHUNK_ROOT / f"{source_id}.rag-chunk-v2.v002.jsonl"
                ).as_posix(),
                "chunk_file_path": f"chunks/{path.name}",
                "chunk_file_sha256": _sha256_file(path),
                "current_status_counts": dict(sorted(current_counts.items())),
                "version_check_status_counts": dict(sorted(version_counts.items())),
                "source_versions_latest_confirmed_by_owner": True,
                "review_status": "verified",
                "human_source_review": "owner_manual_review_completed",
                "reviewed_at": acceptance["signed_at"],
                "reviewer_id": acceptance["project_owner_id"],
                "ingestion_status": "staging",
                "production_approved": False,
                "storage_target": "local_pending_upload",
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "review_status": "verified",
        "acceptance_path": ACCEPTANCE_FILE.as_posix(),
        "acceptance_sha256": acceptance["acceptance_sha256"],
        "sources": sources,
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _chunk_file_manifest(
    staged: Path,
    source_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    acceptance: Mapping[str, Any],
) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for source_id in sorted(source_rows):
        rows = source_rows[source_id]
        relative = Path("chunks") / f"{source_id}.rag-chunk-v3.v003.jsonl"
        files.append(
            {
                "source_id": source_id,
                "chunk_file_id": rows[0]["identity"]["chunk_file_id"],
                "prior_chunk_file_id": rows[0]["identity"]["prior_chunk_file_id"],
                "path": relative.as_posix(),
                "chunk_count": len(rows),
                "chunk_size_target": 600,
                "schema_version": "3.1.0",
                "sha256": _sha256_file(staged / relative),
                "review_status": "verified",
                "embedding_status": "reuse_verified",
                "ingestion_status": "staging",
                "production_approved": False,
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "file_count": len(files),
        "chunk_count": sum(item["chunk_count"] for item in files),
        "review_status": "verified",
        "acceptance_path": ACCEPTANCE_FILE.as_posix(),
        "acceptance_sha256": acceptance["acceptance_sha256"],
        "files": files,
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _review_row(record: Mapping[str, Any], acceptance: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "source_id": record["identity"]["source_id"],
        "chunk_id": record["identity"]["chunk_id"],
        "prior_chunk_id": record["identity"]["prior_chunk_id"],
        "decision": "VERIFIED",
        "review_status": "verified",
        "reviewer_id": acceptance["project_owner_id"],
        "reviewer_role": "PROJECT_OWNER",
        "reviewed_at": acceptance["signed_at"],
        "acceptance_path": ACCEPTANCE_FILE.as_posix(),
        "acceptance_sha256": acceptance["acceptance_sha256"],
        "production_approved": False,
    }


def _crosswalk_row(prior: Mapping[str, Any], successor: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "source_id": successor["identity"]["source_id"],
        "prior_chunk_id": prior["identity"]["chunk_id"],
        "successor_chunk_id": successor["identity"]["chunk_id"],
        "relationship": "metadata_review_successor",
        "text_sha256": successor["content"]["text_sha256"],
        "embedding_text_sha256": successor["content"]["embedding_text_sha256"],
        "text_unchanged": True,
        "embedding_text_unchanged": True,
        "review_status_transition": "needs_review_to_verified",
        "production_approved": False,
    }


def _version_difference_summary(
    source_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    prior_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows = [row for source in source_rows.values() for row in source]
    prior_rows = [prior_by_id[row["identity"]["prior_chunk_id"]] for row in rows]
    blockers = Counter(
        reason for row in rows for reason in row["retrieval_policy"]["retrieval_block_reasons"]
    )
    return {
        "schema_version": "1.0.0",
        "prior_artifact_version": "v002",
        "successor_artifact_version": "v003",
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "text_changed_count": 0,
        "embedding_text_changed_count": 0,
        "review_status_changed_count": CHUNK_COUNT,
        "unknown_to_current_count": sum(
            prior["governance"]["current_status"] == "unknown"
            and successor["governance"]["current_status"] == "current"
            for prior, successor in zip(prior_rows, rows, strict=True)
        ),
        "explicit_superseded_preserved_count": sum(
            prior["governance"]["current_status"] == "superseded"
            and successor["governance"]["current_status"] == "superseded"
            for prior, successor in zip(prior_rows, rows, strict=True)
        ),
        "official_version_check_verified_count": sum(
            row["provenance"]["is_official_source"] is True
            and row["governance"]["version_check_status"] == "verified_official_source"
            for row in rows
        ),
        "license_status_changed_count": 0,
        "risk_level_changed_count": 0,
        "assessment_field_changed_count": 0,
        "stop_normal_rag_changed_count": 0,
        "remaining_retrieval_block_reason_counts": dict(sorted(blockers.items())),
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _candidate_validation_report(
    source_rows: Mapping[str, Sequence[Mapping[str, Any]]],
    acceptance: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    rows = [row for source in source_rows.values() for row in source]
    missing_risk = sum(row["retrieval_policy"]["risk_level"] is None for row in rows)
    missing_official = sum(
        row["retrieval_policy"]["requires_official_assessment"] is None for row in rows
    )
    missing_professional = sum(
        row["retrieval_policy"]["requires_professional_assessment"] is None for row in rows
    )
    empty_audiences = sum(not row["retrieval_policy"]["allowed_audiences"] for row in rows)
    empty_purposes = sum(not row["retrieval_policy"]["allowed_purposes"] for row in rows)
    checks = (
        "prior_artifact_lock_valid",
        "validation_input_inventory_valid",
        "owner_manual_review_acceptance_valid",
        "source_count_17",
        "chunk_count_726",
        "review_status_verified_726",
        "source_text_unchanged_726",
        "embedding_text_unchanged_726",
        "content_hashes_valid_726",
        "chunk_ids_unique_and_indexes_continuous",
        "lineage_complete_726",
        "review_decisions_complete_726",
        "explicit_superseded_preserved",
        "license_statuses_preserved",
        "risk_assessment_and_stop_fields_preserved",
        "embedding_reuse_hash_bound_726",
        "external_sync_not_authorized",
        "production_blocked",
    )
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "status": "PASS",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "verified_chunk_count": CHUNK_COUNT,
        "current_chunk_count": sum(
            row["governance"]["current_status"] == "current" for row in rows
        ),
        "superseded_chunk_count": sum(
            row["governance"]["current_status"] == "superseded" for row in rows
        ),
        "retrieval_eligible_count": sum(
            row["retrieval_policy"]["retrieval_eligible"] is True for row in rows
        ),
        "remaining_governance_gaps": {
            "risk_level_null": missing_risk,
            "requires_official_assessment_null": missing_official,
            "requires_professional_assessment_null": missing_professional,
            "allowed_audiences_empty": empty_audiences,
            "allowed_purposes_empty": empty_purposes,
        },
        "acceptance_sha256": acceptance["acceptance_sha256"],
        "validation_inventory_sha256": preflight["inventory_sha256"],
        "external_sync": "NOT_AUTHORIZED",
        "production_status": "BLOCKED",
        "production_approved": False,
    }


def _acceptance_readme(acceptance: Mapping[str, Any]) -> str:
    return (
        "# RAG v003 owner human-review acceptance v002\n\n"
        f"Project owner `{acceptance['project_owner_id']}` recorded completion of manual review "
        f"for all 726 chunks at `{acceptance['signed_at']}`. The exact interactive statements "
        f"are bound as `{acceptance['authorization']['statements_sha256']}` using "
        f"`{CANONICAL_JSON_HASH_MODE}`.\n\n"
        "This acceptance authorizes a local v003 staging successor with "
        "`review_status=verified`. It records source-fidelity, exact-fact, and latest-source "
        "review by the project owner. It also records that a missing license URL is not an "
        "automatic blocker, while preserving existing license-status values for a separate "
        "policy update.\n\n"
        "External synchronization and Production remain unauthorized. Do not edit this package "
        "in place.\n"
    )


def _preflight_readme(lock: Mapping[str, Any], inventory: Mapping[str, Any]) -> str:
    return (
        "# RAG v003 verified successor preflight v002\n\n"
        "This package locks every selected v002 and v003-v001 formal artifact before the "
        "owner-verified v003 successor is created. It also freezes the verified acceptance, "
        "schemas, implementation, tests, and retrieval configuration.\n\n"
        f"- Prior artifact entries: `{lock['entry_count']}`\n"
        f"- Prior lock SHA-256: `{lock['inventory_sha256']}`\n"
        f"- Validation input entries: `{inventory['entry_count']}`\n"
        f"- Validation inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        "- Sources/chunks: `17` / `726`\n"
        "- Intended review status: `verified`\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n\n"
        "Any selected-byte change invalidates this package. Do not edit v002 in place.\n"
    )


def _audit_preflight_readme(lock: Mapping[str, Any], inventory: Mapping[str, Any]) -> str:
    return (
        "# RAG v003 verified candidate audit preflight v001\n\n"
        "This audit-renewal package locks the immutable v003 candidate, its owner acceptance, "
        "and its build-time preflight. It separately freezes the current schemas, validator, "
        "tests, and retrieval configuration so later formatting or validator maintenance does "
        "not rewrite the candidate or pretend its original build inventory is current.\n\n"
        f"- Candidate artifact entries: `{lock['entry_count']}`\n"
        f"- Candidate lock SHA-256: `{lock['inventory_sha256']}`\n"
        f"- Current validation input entries: `{inventory['entry_count']}`\n"
        f"- Current validation inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        "- Sources/chunks: `17` / `726`\n"
        "- Review status: `verified`\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n\n"
        "Any selected-byte change requires a new audit version. Do not edit v001 in place.\n"
    )


def _candidate_readme(report: Mapping[str, Any]) -> str:
    gaps = report["remaining_governance_gaps"]
    return (
        "# RAG v003 verified local candidate\n\n"
        "This immutable local staging successor records the project owner's completed manual "
        "review for all 726 chunks. Source text and embedding text are unchanged from v002; "
        "lineage, review evidence, and embedding-reuse evidence are explicit per chunk.\n\n"
        "- Sources/chunks: `17` / `726`\n"
        "- `review_status=verified`: `726`\n"
        f"- Current/superseded: `{report['current_chunk_count']}` / "
        f"`{report['superseded_chunk_count']}`\n"
        f"- Retrieval eligible after version-status reconciliation: "
        f"`{report['retrieval_eligible_count']}`\n"
        f"- Remaining null risk/official assessment/professional assessment: "
        f"`{gaps['risk_level_null']}` / `{gaps['requires_official_assessment_null']}` / "
        f"`{gaps['requires_professional_assessment_null']}`\n"
        f"- Remaining empty audience/purpose: `{gaps['allowed_audiences_empty']}` / "
        f"`{gaps['allowed_purposes_empty']}`\n"
        "- External synchronization: not performed\n"
        "- Production: blocked\n\n"
        "This package does not apply the five risk classifications, the 27 stop-normal-RAG "
        "corrections, the remaining governance-field decisions, source-family policy v002, "
        "Golden Query tests, or a staging release cutover.\n"
    )


def _validate_prior_candidate(root: Path) -> None:
    package = root / PRIOR_CANDIDATE
    checksums = _parse_checksums(package / "SHA256SUMS.txt")
    actual = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    if set(checksums) != actual:
        raise V3VerifiedCandidateError("v002 checksum inventory mismatch")
    for relative, expected in checksums.items():
        if _sha256_file(package / relative) != expected:
            raise V3VerifiedCandidateError(f"v002 checksum mismatch: {relative}")
    manifest = _read_json(root / PRIOR_SOURCE_MANIFEST)
    if manifest["source_count"] != SOURCE_COUNT or manifest["chunk_count"] != CHUNK_COUNT:
        raise V3VerifiedCandidateError("v002 source/chunk counts changed")


def _assert_acceptance_anchors(root: Path, acceptance: Mapping[str, Any]) -> None:
    anchors = acceptance["accepted_artifacts"]
    expected = {
        "prior_candidate_checksums_sha256": _sha256_file(root / PRIOR_CANDIDATE / "SHA256SUMS.txt"),
        "prior_public_use_acceptance_sha256": _sha256_file(root / PRIOR_PUBLIC_ACCEPTANCE),
        "prior_source_family_policy_sha256": _sha256_file(root / PRIOR_SOURCE_POLICY),
    }
    for key, value in expected.items():
        if anchors.get(key) != value:
            raise V3VerifiedCandidateError(f"owner acceptance anchor mismatch: {key}")


def _chunk_validator(root: Path) -> Draft202012Validator:
    v2_schema = _read_json(root / V2_SCHEMA)
    schema = _read_json(root / CHUNK_SCHEMA)
    Draft202012Validator.check_schema(schema)
    registry = Registry().with_resource(v2_schema["$id"], Resource.from_contents(v2_schema))
    return Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())


def _validate_schema(path: Path, payload: Mapping[str, Any]) -> None:
    schema = _read_json(path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
    if errors:
        raise V3VerifiedCandidateError(
            f"schema validation failed for {path.name}: {errors[0].message}"
        )


def _prior_records_by_id(root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for path in sorted((root / PRIOR_CHUNK_ROOT).glob("*.jsonl")):
        for record in _read_jsonl(path):
            chunk_id = record["identity"]["chunk_id"]
            if chunk_id in records:
                raise V3VerifiedCandidateError(f"duplicate prior chunk ID: {chunk_id}")
            records[chunk_id] = record
    if len(records) != CHUNK_COUNT:
        raise V3VerifiedCandidateError("prior chunk inventory must contain 726 rows")
    return records


def _prior_artifact_entries(root: Path) -> list[dict[str, Any]]:
    return _artifact_entries(root, PRIOR_FORMAL_ROOTS)


def _artifact_entries(root: Path, roots: Sequence[Path]) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for relative_root in roots:
        absolute = root / relative_root
        if not absolute.is_dir():
            raise V3VerifiedCandidateError(f"prior artifact root missing: {relative_root}")
        paths.extend(path for path in absolute.rglob("*") if path.is_file())
    return [_file_entry(root, path) for path in sorted(set(paths), key=lambda p: p.as_posix())]


def _validation_input_entries(
    root: Path,
    prior_entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    entries = {str(item["path"]): dict(item) for item in prior_entries}
    for relative in VALIDATION_INPUTS:
        path = root / relative
        if not path.is_file():
            raise V3VerifiedCandidateError(f"validation input missing: {relative}")
        entries[relative.as_posix()] = _file_entry(root, path)
    return [entries[key] for key in sorted(entries)]


def _file_entry(root: Path, path: Path) -> dict[str, Any]:
    raw = _read_lf_utf8_bytes(path)
    relative = path.relative_to(root).as_posix()
    return {
        "path": relative,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "hash_mode": HASH_MODE,
    }


def _inventory_document(
    *,
    kind: str,
    scope: str,
    entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    values = list(entries)
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "preflight_version": "v002",
        "kind": kind,
        "scope": scope,
        "hash_mode": HASH_MODE,
        "inventory_hash_mode": CANONICAL_JSON_HASH_MODE,
        "entry_count": len(values),
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "inventory_sha256": _canonical_sha256(values),
        "entries": values,
        "review_status": "verified",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validate_authorization_inputs(
    project_owner_id: str,
    signed_at: str,
    statements: Sequence[str],
) -> tuple[str, ...]:
    if not IDENTIFIER_PATTERN.fullmatch(project_owner_id):
        raise V3VerifiedCandidateError("project owner ID is invalid")
    parsed = datetime.fromisoformat(signed_at)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise V3VerifiedCandidateError("signed_at must include a timezone offset")
    normalized = tuple(statement.strip() for statement in statements)
    if not normalized or any(not item or len(item) > 1024 for item in normalized):
        raise V3VerifiedCandidateError("authorization statements are invalid")
    return normalized


def _resolve_output(root: Path, output: Path | None, default: Path) -> Path:
    if output is None:
        return (root / default).resolve()
    return output.resolve()


def _refuse_overwrite(path: Path) -> None:
    if path.exists():
        raise V3VerifiedCandidateError(f"refuse to overwrite versioned artifact: {path}")


def _new_staging_directory(root: Path, label: str) -> Path:
    parent = root.parent.resolve()
    staged = Path(tempfile.mkdtemp(prefix=f".kinsun-rag-v3-{label}-", dir=parent)).resolve()
    if staged.parent != parent or not staged.name.startswith(f".kinsun-rag-v3-{label}-"):
        raise V3VerifiedCandidateError("unsafe staging directory")
    return staged


def _publish_directory(staged: Path, destination: Path) -> None:
    _refuse_overwrite(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(destination)


def _cleanup_staging_directory(root: Path, staged: Path) -> None:
    resolved = staged.resolve()
    if not resolved.exists():
        return
    parent = root.parent.resolve()
    if resolved.parent != parent or not resolved.name.startswith(".kinsun-rag-v3-"):
        raise V3VerifiedCandidateError("refuse to clean unsafe staging directory")
    shutil.rmtree(resolved)


def _write_checksums(root: Path) -> None:
    lines = [
        f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != "SHA256SUMS.txt"
    ]
    _write_text(root / "SHA256SUMS.txt", "\n".join(lines) + "\n")


def _validate_package_checksums(root: Path) -> None:
    checksums = _parse_checksums(root / "SHA256SUMS.txt")
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    if set(checksums) != actual:
        raise V3VerifiedCandidateError(f"package checksum inventory mismatch: {root}")
    for relative, expected in checksums.items():
        if _sha256_file(root / relative) != expected:
            raise V3VerifiedCandidateError(f"package checksum mismatch: {relative}")


def _parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in _read_lf_utf8_bytes(path).decode("utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        normalized = Path(relative)
        if (
            separator != "  "
            or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or normalized.is_absolute()
            or ".." in normalized.parts
            or relative in checksums
        ):
            raise V3VerifiedCandidateError(f"invalid checksum entry: {path}")
        checksums[relative] = digest
    if not checksums:
        raise V3VerifiedCandidateError(f"empty checksum file: {path}")
    return checksums


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _write_text(
        path,
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict[str, Any]:
    value = _parse_json(_read_lf_utf8_bytes(path).decode("utf-8"), path)
    if not isinstance(value, dict):
        raise V3VerifiedCandidateError(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = _read_lf_utf8_bytes(path).decode("utf-8")
    lines = raw.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise V3VerifiedCandidateError(f"blank or empty JSONL: {path}")
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        value = _parse_json(line, path, line_number)
        if not isinstance(value, dict):
            raise V3VerifiedCandidateError(f"JSONL object required: {path}:{line_number}")
        values.append(value)
    return values


def _parse_json(text: str, path: Path, line_number: int | None = None) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        suffix = f":{line_number}" if line_number is not None else ""
        raise V3VerifiedCandidateError(f"invalid JSON: {path}{suffix}") from exc


def _read_lf_utf8_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise V3VerifiedCandidateError(f"UTF-8 BOM is not allowed: {path}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise V3VerifiedCandidateError(f"invalid UTF-8: {path}") from exc
    if b"\r" in raw:
        raise V3VerifiedCandidateError(f"text input is not LF-only: {path}")
    return raw


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V3VerifiedCandidateError(f"duplicate JSON key: {key}")
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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

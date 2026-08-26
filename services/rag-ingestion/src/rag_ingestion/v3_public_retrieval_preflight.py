"""Build and validate the RAG v003 public-retrieval acceptance and preflight."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"
CANONICAL_JSON_HASH_MODE = "sha256_canonical_json_v1"
ACCEPTANCE_RELATIVE_PATH = Path(
    "data/rag-v3/review/acceptance/v001/owner-public-use-acceptance.json"
)
ACCEPTANCE_PACKAGE_RELATIVE_PATH = ACCEPTANCE_RELATIVE_PATH.parent
PREFLIGHT_RELATIVE_PATH = Path("data/rag-v3/preflight/v001")
PRIOR_CANDIDATE_PATH = Path("data/rag-v2/candidates/v002")
PRIOR_ACCEPTANCE_PATH = Path(
    "data/rag-v2/human-review/acceptance/v002/owner-staging-embedding-acceptance.json"
)
PRIOR_ALLOWLIST_PATH = PRIOR_CANDIDATE_PATH / "manifests/embedding-staging-allowlist-v003.json"
PRIOR_CHECKSUMS_PATH = PRIOR_CANDIDATE_PATH / "SHA256SUMS.txt"
SOURCE_MANIFEST_PATH = PRIOR_CANDIDATE_PATH / "manifests/source-manifest-v002.json"
OWNER_SCHEMA_PATH = Path("contracts/schemas/rag/rag-owner-public-use-acceptance-v3.schema.json")
PRIOR_FORMAL_ROOTS = (
    PRIOR_CANDIDATE_PATH,
    Path("data/rag-v2/human-review/v001"),
    Path("data/rag-v2/human-review/acceptance/v001"),
    Path("data/rag-v2/human-review/acceptance/v002"),
)
V3_VALIDATION_INPUT_PATHS = (
    Path("config/rag/embedding-google.yaml"),
    Path("config/rag/hybrid-legal.json"),
    Path("config/rag/hybrid-natural-language.json"),
    Path("config/rag/staging-filters.yaml"),
    Path("contracts/schemas/rag/rag-chunk-v3.schema.json"),
    OWNER_SCHEMA_PATH,
    Path("docs/project/rag-v3-public-retrieval-plan.md"),
    ACCEPTANCE_RELATIVE_PATH,
    Path("scripts/rag/build_v3_public_retrieval_preflight.py"),
    Path("scripts/rag/validate_v3_public_retrieval_preflight.py"),
    Path("services/rag-ingestion/src/rag_ingestion/" "v3_public_retrieval_preflight.py"),
    Path("services/rag-ingestion/tests/integration/" "test_v3_public_retrieval_preflight.py"),
    Path("services/rag-ingestion/tests/unit/" "test_rag_chunk_v3_schema_contract.py"),
)
IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


class V3PublicRetrievalPreflightError(ValueError):
    """Raised when a v003 acceptance or preflight integrity gate fails."""


@dataclass(frozen=True)
class V3PublicRetrievalSummary:
    artifact: str
    output_path: Path
    source_count: int
    chunk_count: int
    inventory_sha256: str | None = None
    prior_lock_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact": self.artifact,
            "chunk_count": self.chunk_count,
            "inventory_sha256": self.inventory_sha256,
            "output_path": self.output_path.as_posix(),
            "prior_lock_sha256": self.prior_lock_sha256,
            "production_approved": False,
            "source_count": self.source_count,
            "status": "PASS",
        }


def build_v3_owner_public_use_acceptance(
    repository_root: Path,
    *,
    project_owner_id: str,
    signed_at: str,
    authorization_statements: Sequence[str],
    output_path: Path | None = None,
) -> V3PublicRetrievalSummary:
    """Create the versioned owner acceptance without granting external or Production use."""

    root = repository_root.resolve()
    package = (
        output_path.resolve()
        if output_path is not None
        else (root / ACCEPTANCE_PACKAGE_RELATIVE_PATH).resolve()
    )
    if package.exists():
        raise V3PublicRetrievalPreflightError(
            "v003 owner public-use acceptance already exists; refuse to overwrite"
        )
    statements = _validate_authorization_inputs(
        project_owner_id,
        signed_at,
        authorization_statements,
    )
    _validate_prior_candidate(root)
    acceptance = _owner_acceptance_document(
        root,
        project_owner_id=project_owner_id,
        signed_at=signed_at,
        authorization_statements=statements,
    )
    _validate_owner_schema(root, acceptance)

    staged = _new_staging_directory(root, "acceptance")
    try:
        _write_json(staged / ACCEPTANCE_RELATIVE_PATH.name, acceptance)
        _write_text(staged / "README.md", _acceptance_readme(acceptance))
        report = _acceptance_validation_report(root, acceptance)
        _write_json(staged / "validation-report.json", report)
        manifest = {
            "schema_version": "1.0.0",
            "artifact_version": "v003",
            "acceptance_version": "v001",
            "acceptance_path": ACCEPTANCE_RELATIVE_PATH.name,
            "acceptance_sha256": _sha256_file(staged / ACCEPTANCE_RELATIVE_PATH.name),
            "authorization_statements_sha256": acceptance["authorization"]["statements_sha256"],
            "candidate_artifact_version": "v003",
            "prior_candidate_checksums_sha256": acceptance["accepted_artifacts"][
                "prior_candidate_checksums_sha256"
            ],
            "prior_allowlist_sha256": acceptance["accepted_artifacts"]["prior_allowlist_sha256"],
            "prior_acceptance_sha256": acceptance["accepted_artifacts"]["prior_acceptance_sha256"],
            "source_count": 17,
            "chunk_count": 726,
            "review_status": "needs_review",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        }
        _write_json(staged / "manifest.json", manifest)
        _write_checksums(staged)
        validate_v3_owner_public_use_acceptance(root, staged)
        _publish_directory(staged, package)
    finally:
        _cleanup_staging_directory(root, staged)

    return V3PublicRetrievalSummary(
        artifact="v003_owner_public_use_acceptance",
        output_path=package,
        source_count=17,
        chunk_count=726,
    )


def validate_v3_owner_public_use_acceptance(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate the recorded owner instruction, fixed v002 anchors, and blocked gates."""

    root = repository_root.resolve()
    package = (
        package_path.resolve()
        if package_path is not None
        else (root / ACCEPTANCE_PACKAGE_RELATIVE_PATH).resolve()
    )
    _validate_package_checksums(package)
    acceptance = _read_json(package / ACCEPTANCE_RELATIVE_PATH.name)
    _validate_owner_schema(root, acceptance)
    _validate_prior_candidate(root)
    statements = acceptance["authorization"]["statements"]
    if acceptance["authorization"]["statements_sha256"] != _canonical_sha256(statements):
        raise V3PublicRetrievalPreflightError("owner authorization statements hash mismatch")
    _assert_acceptance_anchors(root, acceptance)
    if acceptance["gates"] != {
        "environment": "STAGING",
        "candidate_build": "AUTHORIZED",
        "external_sync": "NOT_AUTHORIZED",
        "production_status": "BLOCKED",
        "production_approved": False,
    }:
        raise V3PublicRetrievalPreflightError("owner acceptance gates were broadened")
    manifest = _read_json(package / "manifest.json")
    if manifest["acceptance_sha256"] != _sha256_file(package / ACCEPTANCE_RELATIVE_PATH.name):
        raise V3PublicRetrievalPreflightError("owner acceptance manifest hash mismatch")
    report = _read_json(package / "validation-report.json")
    if report.get("status") != "PASS" or report.get("fail_count") != 0:
        raise V3PublicRetrievalPreflightError("owner acceptance validation report is not PASS")
    return {
        "acceptance_sha256": manifest["acceptance_sha256"],
        "chunk_count": 726,
        "production_approved": False,
        "review_status": "needs_review",
        "source_count": 17,
        "status": "PASS",
    }


def build_v3_preflight(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> V3PublicRetrievalSummary:
    """Freeze v003 inputs and every selected local v002 formal artifact."""

    root = repository_root.resolve()
    package = (
        output_path.resolve()
        if output_path is not None
        else (root / PREFLIGHT_RELATIVE_PATH).resolve()
    )
    if package.exists():
        raise V3PublicRetrievalPreflightError("v003 preflight already exists; refuse to overwrite")
    validate_v3_owner_public_use_acceptance(root)

    prior_entries = _prior_artifact_entries(root)
    source_inventory = _source_inventory(root)
    validation_entries = _validation_input_entries(root, prior_entries)
    prior_lock = _inventory_document(
        kind="rag_v3_prior_artifact_immutable_lock",
        entries=prior_entries,
        source_inventory=source_inventory,
        scope="local v002 candidate, human-review, and owner-acceptance formal artifacts",
    )
    validation_inventory = _inventory_document(
        kind="rag_v3_validation_input_inventory",
        entries=validation_entries,
        source_inventory=source_inventory,
        scope=(
            "v003 schemas, policy plan, acceptance, implementation, tests, config, "
            "and v002 inputs"
        ),
    )

    staged = _new_staging_directory(root, "preflight")
    try:
        _write_json(staged / "prior-artifact-lock.json", prior_lock)
        _write_json(staged / "validation-input-inventory.json", validation_inventory)
        _write_text(staged / "README.md", _preflight_readme(prior_lock, validation_inventory))
        _write_checksums(staged)
        validate_v3_preflight(root, staged)
        _publish_directory(staged, package)
    finally:
        _cleanup_staging_directory(root, staged)

    return V3PublicRetrievalSummary(
        artifact="v003_preflight",
        output_path=package,
        source_count=17,
        chunk_count=726,
        inventory_sha256=validation_inventory["inventory_sha256"],
        prior_lock_sha256=prior_lock["inventory_sha256"],
    )


def validate_v3_preflight(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Recompute the preflight scope and reject any byte or source-evidence drift."""

    root = repository_root.resolve()
    package = (
        package_path.resolve()
        if package_path is not None
        else (root / PREFLIGHT_RELATIVE_PATH).resolve()
    )
    validate_v3_owner_public_use_acceptance(root)
    _validate_package_checksums(package)
    stored_lock = _read_json(package / "prior-artifact-lock.json")
    stored_inventory = _read_json(package / "validation-input-inventory.json")
    current_prior_entries = _prior_artifact_entries(root)
    current_sources = _source_inventory(root)
    current_lock = _inventory_document(
        kind="rag_v3_prior_artifact_immutable_lock",
        entries=current_prior_entries,
        source_inventory=current_sources,
        scope="local v002 candidate, human-review, and owner-acceptance formal artifacts",
    )
    current_inventory = _inventory_document(
        kind="rag_v3_validation_input_inventory",
        entries=_validation_input_entries(root, current_prior_entries),
        source_inventory=current_sources,
        scope=(
            "v003 schemas, policy plan, acceptance, implementation, tests, config, "
            "and v002 inputs"
        ),
    )
    if stored_lock != current_lock:
        raise V3PublicRetrievalPreflightError("v002 prior-artifact immutable lock mismatch")
    if stored_inventory != current_inventory:
        raise V3PublicRetrievalPreflightError("v003 validation input inventory mismatch")
    return {
        "chunk_count": 726,
        "inventory_entry_count": stored_inventory["entry_count"],
        "inventory_sha256": stored_inventory["inventory_sha256"],
        "prior_artifact_entry_count": stored_lock["entry_count"],
        "prior_lock_sha256": stored_lock["inventory_sha256"],
        "production_approved": False,
        "source_count": 17,
        "status": "PASS",
    }


def validate_v3_preflight_build_snapshot(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate historical build evidence without claiming current-input equality."""

    root = repository_root.resolve()
    package = (
        package_path.resolve()
        if package_path is not None
        else (root / PREFLIGHT_RELATIVE_PATH).resolve()
    )
    validate_v3_owner_public_use_acceptance(root)
    _validate_package_checksums(package)
    stored_lock = _read_json(package / "prior-artifact-lock.json")
    stored_inventory = _read_json(package / "validation-input-inventory.json")
    current_lock = _inventory_document(
        kind="rag_v3_prior_artifact_immutable_lock",
        entries=_prior_artifact_entries(root),
        source_inventory=_source_inventory(root),
        scope="local v002 candidate, human-review, and owner-acceptance formal artifacts",
    )
    if stored_lock != current_lock:
        raise V3PublicRetrievalPreflightError(
            "v003 build snapshot prior-artifact immutable lock mismatch"
        )
    stored_digest_payload = {
        "entries": stored_inventory["entries"],
        "source_inventory": stored_inventory["source_inventory"],
    }
    if stored_inventory["inventory_sha256"] != _canonical_sha256(stored_digest_payload):
        raise V3PublicRetrievalPreflightError(
            "v003 build snapshot stored inventory digest mismatch"
        )
    return {
        "chunk_count": 726,
        "inventory_entry_count": stored_inventory["entry_count"],
        "inventory_sha256": stored_inventory["inventory_sha256"],
        "prior_artifact_entry_count": stored_lock["entry_count"],
        "prior_lock_sha256": stored_lock["inventory_sha256"],
        "production_approved": False,
        "source_count": 17,
        "status": "PASS_BUILD_SNAPSHOT",
    }


def _owner_acceptance_document(
    root: Path,
    *,
    project_owner_id: str,
    signed_at: str,
    authorization_statements: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": "3.0.0",
        "acceptance_version": "v001",
        "candidate_artifact_version": "v003",
        "status": "SIGNED",
        "project_owner_id": project_owner_id,
        "signer_role": "PROJECT_OWNER",
        "signed_at": signed_at,
        "authorization": {
            "channel": "interactive_user_instruction",
            "statements": list(authorization_statements),
            "statements_sha256": _canonical_sha256(list(authorization_statements)),
        },
        "electronic_signature": {
            "assurance": "RECORDED_EXPLICIT_USER_AUTHORIZATION",
            "signature_value": project_owner_id,
            "intent": "AUTHORIZE_V003_STAGING_PUBLIC_RETRIEVAL_POLICY",
            "cryptographic_signature": None,
        },
        "accepted_artifacts": {
            "prior_candidate_path": PRIOR_CANDIDATE_PATH.as_posix(),
            "prior_candidate_checksums_sha256": _sha256_file(root / PRIOR_CHECKSUMS_PATH),
            "prior_allowlist_sha256": _sha256_file(root / PRIOR_ALLOWLIST_PATH),
            "prior_acceptance_path": PRIOR_ACCEPTANCE_PATH.as_posix(),
            "prior_acceptance_sha256": _sha256_file(root / PRIOR_ACCEPTANCE_PATH),
            "source_count": 17,
            "chunk_count": 726,
            "official_source_count": 14,
            "official_chunk_count": 651,
            "research_source_count": 3,
            "research_chunk_count": 75,
        },
        "acceptance_scope": "STAGING_PUBLIC_RETRIEVAL_POLICY",
        "public_use_decision": {
            "public_source_review_completed": True,
            "project_use_approved": True,
            "owner_approval_replaces_source_evidence": False,
        },
        "retrieval_policy_decision": {
            "allowed_audiences": [
                "elder",
                "family_caregiver",
                "care_professional",
                "system_admin",
            ],
            "high_or_unknown_normal_rag": "DENY",
            "audience_override_bypasses_risk": False,
            "embedding_reuse_allowed": True,
        },
        "review_assertions": {
            "formal_item_level_source_fidelity": "NOT_RECORDED",
            "exact_facts_verified": "NOT_RECORDED",
            "source_version_verified": "PRESERVE_EXISTING_EVIDENCE",
            "review_status": "needs_review",
        },
        "gates": {
            "environment": "STAGING",
            "candidate_build": "AUTHORIZED",
            "external_sync": "NOT_AUTHORIZED",
            "production_status": "BLOCKED",
            "production_approved": False,
        },
    }


def _acceptance_validation_report(
    root: Path,
    acceptance: Mapping[str, Any],
) -> dict[str, Any]:
    _assert_acceptance_anchors(root, acceptance)
    checks = [
        "owner_acceptance_schema_valid",
        "authorization_statements_hash_valid",
        "v002_candidate_checksums_valid",
        "v002_candidate_checksums_hash_bound",
        "v002_allowlist_hash_bound",
        "v002_owner_acceptance_hash_bound",
        "source_count_17",
        "chunk_count_726",
        "official_and_research_counts_preserved",
        "owner_approval_does_not_replace_source_evidence",
        "formal_item_review_not_inferred",
        "high_or_unknown_normal_rag_denied",
        "external_sync_not_authorized",
        "production_blocked",
    ]
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "acceptance_version": "v001",
        "checks": [{"name": name, "status": "PASS"} for name in checks],
        "pass_count": len(checks),
        "fail_count": 0,
        "review_status": "needs_review",
        "external_sync": "NOT_AUTHORIZED",
        "production_status": "BLOCKED",
        "production_approved": False,
        "status": "PASS",
    }


def _assert_acceptance_anchors(root: Path, acceptance: Mapping[str, Any]) -> None:
    anchors = acceptance["accepted_artifacts"]
    expected = {
        "prior_candidate_checksums_sha256": _sha256_file(root / PRIOR_CHECKSUMS_PATH),
        "prior_allowlist_sha256": _sha256_file(root / PRIOR_ALLOWLIST_PATH),
        "prior_acceptance_sha256": _sha256_file(root / PRIOR_ACCEPTANCE_PATH),
    }
    for name, value in expected.items():
        if anchors.get(name) != value:
            raise V3PublicRetrievalPreflightError(f"owner acceptance {name} mismatch")


def _validate_prior_candidate(root: Path) -> None:
    candidate = root / PRIOR_CANDIDATE_PATH
    checksums = _parse_checksums(candidate / "SHA256SUMS.txt")
    actual_paths = {
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    if set(checksums) != actual_paths:
        raise V3PublicRetrievalPreflightError("v002 candidate checksum inventory mismatch")
    for relative, expected in checksums.items():
        if _sha256_file(candidate / relative) != expected:
            raise V3PublicRetrievalPreflightError(f"v002 candidate checksum mismatch: {relative}")
    manifest = _read_json(root / SOURCE_MANIFEST_PATH)
    if manifest.get("source_count") != 17 or manifest.get("chunk_count") != 726:
        raise V3PublicRetrievalPreflightError("v002 source manifest count mismatch")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or len(sources) != 17:
        raise V3PublicRetrievalPreflightError("v002 source manifest is incomplete")
    official_sources = [item for item in sources if item.get("is_official_source") is True]
    research_sources = [item for item in sources if item.get("is_official_source") is False]
    if sum(int(item["chunk_count"]) for item in official_sources) != 651:
        raise V3PublicRetrievalPreflightError("v002 official chunk count mismatch")
    if sum(int(item["chunk_count"]) for item in research_sources) != 75:
        raise V3PublicRetrievalPreflightError("v002 research chunk count mismatch")


def _source_inventory(root: Path) -> list[dict[str, Any]]:
    manifest = _read_json(root / SOURCE_MANIFEST_PATH)
    sources: list[dict[str, Any]] = []
    for item in manifest["sources"]:
        source_id = item["source_id"]
        chunk_path = PRIOR_CANDIDATE_PATH / "chunks" / f"{source_id}.rag-chunk-v2.v002.jsonl"
        absolute_chunk_path = root / chunk_path
        if not absolute_chunk_path.is_file():
            raise V3PublicRetrievalPreflightError(f"v002 source chunk file missing: {source_id}")
        sources.append(
            {
                "source_id": source_id,
                "title": item["title"],
                "source_type": item["source_type"],
                "is_official_source": item["is_official_source"],
                "source_versions": item["source_versions"],
                "storage_strategy": "rag_only",
                "chunk_count": item["chunk_count"],
                "chunk_file_path": chunk_path.as_posix(),
                "chunk_file_size_bytes": absolute_chunk_path.stat().st_size,
                "chunk_file_sha256": _sha256_file(absolute_chunk_path),
                "direct_source_urls": item["direct_source_urls"],
                "official_source_page_urls": item["official_source_page_urls"],
                "license_evidence_urls": item["license_evidence_urls"],
                "storage_urls": item["storage_urls"],
                "local_raw_source_bytes_available": False,
                "review_status": "needs_review",
                "production_approved": False,
            }
        )
    sources.sort(key=lambda item: item["source_id"])
    return sources


def _prior_artifact_entries(root: Path) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for relative_root in PRIOR_FORMAL_ROOTS:
        absolute_root = root / relative_root
        if not absolute_root.is_dir():
            raise V3PublicRetrievalPreflightError(
                f"prior formal artifact root missing: {relative_root.as_posix()}"
            )
        paths.extend(path for path in absolute_root.rglob("*") if path.is_file())
    unique_paths = sorted(set(paths), key=lambda path: path.relative_to(root).as_posix())
    return [_file_entry(root, path, prior=True) for path in unique_paths]


def _validation_input_entries(
    root: Path,
    prior_entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_path = {str(entry["path"]): dict(entry) for entry in prior_entries}
    for relative in V3_VALIDATION_INPUT_PATHS:
        path = root / relative
        if not path.is_file():
            raise V3PublicRetrievalPreflightError(
                f"v003 validation input missing: {relative.as_posix()}"
            )
        by_path[relative.as_posix()] = _file_entry(root, path, prior=False)
    return [by_path[path] for path in sorted(by_path)]


def _file_entry(root: Path, path: Path, *, prior: bool) -> dict[str, Any]:
    relative = path.relative_to(root)
    raw = _read_lf_utf8_bytes(path)
    parts = relative.parts
    version = next((part for part in reversed(parts) if re.fullmatch(r"v\d{3}", part)), "none")
    source_id = "rag-v2-corpus"
    if "chunks" in parts or "assignments" in parts:
        source_id = path.name.split(".rag-chunk", 1)[0].split(".jsonl", 1)[0]
    logical_family = "rag_v3_governance"
    if prior:
        if "candidates" in parts:
            logical_family = "rag_v2_candidate"
        elif "acceptance" in parts:
            logical_family = "rag_v2_owner_acceptance"
        else:
            logical_family = "rag_v2_human_review"
    return {
        "path": relative.as_posix(),
        "artifact_kind": _artifact_kind(relative),
        "source_id": source_id,
        "logical_family": logical_family,
        "version": version,
        "size_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "hash_mode": HASH_MODE,
    }


def _artifact_kind(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix == ".jsonl":
        return "chunk_jsonl" if "chunks" in path.parts else "review_jsonl"
    if path.name == "SHA256SUMS.txt":
        return "checksum_manifest"
    if path.name == "README.md":
        return "readme"
    if suffix == ".json":
        if "manifests" in path.parts or path.name == "manifest.json":
            return "manifest"
        if "reports" in path.parts or "report" in path.name:
            return "validation_or_evidence_report"
        if "acceptance" in path.name:
            return "owner_acceptance"
        return "governance_json"
    if suffix in {".py", ".ps1"}:
        return "implementation_or_test"
    if suffix in {".yaml", ".yml"}:
        return "configuration"
    if suffix == ".md":
        return "policy_document"
    return "formal_artifact"


def _inventory_document(
    *,
    kind: str,
    entries: Sequence[Mapping[str, Any]],
    source_inventory: Sequence[Mapping[str, Any]],
    scope: str,
) -> dict[str, Any]:
    digest_payload = {
        "entries": list(entries),
        "source_inventory": list(source_inventory),
    }
    return {
        "schema_version": "1.0.0",
        "artifact_version": "v003",
        "kind": kind,
        "scope": scope,
        "hash_mode": HASH_MODE,
        "inventory_hash_mode": CANONICAL_JSON_HASH_MODE,
        "entry_count": len(entries),
        "source_count": len(source_inventory),
        "chunk_count": sum(int(item["chunk_count"]) for item in source_inventory),
        "inventory_sha256": _canonical_sha256(digest_payload),
        "entries": list(entries),
        "source_inventory": list(source_inventory),
        "external_artifacts": [
            {
                "artifact": "v002_google_document_embedding_staging_artifact",
                "availability": "repository_external_not_revalidated_by_this_preflight",
                "sha256": "599d194db552433710ec6aff69318e962cb5b4b1c9f7a3050d527b369a3df7d5",
                "provider": "google",
                "model_id": "gemini-embedding-001",
                "dimension": 1024,
                "task_type": "RETRIEVAL_DOCUMENT",
                "production_approved": False,
            }
        ],
        "review_status": "needs_review",
        "production_approved": False,
    }


def _validate_owner_schema(root: Path, acceptance: Mapping[str, Any]) -> None:
    schema = _read_json(root / OWNER_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(acceptance), key=lambda error: list(error.absolute_path))
    if errors:
        raise V3PublicRetrievalPreflightError(
            f"v003 owner acceptance schema validation failed: {errors[0].message}"
        )


def _validate_authorization_inputs(
    project_owner_id: str,
    signed_at: str,
    authorization_statements: Sequence[str],
) -> tuple[str, ...]:
    if not IDENTIFIER_PATTERN.fullmatch(project_owner_id):
        raise V3PublicRetrievalPreflightError("project owner ID is invalid")
    parsed = datetime.fromisoformat(signed_at)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise V3PublicRetrievalPreflightError("signed_at must include a timezone offset")
    statements = tuple(statement.strip() for statement in authorization_statements)
    if not statements or any(not statement or len(statement) > 1024 for statement in statements):
        raise V3PublicRetrievalPreflightError("authorization statements are invalid")
    return statements


def _acceptance_readme(acceptance: Mapping[str, Any]) -> str:
    signed_at = acceptance["signed_at"]
    statement_hash = acceptance["authorization"]["statements_sha256"]
    return (
        "# RAG v003 owner public-use acceptance v001\n\n"
        f"Project owner `IanHsu` authorized the v003 staging public-retrieval policy at "
        f"`{signed_at}` through an explicit interactive instruction. The statements array is "
        f"bound with `{CANONICAL_JSON_HASH_MODE}` as `{statement_hash}`.\n\n"
        "This acceptance authorizes local v003 candidate construction and staging policy tests "
        "only. It does not replace source or license evidence, does not record item-level source "
        "fidelity or exact-fact review, and does not authorize external synchronization or "
        "Production. `review_status` remains `needs_review`.\n\n"
        "Do not edit this package in place. Create a versioned successor for changed owner "
        "decisions, external synchronization, completed review evidence, or Production gates.\n"
    )


def _preflight_readme(
    prior_lock: Mapping[str, Any],
    inventory: Mapping[str, Any],
) -> str:
    return (
        "# RAG v003 preflight v001\n\n"
        "This package freezes the local v002 candidate and its supporting review/acceptance "
        "artifacts before v003 candidate generation. It also records the selected v003 schemas, "
        "policy, configuration, implementation, tests, owner acceptance, and all 17 source "
        "families. No raw source bytes were locally available; source, official-page, license, "
        "and storage URLs remain separate in the source inventory.\n\n"
        f"- Prior artifact entries: `{prior_lock['entry_count']}`\n"
        f"- Prior lock SHA-256: `{prior_lock['inventory_sha256']}`\n"
        f"- Validation input entries: `{inventory['entry_count']}`\n"
        f"- Validation inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        "- Sources/chunks: `17` / `726`\n"
        "- Review status: `needs_review`\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n\n"
        "Any selected-byte change invalidates this preflight and requires a new versioned "
        "inventory. Do not edit v001 in place.\n"
    )


def _new_staging_directory(root: Path, label: str) -> Path:
    parent = root.parent.resolve()
    staged = Path(tempfile.mkdtemp(prefix=f".kinsun-rag-v3-{label}-", dir=parent)).resolve()
    if staged.parent != parent or not staged.name.startswith(f".kinsun-rag-v3-{label}-"):
        raise V3PublicRetrievalPreflightError("unsafe staging directory")
    return staged


def _publish_directory(staged: Path, destination: Path) -> None:
    if destination.exists():
        raise V3PublicRetrievalPreflightError("destination appeared before atomic publish")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged.replace(destination)


def _cleanup_staging_directory(root: Path, staged: Path) -> None:
    resolved = staged.resolve()
    parent = root.parent.resolve()
    if not resolved.exists():
        return
    if resolved.parent != parent or not resolved.name.startswith(".kinsun-rag-v3-"):
        raise V3PublicRetrievalPreflightError("refuse to clean unsafe staging directory")
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
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.txt"
    }
    if set(checksums) != actual_paths:
        raise V3PublicRetrievalPreflightError("package checksum inventory mismatch")
    for relative, expected in checksums.items():
        if _sha256_file(root / relative) != expected:
            raise V3PublicRetrievalPreflightError(f"package checksum mismatch: {relative}")


def _parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in _read_lf_utf8_bytes(path).decode("utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if separator != "  " or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise V3PublicRetrievalPreflightError(f"invalid checksum entry: {path.name}")
        normalized = Path(relative)
        if normalized.is_absolute() or ".." in normalized.parts or relative in checksums:
            raise V3PublicRetrievalPreflightError(f"unsafe checksum entry: {relative}")
        checksums[relative] = digest
    if not checksums:
        raise V3PublicRetrievalPreflightError(f"checksum file is empty: {path.name}")
    return checksums


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_lf_utf8_bytes(path).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise V3PublicRetrievalPreflightError(f"invalid JSON: {path.as_posix()}") from exc
    if not isinstance(value, dict):
        raise V3PublicRetrievalPreflightError(f"JSON object required: {path.as_posix()}")
    return value


def _read_lf_utf8_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise V3PublicRetrievalPreflightError(f"UTF-8 BOM is not allowed: {path.as_posix()}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise V3PublicRetrievalPreflightError(f"invalid UTF-8: {path.as_posix()}") from exc
    if b"\r" in raw:
        raise V3PublicRetrievalPreflightError(f"text input is not LF-only: {path.as_posix()}")
    return raw


def _reject_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V3PublicRetrievalPreflightError(f"duplicate JSON key: {key}")
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

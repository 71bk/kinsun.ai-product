"""Build the current-input audit v003 without mutating prior policy artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rag_ingestion.source_family_policy_v2 import (
    AUDIT_FORMAL_ROOTS,
    CHUNK_COUNT,
    POLICY_AUDIT_ROOT,
    POLICY_ROOT,
    SOURCE_COUNT,
    PolicyArtifactSummary,
    SourceFamilyPolicyV2Error,
    _audit_input_entries,
    _cleanup_staging_directory,
    _destination,
    _entries_for_roots,
    _file_entries,
    _inventory_document,
    _new_staging_directory,
    _publish_directory,
    _read_json,
    _refuse_overwrite,
    _validate_package_checksums,
    _write_checksums,
    _write_json,
    _write_text,
    validate_source_family_policy_v2_audit_preflight,
)

POLICY_AUDIT_V3_ROOT = POLICY_ROOT / "audits/v003/preflight"
AUDIT_V3_FORMAL_ROOTS = (*AUDIT_FORMAL_ROOTS, POLICY_AUDIT_ROOT)
AUDIT_V3_INPUT_PATHS = (
    Path("services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v3.py"),
    Path("scripts/rag/build_source_family_policy_audit_v3.py"),
    Path("scripts/rag/validate_source_family_policy_audit_v3.py"),
)
LOCK_KIND = "source_family_policy_v002_audit_v003_candidate_artifact_lock"
INVENTORY_KIND = "source_family_policy_v002_audit_v003_current_validation_input_inventory"


class SourceFamilyPolicyAuditV3Error(SourceFamilyPolicyV2Error):
    """Raised when the v003 current-input audit or its prior bindings diverge."""


def build_source_family_policy_audit_v3(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Bind current policy validation inputs to immutable v001/v002 audit bytes."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_AUDIT_V3_ROOT)
    _refuse_overwrite_v3(destination, "source-family policy audit preflight v003")
    validate_source_family_policy_v2_audit_preflight(root)
    candidate_entries = _entries_for_roots(
        root,
        AUDIT_V3_FORMAL_ROOTS,
        "source_family_policy_v002_audit_v003_formal_artifacts",
    )
    input_entries = _audit_v3_input_entries(root)
    candidate_lock = _inventory_document(
        LOCK_KIND,
        candidate_entries,
        (
            "immutable acceptance v003, policy preflight v002, policy candidate v002, "
            "and audit preflight v001/v002 bytes"
        ),
    )
    inventory = _inventory_document(
        INVENTORY_KIND,
        input_entries,
        "current policy v002 schemas, config, code, tests, evidence, and v003 chunks",
    )
    staged = _new_staging_directory(root, "source-policy-audit-v003")
    try:
        _write_json(staged / "candidate-artifact-lock.json", candidate_lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _audit_readme(candidate_lock, inventory))
        _write_checksums(staged)
        validate_source_family_policy_audit_v3(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_audit_preflight_v003",
        output_path=destination,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=candidate_lock["inventory_sha256"],
    )


def validate_source_family_policy_audit_v3(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate current inputs and all immutable predecessor audit bytes."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_AUDIT_V3_ROOT)
    validate_source_family_policy_v2_audit_preflight(root)
    _validate_package_checksums(package)
    lock = _read_json(package / "candidate-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V3_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v003_formal_artifacts",
        ),
        (
            "immutable acceptance v003, policy preflight v002, policy candidate v002, "
            "and audit preflight v001/v002 bytes"
        ),
    )
    expected_inventory = _inventory_document(
        INVENTORY_KIND,
        _audit_v3_input_entries(root),
        "current policy v002 schemas, config, code, tests, evidence, and v003 chunks",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyAuditV3Error("source-family audit v003 candidate lock mismatch")
    if inventory != expected_inventory:
        raise SourceFamilyPolicyAuditV3Error("source-family audit v003 input mismatch")
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


def _audit_v3_input_entries(root: Path) -> list[dict[str, Any]]:
    entries = _audit_input_entries(root)
    entries.extend(
        _file_entries(
            root,
            [root / path for path in AUDIT_V3_INPUT_PATHS],
            "source_family_policy_v002_audit_v003",
        )
    )
    return sorted(entries, key=lambda entry: entry["path"])


def _refuse_overwrite_v3(destination: Path, label: str) -> None:
    try:
        _refuse_overwrite(destination, label)
    except SourceFamilyPolicyV2Error as exc:
        raise SourceFamilyPolicyAuditV3Error(str(exc)) from exc


def _audit_readme(lock: dict[str, Any], inventory: dict[str, Any]) -> str:
    return (
        "# Source-family policy v002 audit preflight v003\n\n"
        "This successor keeps audit preflight v001 and v002 immutable while binding the "
        "current purpose-classification schemas, code, tests, evidence, and v003 chunks.\n\n"
        f"- Current validation inputs: `{inventory['entry_count']}`\n"
        f"- Current inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Candidate artifact entries: `{lock['entry_count']}`\n"
        f"- Candidate lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- Runtime integration: local hash-pinned runtime policy v003 integrated\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )

"""Build the source-family current-input audit v006 closeout successor."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from rag_ingestion.source_family_policy_audit_v5 import (
    AUDIT_V5_FORMAL_ROOTS,
    POLICY_AUDIT_V5_ROOT,
    _audit_v5_input_entries,
)
from rag_ingestion.source_family_policy_v2 import (
    CHUNK_COUNT,
    POLICY_ROOT,
    SOURCE_COUNT,
    PolicyArtifactSummary,
    SourceFamilyPolicyV2Error,
    _cleanup_staging_directory,
    _destination,
    _entries_for_roots,
    _file_entries,
    _inventory_document,
    _new_staging_directory,
    _read_json,
    _refuse_overwrite,
    _validate_frozen_audit_inventory,
    _validate_package_checksums,
    _write_checksums,
    _write_json,
    _write_text,
)
from rag_ingestion.source_family_runtime_policy_v2 import _publish_directory

POLICY_AUDIT_V6_ROOT = POLICY_ROOT / "audits/v006/preflight"
AUDIT_V6_FORMAL_ROOTS = (*AUDIT_V5_FORMAL_ROOTS, POLICY_AUDIT_V5_ROOT)
AUDIT_V6_INPUT_PATHS = (
    Path("services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v6.py"),
    Path("scripts/rag/build_source_family_policy_audit_v6.py"),
    Path("scripts/rag/validate_source_family_policy_audit_v6.py"),
    Path("services/rag-ingestion/tests/integration/test_source_family_policy_audit_v6.py"),
)
V5_CHECKSUMS_SHA256 = "201be1ea4ac4085269e0e1131c2cc9cd3a3d56fda1eda22d639a1e0d29d765e0"
LOCK_KIND = "source_family_policy_v002_audit_v006_candidate_artifact_lock"
INVENTORY_KIND = "source_family_policy_v002_audit_v006_current_validation_input_inventory"


class SourceFamilyPolicyAuditV6Error(SourceFamilyPolicyV2Error):
    """Raised when v006 current inputs or predecessor bytes diverge."""


def build_source_family_policy_audit_v6(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Bind final closeout checks while preserving v005 and earlier bytes."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_AUDIT_V6_ROOT)
    _refuse_overwrite_v6(destination, "source-family policy audit preflight v006")
    _validate_predecessors(root)
    lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V6_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v006_formal_artifacts",
        ),
        "immutable policy artifacts, audit v001-v005 bytes, and v006 closeout acceptance",
    )
    inventory = _inventory_document(
        INVENTORY_KIND,
        _audit_v6_input_entries(root),
        "current policy schemas, code, tests, evidence, docs, and v003 chunks",
    )
    staged = _new_staging_directory(root, "source-policy-audit-v006")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _readme(lock, inventory))
        _write_checksums(staged)
        validate_source_family_policy_audit_v6(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_audit_preflight_v006",
        output_path=destination,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=lock["inventory_sha256"],
    )


def validate_source_family_policy_audit_v6(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate v006 against the exact current-input inventory."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_AUDIT_V6_ROOT)
    _validate_predecessors(root)
    _validate_package_checksums(package)
    lock = _read_json(package / "candidate-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V6_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v006_formal_artifacts",
        ),
        "immutable policy artifacts, audit v001-v005 bytes, and v006 closeout acceptance",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyAuditV6Error("source-family audit v006 candidate lock mismatch")
    if package == (root / POLICY_AUDIT_V6_ROOT).resolve():
        _validate_frozen_audit_inventory(inventory, INVENTORY_KIND)
    else:
        expected_inventory = _inventory_document(
            INVENTORY_KIND,
            _audit_v6_input_entries(root),
            "current policy schemas, code, tests, evidence, docs, and v003 chunks",
        )
        if inventory != expected_inventory:
            raise SourceFamilyPolicyAuditV6Error("source-family audit v006 input mismatch")
    return {
        "status": "PASS",
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "candidate_artifact_entry_count": lock["entry_count"],
        "candidate_lock_sha256": lock["inventory_sha256"],
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "purpose_verified_count": 32,
        "conditional_stop_count": 27,
        "conditional_stop_active_count": 0,
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validate_predecessors(root: Path) -> None:
    _validate_package_checksums(root / POLICY_AUDIT_V5_ROOT)
    checksum_path = root / POLICY_AUDIT_V5_ROOT / "SHA256SUMS.txt"
    if hashlib.sha256(checksum_path.read_bytes()).hexdigest() != V5_CHECKSUMS_SHA256:
        raise SourceFamilyPolicyAuditV6Error("prior audit v005 bytes changed")


def _audit_v6_input_entries(root: Path) -> list[dict[str, Any]]:
    entries = _audit_v5_input_entries(root)
    entries.extend(
        _file_entries(
            root,
            [root / path for path in AUDIT_V6_INPUT_PATHS],
            "source_family_policy_v002_audit_v006",
        )
    )
    paths = [entry["path"] for entry in entries]
    if len(paths) != len(set(paths)):
        raise SourceFamilyPolicyAuditV6Error("audit v006 input paths must be unique")
    return sorted(entries, key=lambda entry: entry["path"])


def _refuse_overwrite_v6(destination: Path, label: str) -> None:
    try:
        _refuse_overwrite(destination, label)
    except SourceFamilyPolicyV2Error as exc:
        raise SourceFamilyPolicyAuditV6Error(str(exc)) from exc


def _readme(lock: dict[str, Any], inventory: dict[str, Any]) -> str:
    return (
        "# Source-family policy v002 audit preflight v006\n\n"
        "This successor preserves audit v001-v005 and binds the final closeout "
        "regression expectations to the current inputs.\n\n"
        f"- Current validation inputs: `{inventory['entry_count']}`\n"
        f"- Current inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Candidate artifact entries: `{lock['entry_count']}`\n"
        f"- Candidate lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- A-unit purpose decisions Owner verified: `32`\n"
        "- Conditional-stop audience reviews pending / runtime-active: `27` / `0`\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )

"""Immutable supplement binding the authorized law-sync tools to audit v009."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag_ingestion.source_family_policy_audit_v9 import (
    AUDIT_V9_FORMAL_ROOTS,
    POLICY_AUDIT_V9_ROOT,
    _audit_v9_input_entries,
    validate_source_family_policy_audit_v9,
)
from rag_ingestion.source_family_policy_v2 import (
    POLICY_ROOT,
    SourceFamilyPolicyV2Error,
    _cleanup_staging_directory,
    _destination,
    _entries_for_roots,
    _file_entries,
    _inventory_document,
    _new_staging_directory,
    _read_json,
    _refuse_overwrite,
    _validate_package_checksums,
    _write_checksums,
    _write_json,
    _write_text,
)
from rag_ingestion.source_family_runtime_policy_v2 import _publish_directory

AUDIT_ROOT = POLICY_ROOT / "audits/v010/preflight"
PREDECESSOR_SHA = "d5a1474cd1cd18025e974b36d8f2a6ac765834e7e7b931de0f7cd158fc1ed6ef"
INPUT_PATHS = (
    "services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v10.py",
    "services/rag-ingestion/tests/integration/test_source_family_policy_audit_v10.py",
    "scripts/rag/law_sync_audit.py",
    "scripts/rag/sync_law_repair.py",
    "services/core-api/app/rag_embedding_reuse_preflight.py",
    "services/core-api/tests/unit/test_rag_embedding_reuse_preflight.py",
    "services/core-api/tests/unit/test_law_repair_sync.py",
    "docs/project/rag-law-sync-authorization-20260910.json",
)


def documents(root):
    validate_source_family_policy_audit_v9(root)
    prior = root / POLICY_AUDIT_V9_ROOT / "SHA256SUMS.txt"
    if hashlib.sha256(prior.read_bytes()).hexdigest() != PREDECESSOR_SHA:
        raise SourceFamilyPolicyV2Error("audit v009 bytes changed")
    lock = _inventory_document(
        "law_sync_v010_prior_lock",
        _entries_for_roots(
            root, (*AUDIT_V9_FORMAL_ROOTS, POLICY_AUDIT_V9_ROOT), "prior_law_artifacts"
        ),
        "immutable predecessors through v009",
    )
    entries = _audit_v9_input_entries(root)
    entries.extend(_file_entries(root, [root / path for path in INPUT_PATHS], "law_sync_v010"))
    inventory = _inventory_document(
        "law_sync_v010_input_inventory",
        sorted(entries, key=lambda row: row["path"]),
        "authorized staging sync code and original v009 inputs",
    )
    return lock, inventory


def validate(root: Path, package: Path | None = None):
    root = root.resolve()
    package = _destination(root, package, AUDIT_ROOT)
    _validate_package_checksums(package)
    lock, inventory = documents(root)
    if _read_json(package / "candidate-artifact-lock.json") != lock:
        raise SourceFamilyPolicyV2Error("v010 prior lock mismatch")
    if _read_json(package / "validation-input-inventory.json") != inventory:
        raise SourceFamilyPolicyV2Error("v010 inputs changed; create a successor")
    return {
        "status": "PASS",
        "inventory_sha256": inventory["inventory_sha256"],
        "candidate_lock_sha256": lock["inventory_sha256"],
        "production_approved": False,
        "external_sync_authorization": "SEPARATELY_RECORDED_20260910",
        "live_verification": "NOT_PROVEN_BY_THIS_LOCAL_AUDIT",
    }


def build(root: Path, output_path: Path | None = None):
    root = root.resolve()
    destination = _destination(root, output_path, AUDIT_ROOT)
    _refuse_overwrite(destination, "law sync audit v010")
    lock, inventory = documents(root)
    staged = _new_staging_directory(root, "law-sync-audit-v010")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(
            staged / "README.md",
            "# Authorized staging law sync audit v010\n\n"
            "Retains v001-v009 and binds sync/reuse code, tests and "
            "the separate user authorization.\n"
            "Current database exports are not the lost original embedding artifact.\n"
            "This inventory proves local bytes only, not remote success or browser acceptance.\n"
            "Production remains blocked; runtime source safety gates are unchanged.\n",
        )
        _write_checksums(staged)
        validate(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return validate(root, destination)

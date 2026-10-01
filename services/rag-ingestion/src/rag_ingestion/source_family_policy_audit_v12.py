"""Current quality attestation after making the normalization tests cwd-independent."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag_ingestion import source_family_policy_audit_v11 as prior
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

AUDIT_ROOT = POLICY_ROOT / "audits/v012/preflight"
PRIOR_SHA = "2bc46c6a65b8467be4699301dc76f59f31e0712d8cc89efc44b0b7acd3fa8b3d"
INPUT_PATHS = (
    "services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v12.py",
    "services/rag-ingestion/tests/integration/test_source_family_policy_audit_v12.py",
)


def documents(root: Path):
    prior.validate(root)
    checksum = root / prior.AUDIT_ROOT / "SHA256SUMS.txt"
    if hashlib.sha256(checksum.read_bytes()).hexdigest() != PRIOR_SHA:
        raise SourceFamilyPolicyV2Error("audit v011 bytes changed")
    prior_lock, current_inputs = prior.documents(root)
    lock = _inventory_document(
        "quality_v012_prior_lock",
        sorted(
            prior_lock["entries"]
            + _entries_for_roots(root, (prior.AUDIT_ROOT,), "prior_artifacts"),
            key=lambda row: row["path"],
        ),
        "immutable predecessors through v011; no authorization changes",
    )
    entries = current_inputs["entries"] + _file_entries(
        root, [root / p for p in INPUT_PATHS], "quality_v012"
    )
    if len({entry["path"] for entry in entries}) != len(entries):
        raise SourceFamilyPolicyV2Error("duplicate current validation input")
    inventory = _inventory_document(
        "quality_v012_current_inputs",
        sorted(entries, key=lambda row: row["path"]),
        "current routing and quality inputs with cwd-independent normalization tests",
    )
    return lock, inventory


def validate(root: Path, package: Path | None = None):
    root = root.resolve()
    package = _destination(root, package, AUDIT_ROOT)
    _validate_package_checksums(package)
    lock, inventory = documents(root)
    if _read_json(package / "candidate-artifact-lock.json") != lock:
        raise SourceFamilyPolicyV2Error("v012 historical lock mismatch")
    if _read_json(package / "validation-input-inventory.json") != inventory:
        raise SourceFamilyPolicyV2Error("v012 current inputs changed; create a successor")
    return {
        "status": "PASS",
        "attestation_scope": "CURRENT_IMPLEMENTATION_BYTES",
        "inventory_sha256": inventory["inventory_sha256"],
        "candidate_lock_sha256": lock["inventory_sha256"],
        "input_count": inventory["entry_count"],
        "production_approved": False,
        "external_activation": "NOT_AUTHORIZED",
        "quality_acceptance": "NOT_PROVEN_BY_BYTE_ATTESTATION",
    }


def build(root: Path, output_path: Path | None = None):
    root = root.resolve()
    destination = _destination(root, output_path, AUDIT_ROOT)
    _refuse_overwrite(destination, "routing quality audit v012")
    lock, inventory = documents(root)
    staged = _new_staging_directory(root, "quality-audit-v012")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(
            staged / "README.md",
            "# Routing and retrieval quality audit v012\n\n"
            "Preserves every predecessor through v011 and attests current code/fixture bytes.\n"
            "The normalization test now runs independently of the pytest working directory.\n"
            "Historical inventories remain sealed; v012 is the current implementation gate.\n"
            "Routing and legal normalization remain opt-in. Ranking experiments are offline-only.\n"
            "No release, runtime policy, minimum citation count or score threshold is changed.\n"
            "This is not human relevance review, quality acceptance, or production approval.\n"
            "Prior sync authorization does not authorize any new external write or activation.\n",
        )
        _write_checksums(staged)
        validate(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return validate(root, destination)

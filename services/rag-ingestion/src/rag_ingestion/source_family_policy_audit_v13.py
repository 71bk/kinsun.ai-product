"""Current admission evaluation attestation; no runtime activation or human review."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag_ingestion import source_family_policy_audit_v12 as prior
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

AUDIT_ROOT = POLICY_ROOT / "audits/v013/preflight"
PRIOR_SHA = "a91bfe569ff8d3c2c2e9a0b5d5837ee3f1f99601f48015a618ce85183e547d70"
INPUT_PATHS = (
    "services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v13.py",
    "services/rag-ingestion/tests/integration/test_source_family_policy_audit_v13.py",
    "services/rag-ingestion/tests/unit/test_admission_evaluation.py",
    "scripts/rag/admission_quality.py",
    "scripts/rag/evaluate_admission.py",
    "evals/rag/admission-cases-v1.json",
    "evals/rag/ADMISSION.md",
    "evals/rag/reports/live-retrieval-v1.json",
    "evals/rag/reports/admission-snapshot-v1.json",
    "evals/rag/reports/admission-comparison-v1.json",
    "evals/rag/reports/admission-summary-v1.md",
    "evals/rag/review/admission-review-v1.json",
    "evals/rag/review/admission-missed-cases-v1.md",
)


def documents(root: Path):
    prior.validate(root)
    checksum = root / prior.AUDIT_ROOT / "SHA256SUMS.txt"
    if hashlib.sha256(checksum.read_bytes()).hexdigest() != PRIOR_SHA:
        raise SourceFamilyPolicyV2Error("audit v012 bytes changed")
    prior_lock, current_inputs = prior.documents(root)
    lock = _inventory_document(
        "quality_v013_prior_lock",
        sorted(
            prior_lock["entries"]
            + _entries_for_roots(root, (prior.AUDIT_ROOT,), "prior_artifacts"),
            key=lambda row: row["path"],
        ),
        "immutable predecessors through v012; no authorization changes",
    )
    entries = current_inputs["entries"] + _file_entries(
        root, [root / p for p in INPUT_PATHS], "quality_v013"
    )
    if len({entry["path"] for entry in entries}) != len(entries):
        raise SourceFamilyPolicyV2Error("duplicate current validation input")
    inventory = _inventory_document(
        "quality_v013_current_inputs",
        sorted(entries, key=lambda row: row["path"]),
        "admission replay tools, synthetic cases, read-only snapshot and pending human review",
    )
    return lock, inventory


def validate(root: Path, package: Path | None = None):
    root = root.resolve()
    package = _destination(root, package, AUDIT_ROOT)
    _validate_package_checksums(package)
    lock, inventory = documents(root)
    if _read_json(package / "candidate-artifact-lock.json") != lock:
        raise SourceFamilyPolicyV2Error("v013 historical lock mismatch")
    if _read_json(package / "validation-input-inventory.json") != inventory:
        raise SourceFamilyPolicyV2Error("v013 current inputs changed; create a successor")
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
    _refuse_overwrite(destination, "admission evaluation audit v013")
    lock, inventory = documents(root)
    staged = _new_staging_directory(root, "admission-audit-v013")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(
            staged / "README.md",
            "# Admission evaluation audit v013\n\n"
            "Preserves every predecessor through v012 and attests current evaluation bytes.\n"
            "Captured staging candidates are replayed offline with fixed Hybrid ranking.\n"
            "Human relevance, answerability and sufficiency judgments remain pending.\n"
            "No threshold or 3-5 citation contract is changed in runtime.\n"
            "No source, release, policy, production flag or external activation is changed.\n"
            "This byte attestation does not prove human relevance or answer quality.\n",
        )
        _write_checksums(staged)
        validate(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return validate(root, destination)

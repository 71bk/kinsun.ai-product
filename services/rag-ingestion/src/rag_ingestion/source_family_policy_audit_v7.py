"""Build the current runtime-governance audit v007 successor."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from rag_ingestion.source_family_policy_audit_v6 import (
    AUDIT_V6_FORMAL_ROOTS,
    POLICY_AUDIT_V6_ROOT,
    _audit_v6_input_entries,
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

POLICY_AUDIT_V7_ROOT = POLICY_ROOT / "audits/v007/preflight"
AUDIT_V7_FORMAL_ROOTS = (*AUDIT_V6_FORMAL_ROOTS, POLICY_AUDIT_V6_ROOT)
AUDIT_V7_INPUT_PATHS = (
    Path("services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v7.py"),
    Path("scripts/rag/build_source_family_policy_audit_v7.py"),
    Path("scripts/rag/validate_source_family_policy_audit_v7.py"),
    Path("services/rag-ingestion/tests/integration/test_source_family_policy_audit_v7.py"),
)
RUNTIME_GOVERNANCE_INPUT_PATHS = (
    Path("config/rag/source-family-golden-queries-v003.json"),
    Path("contracts/schemas/rag/rag-source-family-runtime-policy-v3.schema.json"),
    Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v003/" "SHA256SUMS.txt"),
    Path(
        "data/rag-v3/governance/source-family-policy/runtime/candidates/v003/"
        "source-family-runtime-policy.json"
    ),
    Path("services/agent-runtime/src/agent_runtime/rag/client.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/filters.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/postgres_backend.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/retriever.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/runtime_policy.py"),
    Path("services/agent-runtime/tests/unit/test_postgres_rag_backend.py"),
    Path("services/agent-runtime/tests/unit/test_rag_retrieval.py"),
    Path("services/agent-runtime/tests/unit/test_source_family_runtime_policy.py"),
    Path("services/rag-ingestion/src/rag_ingestion/source_family_runtime_policy_v3.py"),
    Path("services/rag-ingestion/tests/integration/" "test_source_family_runtime_policy_v3.py"),
)
V6_CHECKSUMS_SHA256 = "74db77295191511a47f5b31268e5164ec1c6227e6987c60b05576fe3a59698aa"
LOCK_KIND = "source_family_policy_v002_audit_v007_candidate_artifact_lock"
INVENTORY_KIND = "source_family_policy_v002_audit_v007_current_validation_input_inventory"


class SourceFamilyPolicyAuditV7Error(SourceFamilyPolicyV2Error):
    """Raised when v007 current inputs or predecessor bytes diverge."""


def build_source_family_policy_audit_v7(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Bind H-07 live-governance enforcement while preserving v006 and earlier bytes."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_AUDIT_V7_ROOT)
    _refuse_overwrite_v7(destination, "source-family policy audit preflight v007")
    _validate_predecessors(root)
    lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V7_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v007_formal_artifacts",
        ),
        "immutable policy artifacts and audit v001-v006 bytes",
    )
    inventory = _inventory_document(
        INVENTORY_KIND,
        _audit_v7_input_entries(root),
        "current policy inputs and H-07 live-governance runtime enforcement",
    )
    staged = _new_staging_directory(root, "source-policy-audit-v007")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _readme(lock, inventory))
        _write_checksums(staged)
        validate_source_family_policy_audit_v7(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_audit_preflight_v007",
        output_path=destination,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=lock["inventory_sha256"],
    )


def validate_source_family_policy_audit_v7(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate v007 against its immutable predecessors and current H-07 inputs."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_AUDIT_V7_ROOT)
    _validate_predecessors(root)
    _validate_package_checksums(package)
    lock = _read_json(package / "candidate-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V7_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v007_formal_artifacts",
        ),
        "immutable policy artifacts and audit v001-v006 bytes",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyAuditV7Error("source-family audit v007 candidate lock mismatch")
    if package == (root / POLICY_AUDIT_V7_ROOT).resolve():
        _validate_frozen_audit_inventory(inventory, INVENTORY_KIND)
    else:
        expected_inventory = _inventory_document(
            INVENTORY_KIND,
            _audit_v7_input_entries(root),
            "current policy inputs and H-07 live-governance runtime enforcement",
        )
        if inventory != expected_inventory:
            raise SourceFamilyPolicyAuditV7Error("source-family audit v007 input mismatch")
    return {
        "status": "PASS",
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "candidate_artifact_entry_count": lock["entry_count"],
        "candidate_lock_sha256": lock["inventory_sha256"],
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "live_governance_validation": "ENFORCED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validate_predecessors(root: Path) -> None:
    _validate_package_checksums(root / POLICY_AUDIT_V6_ROOT)
    checksum_path = root / POLICY_AUDIT_V6_ROOT / "SHA256SUMS.txt"
    if hashlib.sha256(checksum_path.read_bytes()).hexdigest() != V6_CHECKSUMS_SHA256:
        raise SourceFamilyPolicyAuditV7Error("prior audit v006 bytes changed")


def _audit_v7_input_entries(root: Path) -> list[dict[str, Any]]:
    entries = _audit_v6_input_entries(root)
    entries.extend(
        _file_entries(
            root,
            [root / path for path in (*AUDIT_V7_INPUT_PATHS, *RUNTIME_GOVERNANCE_INPUT_PATHS)],
            "source_family_policy_v002_audit_v007",
        )
    )
    paths = [entry["path"] for entry in entries]
    if len(paths) != len(set(paths)):
        raise SourceFamilyPolicyAuditV7Error("audit v007 input paths must be unique")
    return sorted(entries, key=lambda entry: entry["path"])


def _refuse_overwrite_v7(destination: Path, label: str) -> None:
    try:
        _refuse_overwrite(destination, label)
    except SourceFamilyPolicyV2Error as exc:
        raise SourceFamilyPolicyAuditV7Error(str(exc)) from exc


def _readme(lock: dict[str, Any], inventory: dict[str, Any]) -> str:
    return (
        "# Source-family policy v002 runtime-governance audit v007\n\n"
        "This successor preserves audit v001-v006 and binds H-07 live-governance "
        "enforcement to the current Agent Runtime implementation and acceptance tests.\n\n"
        f"- Current validation inputs: `{inventory['entry_count']}`\n"
        f"- Current inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Historical artifact entries: `{lock['entry_count']}`\n"
        f"- Historical lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- Runtime policy v003 decisions: unchanged\n"
        "- Live status, stop, eligibility, block, review, and Production gates: enforced\n"
        "- Historical inventories: sealed and validated independently of current HEAD\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )

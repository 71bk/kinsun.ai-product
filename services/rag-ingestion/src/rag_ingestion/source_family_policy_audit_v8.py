"""Build the current OpenSearch transport-governance audit v008 successor."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from rag_ingestion.source_family_policy_audit_v7 import (
    AUDIT_V7_FORMAL_ROOTS,
    POLICY_AUDIT_V7_ROOT,
    _audit_v7_input_entries,
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
    _validate_package_checksums,
    _write_checksums,
    _write_json,
    _write_text,
)
from rag_ingestion.source_family_runtime_policy_v2 import _publish_directory

POLICY_AUDIT_V8_ROOT = POLICY_ROOT / "audits/v008/preflight"
AUDIT_V8_FORMAL_ROOTS = (*AUDIT_V7_FORMAL_ROOTS, POLICY_AUDIT_V7_ROOT)
AUDIT_V8_INPUT_PATHS = (
    Path("services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v8.py"),
    Path("scripts/rag/build_source_family_policy_audit_v8.py"),
    Path("scripts/rag/validate_source_family_policy_audit_v8.py"),
    Path("services/rag-ingestion/tests/integration/test_source_family_policy_audit_v8.py"),
)
OPENSEARCH_TRANSPORT_INPUT_PATHS = (
    Path("services/agent-runtime/src/agent_runtime/app.py"),
    Path("services/agent-runtime/src/agent_runtime/rag/models.py"),
    Path("services/agent-runtime/src/agent_runtime/settings.py"),
)
V7_CHECKSUMS_SHA256 = "4f3c5dc4b9b90036266028bc50a2bf7c50824a16d371230ddb581407f437cf2b"
LOCK_KIND = "source_family_policy_v002_audit_v008_candidate_artifact_lock"
INVENTORY_KIND = "source_family_policy_v002_audit_v008_current_validation_input_inventory"


class SourceFamilyPolicyAuditV8Error(SourceFamilyPolicyV2Error):
    """Raised when v008 current inputs or predecessor bytes diverge."""


def build_source_family_policy_audit_v8(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Bind M-03 transport enforcement while preserving v007 and earlier bytes."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_AUDIT_V8_ROOT)
    _refuse_overwrite_v8(destination, "source-family policy audit preflight v008")
    _validate_predecessors(root)
    lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V8_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v008_formal_artifacts",
        ),
        "immutable policy artifacts and audit v001-v007 bytes",
    )
    inventory = _inventory_document(
        INVENTORY_KIND,
        _audit_v8_input_entries(root),
        "current policy inputs plus bounded and TLS-enforced OpenSearch transport",
    )
    staged = _new_staging_directory(root, "source-policy-audit-v008")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _readme(lock, inventory))
        _write_checksums(staged)
        validate_source_family_policy_audit_v8(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_audit_preflight_v008",
        output_path=destination,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=lock["inventory_sha256"],
    )


def validate_source_family_policy_audit_v8(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate v008 against immutable predecessors and current M-03 inputs."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_AUDIT_V8_ROOT)
    _validate_predecessors(root)
    _validate_package_checksums(package)
    lock = _read_json(package / "candidate-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V8_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v008_formal_artifacts",
        ),
        "immutable policy artifacts and audit v001-v007 bytes",
    )
    expected_inventory = _inventory_document(
        INVENTORY_KIND,
        _audit_v8_input_entries(root),
        "current policy inputs plus bounded and TLS-enforced OpenSearch transport",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyAuditV8Error("source-family audit v008 candidate lock mismatch")
    if inventory != expected_inventory:
        raise SourceFamilyPolicyAuditV8Error(
            "current RAG runtime attestation is outdated; create a successor to audit v008"
        )
    return {
        "status": "PASS",
        "source_count": SOURCE_COUNT,
        "chunk_count": CHUNK_COUNT,
        "candidate_artifact_entry_count": lock["entry_count"],
        "candidate_lock_sha256": lock["inventory_sha256"],
        "inventory_entry_count": inventory["entry_count"],
        "inventory_sha256": inventory["inventory_sha256"],
        "live_governance_validation": "ENFORCED",
        "opensearch_transport_validation": "TLS_AND_CAPACITY_ENFORCED",
        "external_sync": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _validate_predecessors(root: Path) -> None:
    _validate_package_checksums(root / POLICY_AUDIT_V7_ROOT)
    checksum_path = root / POLICY_AUDIT_V7_ROOT / "SHA256SUMS.txt"
    if hashlib.sha256(checksum_path.read_bytes()).hexdigest() != V7_CHECKSUMS_SHA256:
        raise SourceFamilyPolicyAuditV8Error("prior audit v007 bytes changed")


def _audit_v8_input_entries(root: Path) -> list[dict[str, Any]]:
    entries = _audit_v7_input_entries(root)
    entries.extend(
        _file_entries(
            root,
            [root / path for path in (*AUDIT_V8_INPUT_PATHS, *OPENSEARCH_TRANSPORT_INPUT_PATHS)],
            "source_family_policy_v002_audit_v008",
        )
    )
    paths = [entry["path"] for entry in entries]
    if len(paths) != len(set(paths)):
        raise SourceFamilyPolicyAuditV8Error("audit v008 input paths must be unique")
    return sorted(entries, key=lambda entry: entry["path"])


def _refuse_overwrite_v8(destination: Path, label: str) -> None:
    try:
        _refuse_overwrite(destination, label)
    except SourceFamilyPolicyV2Error as exc:
        raise SourceFamilyPolicyAuditV8Error(str(exc)) from exc


def _readme(lock: dict[str, Any], inventory: dict[str, Any]) -> str:
    return (
        "# Source-family policy v002 OpenSearch transport audit v008\n\n"
        "This successor preserves audit v001-v007 and binds M-03 OpenSearch transport "
        "enforcement to the current Agent Runtime implementation and acceptance tests.\n\n"
        f"- Current validation inputs: `{inventory['entry_count']}`\n"
        f"- Current inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Historical artifact entries: `{lock['entry_count']}`\n"
        f"- Historical lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- Runtime policy v003 decisions: unchanged\n"
        "- Remote OpenSearch transport: HTTPS with certificate and hostname validation\n"
        "- Search execution: bounded concurrency, dedicated workers, shared deadline\n"
        "- Cancellation: prompt caller cancellation with worker capacity retained until exit\n"
        "- Historical inventories: sealed and validated independently of current HEAD\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )

"""Build the current law-repair projection-governance audit v009 successor."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from rag_ingestion.source_family_policy_audit_v8 import (
    AUDIT_V8_FORMAL_ROOTS,
    POLICY_AUDIT_V8_ROOT,
    _audit_v8_input_entries,
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

POLICY_AUDIT_V9_ROOT = POLICY_ROOT / "audits/v009/preflight"
AUDIT_V9_FORMAL_ROOTS = (*AUDIT_V8_FORMAL_ROOTS, POLICY_AUDIT_V8_ROOT)
AUDIT_V9_INPUT_PATHS = (
    Path("services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v9.py"),
    Path("scripts/rag/build_source_family_policy_audit_v9.py"),
    Path("scripts/rag/validate_source_family_policy_audit_v9.py"),
    Path("services/rag-ingestion/tests/integration/test_source_family_policy_audit_v9.py"),
)
REPAIR_INPUT_PATHS = (
    Path("scripts/rag/preview_law_governance_sync.py"),
    Path("scripts/rag/build_law_repair_candidate.py"),
    Path("scripts/rag/build_law_repair_runtime_policy.py"),
    Path("services/core-api/tests/unit/test_law_governance_preview.py"),
    Path("services/core-api/tests/unit/test_law_repair_candidate.py"),
    Path("services/core-api/app/rag_projection_importer.py"),
    Path("services/core-api/app/rag_embedding_importer.py"),
    Path("services/agent-runtime/tests/unit/test_law_repair_runtime_policy.py"),
    Path("contracts/schemas/rag/rag-chunk-v2.1.schema.json"),
)
V8_CHECKSUMS_SHA256 = "87c49a1f2a89cb029ccf1ffb2ae358ddffaf36d42062a6fc545812ed8abcd1f6"
LOCK_KIND = "source_family_policy_v002_audit_v009_candidate_artifact_lock"
INVENTORY_KIND = "source_family_policy_v002_audit_v009_current_validation_input_inventory"


class SourceFamilyPolicyAuditV9Error(SourceFamilyPolicyV2Error):
    """Raised when v009 current inputs or predecessor bytes diverge."""


def build_source_family_policy_audit_v9(
    repository_root: Path,
    *,
    output_path: Path | None = None,
) -> PolicyArtifactSummary:
    """Bind law-repair projection compatibility while preserving v008 and earlier bytes."""

    root = repository_root.resolve()
    destination = _destination(root, output_path, POLICY_AUDIT_V9_ROOT)
    _refuse_overwrite_v9(destination, "source-family policy audit preflight v009")
    _validate_predecessors(root)
    lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V9_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v009_formal_artifacts",
        ),
        "immutable policy artifacts and audit v001-v008 bytes",
    )
    inventory = _inventory_document(
        INVENTORY_KIND,
        _audit_v9_input_entries(root),
        "current policy inputs plus immutable law-repair candidates and runtime bindings",
    )
    staged = _new_staging_directory(root, "source-policy-audit-v009")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(staged / "README.md", _readme(lock, inventory))
        _write_checksums(staged)
        validate_source_family_policy_audit_v9(root, staged)
        _publish_directory(staged, destination)
    finally:
        _cleanup_staging_directory(root, staged)
    return PolicyArtifactSummary(
        artifact="source_family_policy_v002_audit_preflight_v009",
        output_path=destination,
        inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=lock["inventory_sha256"],
    )


def validate_source_family_policy_audit_v9(
    repository_root: Path,
    package_path: Path | None = None,
) -> dict[str, Any]:
    """Validate v009 against immutable predecessors and current law-repair inputs."""

    root = repository_root.resolve()
    package = _destination(root, package_path, POLICY_AUDIT_V9_ROOT)
    _validate_predecessors(root)
    _validate_package_checksums(package)
    lock = _read_json(package / "candidate-artifact-lock.json")
    inventory = _read_json(package / "validation-input-inventory.json")
    expected_lock = _inventory_document(
        LOCK_KIND,
        _entries_for_roots(
            root,
            AUDIT_V9_FORMAL_ROOTS,
            "source_family_policy_v002_audit_v009_formal_artifacts",
        ),
        "immutable policy artifacts and audit v001-v008 bytes",
    )
    expected_inventory = _inventory_document(
        INVENTORY_KIND,
        _audit_v9_input_entries(root),
        "current policy inputs plus immutable law-repair candidates and runtime bindings",
    )
    if lock != expected_lock:
        raise SourceFamilyPolicyAuditV9Error("source-family audit v009 candidate lock mismatch")
    if inventory != expected_inventory:
        raise SourceFamilyPolicyAuditV9Error(
            "current RAG runtime attestation is outdated; create a successor to audit v009"
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
    _validate_package_checksums(root / POLICY_AUDIT_V8_ROOT)
    checksum_path = root / POLICY_AUDIT_V8_ROOT / "SHA256SUMS.txt"
    if hashlib.sha256(checksum_path.read_bytes()).hexdigest() != V8_CHECKSUMS_SHA256:
        raise SourceFamilyPolicyAuditV9Error("prior audit v008 bytes changed")


def _audit_v9_input_entries(root: Path) -> list[dict[str, Any]]:
    entries = _audit_v8_input_entries(root)
    entries.extend(
        _file_entries(
            root,
            [root / path for path in (*AUDIT_V9_INPUT_PATHS, *REPAIR_INPUT_PATHS)],
            "source_family_policy_v002_audit_v009",
        )
    )
    entries.extend(
        _entries_for_roots(
            root,
            (
                Path("data/rag-v2/candidates/v004"),
                Path("data/rag-v3/governance/source-family-policy/runtime/candidates/v004"),
            ),
            "law_repair_immutable_candidates",
        )
    )
    paths = [entry["path"] for entry in entries]
    if len(paths) != len(set(paths)):
        raise SourceFamilyPolicyAuditV9Error("audit v009 input paths must be unique")
    return sorted(entries, key=lambda entry: entry["path"])


def _refuse_overwrite_v9(destination: Path, label: str) -> None:
    try:
        _refuse_overwrite(destination, label)
    except SourceFamilyPolicyV2Error as exc:
        raise SourceFamilyPolicyAuditV9Error(str(exc)) from exc


def _readme(lock: dict[str, Any], inventory: dict[str, Any]) -> str:
    return (
        "# Source-family policy v002 law-repair projection audit v009\n\n"
        "This successor preserves audit v001-v008 and binds the local v004 law-repair "
        "projection and runtime ID mapping to their implementation and tests.\n\n"
        f"- Current validation inputs: `{inventory['entry_count']}`\n"
        f"- Current inventory SHA-256: `{inventory['inventory_sha256']}`\n"
        f"- Historical artifact entries: `{lock['entry_count']}`\n"
        f"- Historical lock SHA-256: `{lock['inventory_sha256']}`\n"
        "- Runtime policy v003 decisions: unchanged\n"
        "- Local projection candidate: 726 new IDs, only 71 governance corrections\n"
        "- Runtime policy v004: pinned v003 response policy plus exact projection binding\n"
        "- Live current/stop/eligibility/block/review gates: unchanged\n"
        "- Remote OpenSearch transport: HTTPS with certificate and hostname validation\n"
        "- Search execution: bounded concurrency, dedicated workers, shared deadline\n"
        "- Cancellation: prompt caller cancellation with worker capacity retained until exit\n"
        "- Historical inventories: sealed and validated independently of current HEAD\n"
        "- External synchronization: not authorized\n"
        "- Production: blocked\n"
    )

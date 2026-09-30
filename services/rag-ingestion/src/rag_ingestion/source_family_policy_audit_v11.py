"""Current routing/retrieval attestation; preserve sealed audits through v010."""

from __future__ import annotations

import hashlib
from pathlib import Path

from rag_ingestion.source_family_policy_audit_v9 import (
    AUDIT_V9_FORMAL_ROOTS,
    POLICY_AUDIT_V9_ROOT,
    _audit_v9_input_entries,
)
from rag_ingestion.source_family_policy_audit_v10 import (
    AUDIT_ROOT as PRIOR_ROOT,
)
from rag_ingestion.source_family_policy_audit_v10 import (
    INPUT_PATHS as PRIOR_INPUTS,
)
from rag_ingestion.source_family_policy_audit_v10 import validate as validate_prior
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

AUDIT_ROOT = POLICY_ROOT / "audits/v011/preflight"
PRIOR_SHA = "380725d2bc53dafabf5061f981e800c7a59d1e6474c0186a842e9d6b37738d33"
INPUT_PATHS = (
    "services/rag-ingestion/src/rag_ingestion/source_family_policy_audit_v11.py",
    "services/rag-ingestion/tests/integration/test_source_family_policy_audit_v11.py",
    "scripts/rag/quality_audit.py",
    "scripts/rag/evaluate_quality.py",
    "scripts/rag/evaluate_live_quality.py",
    "scripts/rag/quality_metrics.py",
    "scripts/rag/quality_search.py",
    "evals/rag/.gitattributes",
    "evals/rag/README.md",
    "evals/rag/cases-v1.json",
    "services/core-api/.gitattributes",
    "services/core-api/app/core/config.py",
    "services/core-api/app/services/companion_service.py",
    "services/core-api/app/services/knowledge_intent.py",
    "services/core-api/app/services/knowledge_router.py",
    "services/core-api/tests/unit/test_companion_service.py",
    "services/core-api/tests/unit/test_knowledge_router.py",
    "services/core-api/tests/unit/test_rag_quality_evaluation.py",
    "services/agent-runtime/src/agent_runtime/rag/query_normalization.py",
    "services/agent-runtime/tests/unit/test_query_normalization.py",
    "services/agent-runtime/tests/unit/test_quality_search.py",
)


def documents(root: Path):
    validate_prior(root)
    if hashlib.sha256((root / PRIOR_ROOT / "SHA256SUMS.txt").read_bytes()).hexdigest() != PRIOR_SHA:
        raise SourceFamilyPolicyV2Error("audit v010 bytes changed")
    lock = _inventory_document(
        "quality_v011_prior_lock",
        _entries_for_roots(
            root, (*AUDIT_V9_FORMAL_ROOTS, POLICY_AUDIT_V9_ROOT, PRIOR_ROOT), "prior_artifacts"
        ),
        "immutable predecessors through v010; no authorization changes",
    )
    entries = _audit_v9_input_entries(root)
    entries.extend(_file_entries(root, [root / p for p in PRIOR_INPUTS], "law_sync_v010"))
    seen = {entry["path"] for entry in entries}
    entries.extend(
        _file_entries(root, [root / p for p in INPUT_PATHS if p not in seen], "quality_v011")
    )
    if len({entry["path"] for entry in entries}) != len(entries):
        raise SourceFamilyPolicyV2Error("duplicate current validation input")
    inventory = _inventory_document(
        "quality_v011_current_inputs",
        sorted(entries, key=lambda row: row["path"]),
        "current bounded router, opt-in normalization, quality tools and unchanged governance",
    )
    return lock, inventory


def validate(root: Path, package: Path | None = None):
    root = root.resolve()
    package = _destination(root, package, AUDIT_ROOT)
    _validate_package_checksums(package)
    lock, inventory = documents(root)
    if _read_json(package / "candidate-artifact-lock.json") != lock:
        raise SourceFamilyPolicyV2Error("v011 historical lock mismatch")
    if _read_json(package / "validation-input-inventory.json") != inventory:
        raise SourceFamilyPolicyV2Error("v011 current inputs changed; create a successor")
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
    _refuse_overwrite(destination, "routing quality audit v011")
    lock, inventory = documents(root)
    staged = _new_staging_directory(root, "quality-audit-v011")
    try:
        _write_json(staged / "candidate-artifact-lock.json", lock)
        _write_json(staged / "validation-input-inventory.json", inventory)
        _write_text(
            staged / "README.md",
            "# Routing and retrieval quality audit v011\n\n"
            "Preserves every predecessor through v010 and attests current code/fixture bytes.\n"
            "Historical v009/v010 inventories are sealed, not compared to current source files.\n"
            "v011 is the current implementation gate; changes require a successor.\n"
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

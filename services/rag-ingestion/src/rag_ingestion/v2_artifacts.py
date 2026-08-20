"""Deterministic RagChunkV2 successor-artifact builder.

The builder never calls external services and never mutates the current V1
bundle. It requires a strict raw-LF preflight lock before it can publish a new
local candidate directory.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from rag_ingestion.allowlist import Allowlist, load_allowlist
from rag_ingestion.bulk_ingester import REQUIRED_EMBEDDING_DIMENSION, build_index_document
from rag_ingestion.chunk_loader import load_allowlisted_chunks
from rag_ingestion.validator import ValidatedChunk, validate_chunks

SCHEMA_VERSION = "2.1.0"
ARTIFACT_VERSION = "v002"
ALLOWLIST_VERSION = "v003"
PREFLIGHT_VERSION = "v003"
EVIDENCE_VERSION = "v003"

CANONICAL_TEXT_HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"
COLLECTED_TEST_NODE_HASH_MODE = "sha256_canonical_json_v1"
PREFLIGHT_INVENTORY_FILENAME = "validation-input-inventory.json"
PRIOR_ARTIFACT_LOCK_FILENAME = "prior-artifact-lock.json"
TEST_EXECUTION_RECEIPT_FILENAME = "pytest-execution-receipt.json"

ALLOWLIST_PATH = Path("data/rag-manifest/AI_Reviewed_Embedding_Staging_Allowlist_v002.json")
CHUNKS_DIRECTORY = Path("data/rag-chunks/approved")
SOURCE_REVIEW_PATH = Path(
    "data/rag-manifest/AWS長照_RAG_AI_Source_Review_Current_Candidates_v002.json"
)
V2_SCHEMA_PATH = Path("contracts/schemas/rag/rag-chunk-v2.1.schema.json")
TEST_EVIDENCE_PATH = Path(f"data/rag-v2/evidence/{EVIDENCE_VERSION}/pytest-rag-ingestion.xml")
TEST_EXECUTION_RECEIPT_PATH = Path(
    f"data/rag-v2/evidence/{EVIDENCE_VERSION}/{TEST_EXECUTION_RECEIPT_FILENAME}"
)

_OFFICIAL_AUTHORITIES = frozenset(
    {
        "official_government",
        "official_health_education",
        "official_law",
        "official_manual",
        "official_manual_appendix",
    }
)
_CANONICAL_CURRENT_STATUSES = frozenset({"current", "superseded", "unknown"})
_CANONICAL_VERSION_CHECK_STATUSES = frozenset({"pending", "verified_official_source"})
_CANONICAL_RISK_LEVELS = frozenset({"low", "medium", "high", "high_red_line"})
_CANONICAL_LANGUAGES = frozenset({"en", "zh-Hant"})
_CANONICAL_LOCALES = frozenset({"en-US", "zh-TW"})

_PRIOR_FORMAL_PATHS = (
    Path("data/rag-chunks/README.md"),
    Path("data/rag-chunks/SHA256SUMS.txt"),
    ALLOWLIST_PATH,
    Path("data/rag-manifest/all_current_chunk_catalog_20260802.json"),
    SOURCE_REVIEW_PATH,
)

_VALIDATION_FIXED_PATHS = (
    *_PRIOR_FORMAL_PATHS,
    Path(".gitattributes"),
    Path("services/rag-ingestion/src/rag_ingestion/allowlist.py"),
    Path("services/rag-ingestion/src/rag_ingestion/bulk_ingester.py"),
    Path("services/rag-ingestion/src/rag_ingestion/chunk_loader.py"),
    Path("services/rag-ingestion/src/rag_ingestion/validator.py"),
    Path("services/rag-ingestion/src/rag_ingestion/v2_artifacts.py"),
    Path("services/rag-ingestion/pyproject.toml"),
    Path("services/rag-ingestion/README.md"),
    Path("services/rag-ingestion/uv.lock"),
    Path("scripts/rag/build_v2_artifacts.py"),
    Path("scripts/rag/validate_v2_artifacts.py"),
    Path("data/rag-v2/README.md"),
    Path("data/rag-v2/evidence/README.md"),
    V2_SCHEMA_PATH,
)


class V2ArtifactError(ValueError):
    """Raised before a candidate is published."""


class _DuplicateJsonKey(ValueError):
    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(key)


@dataclass(frozen=True, slots=True)
class V2BuildSummary:
    output_path: Path
    source_count: int
    chunk_count: int
    official_source_count: int
    official_chunk_count: int
    research_source_count: int
    research_chunk_count: int
    retrieval_eligible_count: int
    review_row_count: int
    input_inventory_sha256: str
    prior_lock_sha256: str
    standalone_validation_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "BUILT",
            "artifact_version": ARTIFACT_VERSION,
            "preflight_version": PREFLIGHT_VERSION,
            "evidence_version": EVIDENCE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "output_path": self.output_path.as_posix(),
            "source_count": self.source_count,
            "chunk_count": self.chunk_count,
            "official_source_count": self.official_source_count,
            "official_chunk_count": self.official_chunk_count,
            "research_source_count": self.research_source_count,
            "research_chunk_count": self.research_chunk_count,
            "retrieval_eligible_count": self.retrieval_eligible_count,
            "review_row_count": self.review_row_count,
            "input_inventory_sha256": self.input_inventory_sha256,
            "prior_lock_sha256": self.prior_lock_sha256,
            "standalone_validation_status": self.standalone_validation_status,
            "review_status": "needs_review",
            "production_approved": False,
        }


def prepare_preflight(repository_root: Path, output_root: Path) -> dict[str, Any]:
    """Freeze strict raw-LF inputs and atomically publish the preflight directory."""

    root = repository_root.resolve()
    output_base = output_root.resolve()
    preflight_parent = output_base / "preflight"
    preflight_dir = preflight_parent / PREFLIGHT_VERSION
    if preflight_dir.exists():
        raise V2ArtifactError("preflight evidence already exists; refuse to overwrite")

    inventory_entries = _validation_inventory_entries(root)
    lock_entries = _prior_lock_entries(root)
    inventory = _inventory_document("validation_input_inventory", inventory_entries)
    prior_lock = _inventory_document("prior_artifact_immutable_lock", lock_entries)

    preflight_parent.mkdir(parents=True, exist_ok=True)
    pending_root = output_base / ".pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    temporary_prefix = f"preflight-{PREFLIGHT_VERSION}-"
    temporary_root = Path(tempfile.mkdtemp(prefix=temporary_prefix, dir=pending_root)).resolve()
    temporary_preflight = temporary_root / PREFLIGHT_VERSION
    temporary_preflight.mkdir()
    temporary_inventory_path = temporary_preflight / PREFLIGHT_INVENTORY_FILENAME
    temporary_lock_path = temporary_preflight / PRIOR_ARTIFACT_LOCK_FILENAME
    try:
        _write_canonical_json(temporary_inventory_path, inventory)
        _write_canonical_json(temporary_lock_path, prior_lock)
        if _read_canonical_json(temporary_inventory_path) != inventory:
            raise V2ArtifactError("written validation inventory failed self-verification")
        if _read_canonical_json(temporary_lock_path) != prior_lock:
            raise V2ArtifactError("written prior-artifact lock failed self-verification")
        _assert_inventory_matches(
            inventory,
            _validation_inventory_entries(root),
            "validation input",
            expected_kind="validation_input_inventory",
        )
        _assert_inventory_matches(
            prior_lock,
            _prior_lock_entries(root),
            "prior artifact",
            expected_kind="prior_artifact_immutable_lock",
        )
        _publish_pending_directory(
            temporary_preflight,
            preflight_dir,
            label="preflight evidence",
        )
    finally:
        _cleanup_owned_pending_directory(
            temporary_root,
            pending_root,
            expected_prefix=temporary_prefix,
        )
    inventory_path = preflight_dir / PREFLIGHT_INVENTORY_FILENAME
    lock_path = preflight_dir / PRIOR_ARTIFACT_LOCK_FILENAME
    return {
        "status": "PREFLIGHT_FROZEN",
        "preflight_version": PREFLIGHT_VERSION,
        "hash_mode": CANONICAL_TEXT_HASH_MODE,
        "inventory_path": inventory_path.as_posix(),
        "inventory_sha256": inventory["inventory_sha256"],
        "prior_lock_path": lock_path.as_posix(),
        "prior_lock_sha256": prior_lock["inventory_sha256"],
        "validation_input_count": len(inventory_entries),
        "protected_artifact_count": len(lock_entries),
    }


def run_test_evidence(repository_root: Path, output_root: Path) -> dict[str, Any]:
    """Run the complete suite once and atomically record its formal exit receipt."""

    root = repository_root.resolve()
    output_base = output_root.resolve()
    if output_base != (root / "data/rag-v2").resolve():
        raise V2ArtifactError("formal test evidence requires the canonical data/rag-v2 root")

    preflight_dir = output_base / "preflight" / PREFLIGHT_VERSION
    inventory_path = preflight_dir / PREFLIGHT_INVENTORY_FILENAME
    prior_lock_path = preflight_dir / PRIOR_ARTIFACT_LOCK_FILENAME
    inventory = _read_canonical_json(inventory_path)
    prior_lock = _read_canonical_json(prior_lock_path)
    inventory_file_sha256 = _sha256_file(inventory_path)
    prior_lock_file_sha256 = _sha256_file(prior_lock_path)
    _assert_inventory_matches(
        inventory,
        _validation_inventory_entries(root),
        "validation input",
        expected_kind="validation_input_inventory",
    )
    _assert_inventory_matches(
        prior_lock,
        _prior_lock_entries(root),
        "prior artifact",
        expected_kind="prior_artifact_immutable_lock",
    )

    evidence_parent = output_base / "evidence"
    evidence_dir = evidence_parent / EVIDENCE_VERSION
    if evidence_dir.exists():
        raise V2ArtifactError("formal test evidence already exists; refuse to overwrite")
    evidence_parent.mkdir(parents=True, exist_ok=True)
    pending_root = output_base / ".pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    temporary_prefix = f"evidence-{EVIDENCE_VERSION}-"
    temporary_root = Path(tempfile.mkdtemp(prefix=temporary_prefix, dir=pending_root)).resolve()
    temporary_evidence = temporary_root / EVIDENCE_VERSION
    temporary_evidence.mkdir()
    junit_path = temporary_evidence / TEST_EVIDENCE_PATH.name
    receipt_path = temporary_evidence / TEST_EXECUTION_RECEIPT_FILENAME
    inventory_relative_path = (
        Path("data/rag-v2/preflight") / PREFLIGHT_VERSION / PREFLIGHT_INVENTORY_FILENAME
    ).as_posix()
    prior_lock_relative_path = (
        Path("data/rag-v2/preflight") / PREFLIGHT_VERSION / PRIOR_ARTIFACT_LOCK_FILENAME
    ).as_posix()

    command_display = (
        "python -m pytest services/rag-ingestion/tests --junitxml="
        f"{TEST_EVIDENCE_PATH.as_posix()}"
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        "services/rag-ingestion/tests",
        f"--junitxml={junit_path}",
    ]
    environment = _clean_pytest_environment()
    environment["RAG_V2_VALIDATION_INPUT_INVENTORY_SHA256"] = inventory["inventory_sha256"]
    try:
        started_at = datetime.now().astimezone().isoformat()
        exit_code: int | None = None
        failure_reasons: list[str] = []
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                env=environment,
                capture_output=True,
                timeout=300,
                check=False,
            )
            exit_code = completed.returncode
            if exit_code != 0:
                failure_reasons.append(f"pytest exited with code {exit_code}")
        except subprocess.TimeoutExpired:
            failure_reasons.append("pytest process exceeded the 300-second evidence limit")
        except OSError:
            failure_reasons.append("pytest process could not be started")
        finished_at = datetime.now().astimezone().isoformat()

        try:
            _assert_preflight_unchanged(
                root,
                inventory_path=inventory_path,
                inventory=inventory,
                inventory_file_sha256=inventory_file_sha256,
                prior_lock_path=prior_lock_path,
                prior_lock=prior_lock,
                prior_lock_file_sha256=prior_lock_file_sha256,
            )
        except V2ArtifactError:
            failure_reasons.append("frozen preflight inputs changed during pytest")

        junit_sha256: str | None = None
        if junit_path.is_file():
            try:
                _canonical_lf_bytes(junit_path)
                junit_sha256 = _sha256_file(junit_path)
            except V2ArtifactError:
                failure_reasons.append("pytest JUnit is not strict UTF-8 LF-only text")
        else:
            failure_reasons.append("pytest did not produce JUnit evidence")

        status = "PASS" if exit_code == 0 and not failure_reasons else "FAIL"
        receipt = {
            "schema_version": "1.0.0",
            "artifact_version": ARTIFACT_VERSION,
            "preflight_version": PREFLIGHT_VERSION,
            "evidence_version": EVIDENCE_VERSION,
            "status": status,
            "display_command": command_display,
            "executed_argv": [str(argument) for argument in command],
            "exit_code": exit_code,
            "validation_input_inventory_sha256": inventory["inventory_sha256"],
            "preflight_inventory_path": inventory_relative_path,
            "preflight_inventory_file_sha256": inventory_file_sha256,
            "prior_artifact_lock_sha256": prior_lock["inventory_sha256"],
            "prior_artifact_lock_path": prior_lock_relative_path,
            "prior_artifact_lock_file_sha256": prior_lock_file_sha256,
            "junit_path": TEST_EVIDENCE_PATH.as_posix(),
            "junit_sha256": junit_sha256,
            "started_at": started_at,
            "finished_at": finished_at,
            "failure_reasons": failure_reasons,
            "production_approved": False,
        }
        _write_json_atomic_no_overwrite(receipt_path, receipt)
        if status != "PASS":
            raise V2ArtifactError("formal pytest evidence failed; nothing was published")

        _test_evidence_document(
            junit_path,
            execution_receipt_path=receipt_path,
            required=True,
            repository_root=root,
            validation_inventory_paths={entry["path"] for entry in inventory["entries"]},
            validation_input_inventory_sha256=inventory["inventory_sha256"],
            preflight_inventory_path=inventory_relative_path,
            preflight_inventory_file_sha256=inventory_file_sha256,
            prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
            prior_artifact_lock_path=prior_lock_relative_path,
            prior_artifact_lock_file_sha256=prior_lock_file_sha256,
        )
        _assert_preflight_unchanged(
            root,
            inventory_path=inventory_path,
            inventory=inventory,
            inventory_file_sha256=inventory_file_sha256,
            prior_lock_path=prior_lock_path,
            prior_lock=prior_lock,
            prior_lock_file_sha256=prior_lock_file_sha256,
        )
        _assert_candidate_text_bytes(temporary_evidence)
        _publish_pending_directory(
            temporary_evidence,
            evidence_dir,
            label="formal test evidence",
        )
        return {
            **receipt,
            "receipt_path": TEST_EXECUTION_RECEIPT_PATH.as_posix(),
            "receipt_sha256": _sha256_file(evidence_dir / TEST_EXECUTION_RECEIPT_FILENAME),
        }
    finally:
        _cleanup_owned_pending_directory(
            temporary_root,
            pending_root,
            expected_prefix=temporary_prefix,
        )


def build_v2_artifacts(
    repository_root: Path,
    output_root: Path,
    *,
    require_test_evidence: bool = False,
) -> V2BuildSummary:
    """Build a complete local candidate after verifying frozen preflight evidence."""

    root = repository_root.resolve()
    output_base = output_root.resolve()
    candidate_dir = output_base / "candidates" / ARTIFACT_VERSION
    if candidate_dir.exists():
        raise V2ArtifactError("candidate output already exists; refuse to overwrite")

    preflight_dir = output_base / "preflight" / PREFLIGHT_VERSION
    inventory_path = preflight_dir / PREFLIGHT_INVENTORY_FILENAME
    prior_lock_path = preflight_dir / PRIOR_ARTIFACT_LOCK_FILENAME
    inventory = _read_canonical_json(inventory_path)
    prior_lock = _read_canonical_json(prior_lock_path)
    inventory_file_sha256 = _sha256_file(inventory_path)
    prior_lock_file_sha256 = _sha256_file(prior_lock_path)
    active_junit_path = root / TEST_EVIDENCE_PATH
    active_receipt_path = root / TEST_EXECUTION_RECEIPT_PATH
    _assert_inventory_matches(
        inventory,
        _validation_inventory_entries(root),
        "validation input",
        expected_kind="validation_input_inventory",
    )
    _assert_inventory_matches(
        prior_lock,
        _prior_lock_entries(root),
        "prior artifact",
        expected_kind="prior_artifact_immutable_lock",
    )

    allowlist = load_allowlist(root / ALLOWLIST_PATH)
    loaded = load_allowlisted_chunks(root / CHUNKS_DIRECTORY, allowlist)
    validation = validate_chunks(loaded, allowlist)
    titles = _source_titles(root / SOURCE_REVIEW_PATH)
    source_numbers = {
        source["source_id"]: source["source_number"]
        for source in allowlist.raw["sources"]
        if isinstance(source, dict)
    }

    records_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prior_by_id: dict[str, ValidatedChunk] = {}
    crosswalk: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for chunk in validation.chunks:
        source_id = chunk.data["source_id"]
        prior_path = chunk.loaded.file_path.relative_to(root).as_posix()
        record = _to_v2_record(
            chunk,
            title=titles.get(source_id) or chunk.allowlist_entry.source_title,
            prior_path=prior_path,
        )
        records_by_source[source_id].append(record)
        prior_by_id[chunk.chunk_id] = chunk
        crosswalk.append(_crosswalk_record(record, chunk, prior_path))
        warnings = record["provenance"]["mapping_warnings"]
        block_reasons = record["retrieval_policy"]["retrieval_block_reasons"]
        if warnings or block_reasons:
            review_rows.append(
                {
                    "schema_version": "1.0.0",
                    "worksheet_version": ARTIFACT_VERSION,
                    "source_id": source_id,
                    "prior_chunk_id": chunk.chunk_id,
                    "successor_chunk_id": record["identity"]["chunk_id"],
                    "retrieval_block_reasons": block_reasons,
                    "mapping_warnings": warnings,
                    "review_status": "needs_review",
                    "production_approved": False,
                }
            )

    _validate_records(records_by_source, prior_by_id)
    candidate_dir.parent.mkdir(parents=True, exist_ok=True)
    pending_root = output_base / ".pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    temporary_prefix = f"candidate-{ARTIFACT_VERSION}-"
    temporary_root = Path(tempfile.mkdtemp(prefix=temporary_prefix, dir=pending_root)).resolve()
    temporary_candidate = temporary_root / ARTIFACT_VERSION
    temporary_candidate.mkdir(parents=True)
    standalone_validation_status = "NOT_REQUIRED"
    try:
        chunk_files = _write_chunk_files(temporary_candidate, records_by_source)
        all_records = [
            record
            for source_id in sorted(records_by_source, key=source_numbers.__getitem__)
            for record in records_by_source[source_id]
        ]
        source_manifest = _source_manifest(all_records, source_numbers, titles)
        chunk_manifest = _chunk_file_manifest(chunk_files, records_by_source)
        candidate_allowlist = _candidate_allowlist(
            allowlist,
            all_records,
            source_numbers,
        )
        enum_evidence = _enum_evidence(all_records, inventory["inventory_sha256"])
        nested_v1_input_count = sum(
            isinstance(chunk.data.get("metadata"), dict) for chunk in validation.chunks
        )
        flat_v1_input_count = validation.chunk_count - nested_v1_input_count
        version_diff = _version_difference_summary(
            all_records,
            review_rows,
            nested_v1_input_count=nested_v1_input_count,
            flat_v1_input_count=flat_v1_input_count,
        )
        validation_report = _validation_report(
            all_records,
            review_rows,
            inventory_sha256=inventory["inventory_sha256"],
            prior_lock_sha256=prior_lock["inventory_sha256"],
        )
        test_evidence = _test_evidence_document(
            active_junit_path,
            execution_receipt_path=active_receipt_path,
            required=require_test_evidence,
            repository_root=root,
            validation_inventory_paths={entry["path"] for entry in inventory["entries"]},
            validation_input_inventory_sha256=inventory["inventory_sha256"],
            preflight_inventory_path=(
                Path("data/rag-v2/preflight") / PREFLIGHT_VERSION / PREFLIGHT_INVENTORY_FILENAME
            ).as_posix(),
            preflight_inventory_file_sha256=inventory_file_sha256,
            prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
            prior_artifact_lock_path=(
                Path("data/rag-v2/preflight") / PREFLIGHT_VERSION / PRIOR_ARTIFACT_LOCK_FILENAME
            ).as_posix(),
            prior_artifact_lock_file_sha256=prior_lock_file_sha256,
        )

        _write_json(
            temporary_candidate / "manifests" / f"source-manifest-{ARTIFACT_VERSION}.json",
            source_manifest,
        )
        _write_json(
            temporary_candidate / "manifests" / f"chunk-file-manifest-{ARTIFACT_VERSION}.json",
            chunk_manifest,
        )
        _write_json(
            temporary_candidate
            / "manifests"
            / f"embedding-staging-allowlist-{ALLOWLIST_VERSION}.json",
            candidate_allowlist,
        )
        _write_json(
            temporary_candidate / "governance" / f"enum-evidence-{ARTIFACT_VERSION}.json",
            enum_evidence,
        )
        _write_jsonl(
            temporary_candidate / "crosswalk" / f"chunk-id-crosswalk-{ARTIFACT_VERSION}.jsonl",
            crosswalk,
        )
        _write_jsonl(
            temporary_candidate / "review" / f"human-review-worksheet-{ARTIFACT_VERSION}.jsonl",
            review_rows,
        )
        _write_json(
            temporary_candidate / "reports" / f"version-difference-summary-{ARTIFACT_VERSION}.json",
            version_diff,
        )
        _write_json(
            temporary_candidate / "reports" / f"validation-report-{ARTIFACT_VERSION}.json",
            validation_report,
        )
        _write_json(
            temporary_candidate / "reports" / f"test-evidence-{ARTIFACT_VERSION}.json",
            test_evidence,
        )
        if test_evidence["status"] == "PASS":
            copied_junit_path = (
                temporary_candidate / "reports" / f"pytest-rag-ingestion-{ARTIFACT_VERSION}.xml"
            )
            shutil.copyfile(
                active_junit_path,
                copied_junit_path,
            )
            _assert_file_sha256(
                copied_junit_path,
                test_evidence["evidence_sha256"],
                "copied pytest JUnit evidence",
            )
            copied_receipt_path = (
                temporary_candidate
                / "reports"
                / f"pytest-execution-receipt-{ARTIFACT_VERSION}.json"
            )
            shutil.copyfile(active_receipt_path, copied_receipt_path)
            _assert_file_sha256(
                copied_receipt_path,
                test_evidence["execution_receipt_sha256"],
                "copied pytest execution receipt",
            )
        _write_text(temporary_candidate / "README.md", _candidate_readme())
        _write_checksums(temporary_candidate)
        _assert_candidate_text_bytes(temporary_candidate)
        if require_test_evidence:
            _run_standalone_candidate_validator(
                root,
                temporary_candidate,
                root / V2_SCHEMA_PATH,
            )
            standalone_validation_status = "PASS"

        _assert_file_sha256(
            inventory_path,
            inventory_file_sha256,
            "preflight validation inventory",
        )
        _assert_file_sha256(
            prior_lock_path,
            prior_lock_file_sha256,
            "preflight prior-artifact lock",
        )
        _assert_inventory_matches(
            inventory,
            _validation_inventory_entries(root),
            "validation input",
            expected_kind="validation_input_inventory",
        )
        _assert_inventory_matches(
            prior_lock,
            _prior_lock_entries(root),
            "prior artifact",
            expected_kind="prior_artifact_immutable_lock",
        )
        if test_evidence["status"] == "PASS":
            _assert_file_sha256(
                active_junit_path,
                test_evidence["evidence_sha256"],
                "pytest JUnit evidence",
            )
            _assert_file_sha256(
                active_receipt_path,
                test_evidence["execution_receipt_sha256"],
                "pytest execution receipt",
            )
        _publish_pending_directory(
            temporary_candidate,
            candidate_dir,
            label="candidate output",
        )
    finally:
        _cleanup_owned_pending_directory(
            temporary_root,
            pending_root,
            expected_prefix=temporary_prefix,
        )

    official_sources = {
        record["identity"]["source_id"]
        for records in records_by_source.values()
        for record in records
        if record["provenance"]["is_official_source"]
    }
    official_chunks = sum(
        record["provenance"]["is_official_source"]
        for records in records_by_source.values()
        for record in records
    )
    eligible = sum(
        record["retrieval_policy"]["retrieval_eligible"]
        for records in records_by_source.values()
        for record in records
    )
    return V2BuildSummary(
        output_path=candidate_dir,
        source_count=len(records_by_source),
        chunk_count=sum(len(records) for records in records_by_source.values()),
        official_source_count=len(official_sources),
        official_chunk_count=official_chunks,
        research_source_count=len(records_by_source) - len(official_sources),
        research_chunk_count=validation.chunk_count - official_chunks,
        retrieval_eligible_count=eligible,
        review_row_count=len(review_rows),
        input_inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=prior_lock["inventory_sha256"],
        standalone_validation_status=standalone_validation_status,
    )


def _to_v2_record(
    chunk: ValidatedChunk,
    *,
    title: str | None,
    prior_path: str,
) -> dict[str, Any]:
    data = chunk.data
    warnings: list[str] = []
    policy = build_index_document(chunk, [0.0] * REQUIRED_EMBEDDING_DIMENSION)
    source_id = data["source_id"]
    chunk_index = data["chunk_index"]
    successor_id = f"{source_id}_rag_v2_{ARTIFACT_VERSION}_{chunk_index:04d}"

    raw_current_status = _string_value(data, "current_status", warnings)
    if raw_current_status == "needs_verification":
        current_status = "unknown"
        warnings.append("current_status_needs_verification_preserved_as_unknown")
    elif raw_current_status in _CANONICAL_CURRENT_STATUSES:
        current_status = raw_current_status
    else:
        current_status = "unknown"
        if raw_current_status is not None:
            warnings.append("current_status_not_in_v2_enum")

    raw_version_check = _string_value(data, "version_check_status", warnings)
    version_check_status = raw_version_check or "pending"
    if version_check_status not in _CANONICAL_VERSION_CHECK_STATUSES:
        warnings.append("version_check_status_not_in_v2_enum")
        version_check_status = "pending"

    raw_risk = _string_value(data, "risk_level", warnings)
    risk_level = raw_risk if raw_risk in _CANONICAL_RISK_LEVELS else None
    if raw_risk is not None and risk_level is None:
        warnings.append("risk_level_not_in_v2_enum")

    stop_normal_rag = _bool_value(data, "stop_normal_rag", warnings)
    requires_human_review = _bool_value(data, "requires_human_review", warnings)
    if requires_human_review is None:
        requires_human_review = True
        warnings.append("requires_human_review_missing_conservative_true")

    language, locale = _normalize_language_locale(data, warnings)
    page_start = _positive_int_value(
        data, ("physical_page_start", "page_start"), "physical_page_start", warnings
    )
    page_end = _positive_int_value(
        data, ("physical_page_end", "page_end"), "physical_page_end", warnings
    )
    printed_page_start = _positive_int_value(
        data, ("printed_page_start",), "printed_page_start", warnings
    )
    printed_page_end = _positive_int_value(
        data, ("printed_page_end",), "printed_page_end", warnings
    )
    _validate_page_pair(page_start, page_end, "physical_page", warnings)
    _validate_page_pair(printed_page_start, printed_page_end, "printed_page", warnings)

    authority_level = _string_value(data, "authority_level", warnings)
    source_type = _string_value(data, "source_type", warnings)
    is_official = authority_level in _OFFICIAL_AUTHORITIES
    if authority_level is None:
        warnings.append("authority_level_missing")
    if not is_official and authority_level is not None:
        warnings.append("non_official_source_preserved_as_research_evidence")

    direct_source_url = _url_value(data, "official_source_url", warnings)
    source_page_url = _url_value(data, "official_source_page_url", warnings)
    direct_official_source_url = direct_source_url if is_official else None
    official_source_page_url = source_page_url if is_official else None

    record = {
        "schema_version": SCHEMA_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "identity": {
            "chunk_id": successor_id,
            "prior_chunk_id": chunk.chunk_id,
            "source_id": source_id,
            "chunk_file_id": f"{source_id}_rag_v2_{ARTIFACT_VERSION}",
            "prior_chunk_file_id": _string_value(data, "chunk_file_id", warnings),
            "chunk_index": chunk_index,
        },
        "content": {
            "text": chunk.text,
            "embedding_text": chunk.embedding_text,
            "char_count": len(chunk.text),
            "embedding_char_count": len(chunk.embedding_text),
            "text_sha256": chunk.text_sha256,
            "embedding_text_sha256": chunk.embedding_text_sha256,
            "content_type": _string_value(data, "chunk_type", warnings),
            "language": language,
            "locale": locale,
        },
        "citation": {
            "title": title or policy["document_name"],
            "publisher": _first_string_alias(
                data, ("publish_agency", "competent_authority"), warnings
            ),
            "section": policy["section"],
            "physical_page_start": page_start,
            "physical_page_end": page_end,
            "printed_page_start": printed_page_start,
            "printed_page_end": printed_page_end,
            "source_locator": _string_value(data, "source_locator", warnings),
            "direct_source_url": direct_source_url,
            "source_page_url": source_page_url,
            "direct_official_source_url": direct_official_source_url,
            "official_source_page_url": official_source_page_url,
            "license_evidence_url": _url_value(data, "license_source_url", warnings),
            "storage_url": _url_value(data, "storage_url", warnings),
        },
        "retrieval_policy": {
            "allowed_audiences": policy["allowed_audiences"],
            "allowed_purposes": policy["allowed_purposes"],
            "risk_level": risk_level,
            "requires_official_assessment": policy["requires_official_assessment"],
            "requires_professional_assessment": policy["requires_professional_assessment"],
            "requires_human_review": requires_human_review,
            "stop_normal_rag": stop_normal_rag,
            "retrieval_eligible": policy["retrieval_eligible"],
            "retrieval_block_reasons": policy["retrieval_block_reasons"],
        },
        "governance": {
            "review_status": "needs_review",
            "current_status": current_status,
            "version_check_status": version_check_status,
            "license_status": _string_value(data, "license_status", warnings) or "unknown",
            "embedding_status": "not_started",
            "ingestion_status": "staging",
            "human_source_review": "not_completed",
            "production_gate": "blocked",
            "production_approved": False,
            "data_classification": _string_value(data, "data_classification", warnings),
            "distribution_scope": _string_value(data, "share_scope", warnings),
            "storage_target": "local_pending_upload",
        },
        "provenance": {
            "source_version": _first_string_alias(
                data,
                ("source_version", "document_version", "source_version_date"),
                warnings,
            )
            or chunk.allowlist_entry.source_version,
            "source_version_date": _string_value(data, "source_version_date", warnings),
            "version_published_at": _string_value(data, "version_published_at", warnings),
            "source_page_updated_at": _string_value(data, "source_page_updated_at", warnings),
            "published_at": _string_value(data, "published_at", warnings),
            "last_verified_at": _first_string_alias(
                data, ("last_verified_at", "last_version_checked_at"), warnings
            ),
            "parser_version": _string_value(data, "parser_version", warnings),
            "chunker_version": _string_value(data, "chunker_version", warnings),
            "pipeline_version": _string_value(data, "pipeline_version", warnings),
            "prior_artifact_version": _string_value(data, "artifact_version", warnings),
            "prior_delivery_version": _string_value(data, "delivery_version", warnings),
            "source_file": _string_value(data, "source_file", warnings),
            "prior_artifact_path": prior_path,
            "authority_level": authority_level,
            "source_type": source_type,
            "is_official_source": is_official,
            "mapping_warnings": sorted(set(warnings)),
        },
    }
    if direct_source_url is None and source_page_url is None:
        record["provenance"]["mapping_warnings"].append("source_url_missing")
    if is_official and (direct_official_source_url is None and official_source_page_url is None):
        record["provenance"]["mapping_warnings"].append("official_source_url_missing")
    if not is_official and record["governance"]["distribution_scope"] != "research_evidence":
        record["provenance"]["mapping_warnings"].append(
            "non_official_distribution_scope_preserved_for_review"
        )
    if record["citation"]["source_locator"] is None:
        record["provenance"]["mapping_warnings"].append("source_locator_missing")
    record["provenance"]["mapping_warnings"] = sorted(set(record["provenance"]["mapping_warnings"]))
    return record


def _crosswalk_record(
    record: dict[str, Any], chunk: ValidatedChunk, prior_path: str
) -> dict[str, Any]:
    identity = record["identity"]
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "source_id": identity["source_id"],
        "prior_chunk_id": chunk.chunk_id,
        "supersedes_artifact_version": "v001",
        "supersedes_chunk_id": (f"{identity['source_id']}_rag_v2_{identity['chunk_index']:04d}"),
        "successor_chunk_id": identity["chunk_id"],
        "relationship": "metadata_successor",
        "prior_artifact_path": prior_path,
        "text_sha256_equal": record["content"]["text_sha256"] == chunk.text_sha256,
        "embedding_text_sha256_equal": (
            record["content"]["embedding_text_sha256"] == chunk.embedding_text_sha256
        ),
        "status_change_recommendation": "human_review_required",
        "status_changed_automatically": False,
    }


def _write_chunk_files(
    candidate_dir: Path, records_by_source: Mapping[str, Sequence[dict[str, Any]]]
) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for source_id in sorted(records_by_source):
        records = records_by_source[source_id]
        relative_path = Path("chunks") / f"{source_id}.rag-chunk-v2.{ARTIFACT_VERSION}.jsonl"
        path = candidate_dir / relative_path
        _write_jsonl(path, records)
        files.append(
            {
                "source_id": source_id,
                "chunk_file_id": records[0]["identity"]["chunk_file_id"],
                "path": relative_path.as_posix(),
                "chunk_count": len(records),
                "sha256": _sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return files


def _source_manifest(
    records: Sequence[dict[str, Any]],
    source_numbers: Mapping[str, int],
    titles: Mapping[str, str],
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["identity"]["source_id"]].append(record)
    sources: list[dict[str, Any]] = []
    for source_id in sorted(grouped, key=source_numbers.__getitem__):
        source_records = grouped[source_id]
        first = source_records[0]
        sources.append(
            {
                "source_number": source_numbers[source_id],
                "source_id": source_id,
                "title": titles.get(source_id) or first["citation"]["title"],
                "authority_level": first["provenance"]["authority_level"],
                "source_type": first["provenance"]["source_type"],
                "is_official_source": first["provenance"]["is_official_source"],
                "chunk_count": len(source_records),
                "source_versions": _unique_values(
                    record["provenance"]["source_version"] for record in source_records
                ),
                "direct_source_urls": _unique_values(
                    record["citation"]["direct_source_url"] for record in source_records
                ),
                "source_page_urls": _unique_values(
                    record["citation"]["source_page_url"] for record in source_records
                ),
                "direct_official_source_urls": _unique_values(
                    record["citation"]["direct_official_source_url"] for record in source_records
                ),
                "official_source_page_urls": _unique_values(
                    record["citation"]["official_source_page_url"] for record in source_records
                ),
                "license_evidence_urls": _unique_values(
                    record["citation"]["license_evidence_url"] for record in source_records
                ),
                "storage_urls": _unique_values(
                    record["citation"]["storage_url"] for record in source_records
                ),
                "review_status": "needs_review",
                "ingestion_status": "staging",
                "production_approved": False,
                "storage_target": "local_pending_upload",
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "source_count": len(sources),
        "chunk_count": len(records),
        "sources": sources,
    }


def _chunk_file_manifest(
    files: Sequence[dict[str, Any]],
    records_by_source: Mapping[str, Sequence[dict[str, Any]]],
) -> dict[str, Any]:
    entries = []
    for item in sorted(files, key=lambda value: value["source_id"]):
        records = records_by_source[item["source_id"]]
        entries.append(
            {
                **item,
                "schema_version": SCHEMA_VERSION,
                "extension_schema_version": None,
                "artifact_version": ARTIFACT_VERSION,
                "chunk_size_target": 600,
                "chunk_overlap": 0,
                "parser_versions": _unique_values(
                    record["provenance"]["parser_version"] for record in records
                ),
                "chunker_versions": _unique_values(
                    record["provenance"]["chunker_version"] for record in records
                ),
                "review_status": "needs_review",
                "ingestion_status": "staging",
                "embedding_status": "not_started",
                "production_approved": False,
                "storage_target": "local_pending_upload",
            }
        )
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "chunk_file_count": len(entries),
        "chunk_count": sum(item["chunk_count"] for item in entries),
        "files": entries,
    }


def _candidate_allowlist(
    allowlist: Allowlist,
    records: Sequence[dict[str, Any]],
    source_numbers: Mapping[str, int],
) -> dict[str, Any]:
    document = {
        key: value
        for key, value in allowlist.raw.items()
        if key not in {"schema_version", "sources", "entries", "source_count", "chunk_count"}
    }
    source_templates = {
        item["source_id"]: dict(item) for item in allowlist.raw["sources"] if isinstance(item, dict)
    }
    counts = Counter(record["identity"]["source_id"] for record in records)
    sources = []
    for source_id in sorted(counts, key=source_numbers.__getitem__):
        source = source_templates[source_id]
        source["chunk_count"] = counts[source_id]
        source["successor_artifact_version"] = ARTIFACT_VERSION
        source["review_status"] = "needs_review"
        source["human_source_review"] = "NOT_COMPLETED"
        source["production_gate"] = "BLOCKED"
        source["storage_target"] = "local_pending_upload"
        sources.append(source)
    entries = []
    for record in records:
        identity = record["identity"]
        content = record["content"]
        entries.append(
            {
                "source_number": source_numbers[identity["source_id"]],
                "source_id": identity["source_id"],
                "chunk_id": identity["chunk_id"],
                "prior_chunk_id": identity["prior_chunk_id"],
                "supersedes_artifact_version": "v001",
                "supersedes_chunk_id": (
                    f"{identity['source_id']}_rag_v2_{identity['chunk_index']:04d}"
                ),
                "chunk_index": identity["chunk_index"],
                "text_sha256": content["text_sha256"],
                "embedding_text_sha256": content["embedding_text_sha256"],
                "allowed_use": allowlist.raw["allowed_use"],
                "signature_required": True,
                "review_status": "needs_review",
                "human_source_review": "NOT_COMPLETED",
                "embedding_status": "NOT_STARTED",
                "opensearch_indexing_status": "NOT_STARTED",
                "production_gate": "BLOCKED",
                "retrieval_eligible": record["retrieval_policy"]["retrieval_eligible"],
            }
        )
    return {
        "schema_version": ALLOWLIST_VERSION,
        "artifact_version": ARTIFACT_VERSION,
        "supersedes_allowlist_sha256": allowlist.sha256,
        "source_count": len(sources),
        "chunk_count": len(entries),
        "sources": sources,
        "entries": entries,
        **document,
    }


def _enum_evidence(
    records: Sequence[dict[str, Any]], input_inventory_sha256: str
) -> dict[str, Any]:
    selectors = {
        "authority_level": lambda record: record["provenance"]["authority_level"],
        "source_type": lambda record: record["provenance"]["source_type"],
        "content_type": lambda record: record["content"]["content_type"],
        "language": lambda record: record["content"]["language"],
        "locale": lambda record: record["content"]["locale"],
        "risk_level": lambda record: record["retrieval_policy"]["risk_level"],
        "current_status": lambda record: record["governance"]["current_status"],
        "version_check_status": lambda record: record["governance"]["version_check_status"],
        "license_status": lambda record: record["governance"]["license_status"],
        "data_classification": lambda record: record["governance"]["data_classification"],
        "distribution_scope": lambda record: record["governance"]["distribution_scope"],
    }
    fields = {}
    for field, selector in selectors.items():
        values = _unique_values(selector(record) for record in records)
        evidence_items = []
        for value in values:
            matching_records = [record for record in records if selector(record) == value]
            if not matching_records:
                raise V2ArtifactError(f"enum evidence is missing a record for {field}")
            selected = min(
                matching_records,
                key=lambda record: (
                    record["provenance"]["prior_artifact_path"],
                    record["identity"]["prior_chunk_id"],
                ),
            )
            evidence_items.append(
                {
                    "value": value,
                    "path": selected["provenance"]["prior_artifact_path"],
                    "prior_chunk_id": selected["identity"]["prior_chunk_id"],
                    "source_locator": selected["citation"]["source_locator"],
                    "field": field,
                }
            )
        if {_json_token(item["value"]) for item in evidence_items} != {
            _json_token(value) for value in values
        }:
            raise V2ArtifactError(f"enum evidence does not cover every value for {field}")
        fields[field] = {
            "classification": "controlled_enum",
            "canonical_values": values,
            "evidence": evidence_items,
        }
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "scope": "source-scoped evidence snapshot; not a canonical global registry",
        "validation_input_inventory_sha256": input_inventory_sha256,
        "fields": fields,
    }


def _version_difference_summary(
    records: Sequence[dict[str, Any]],
    review_rows: Sequence[dict[str, Any]],
    *,
    nested_v1_input_count: int,
    flat_v1_input_count: int,
) -> dict[str, Any]:
    if nested_v1_input_count + flat_v1_input_count != len(records):
        raise V2ArtifactError("V1 input shape counts do not match the validated chunk count")
    warning_counts = Counter(
        warning for record in records for warning in record["provenance"]["mapping_warnings"]
    )
    block_counts = Counter(
        reason
        for record in records
        for reason in record["retrieval_policy"]["retrieval_block_reasons"]
    )
    official_chunks = sum(record["provenance"]["is_official_source"] for record in records)
    official_sources = {
        record["identity"]["source_id"]
        for record in records
        if record["provenance"]["is_official_source"]
    }
    all_sources = {record["identity"]["source_id"] for record in records}
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "prior_artifact_version": "v001",
        "successor_artifact_version": ARTIFACT_VERSION,
        "prior_schema_version": "2.0.0",
        "successor_schema_version": SCHEMA_VERSION,
        "chunk_id_transition": {
            "from_pattern": "{source_id}_rag_v2_{chunk_index:04d}",
            "to_pattern": f"{{source_id}}_rag_v2_{ARTIFACT_VERSION}_{{chunk_index:04d}}",
            "reason": "v002 uses version-qualified successor identities",
        },
        "prior_shape": {"canonical_rag_chunk_v2_chunks": len(records)},
        "successor_shape": {"canonical_rag_chunk_v2_chunks": len(records)},
        "underlying_v1_input_shape": {
            "nested_metadata_chunks": nested_v1_input_count,
            "flat_metadata_chunks": flat_v1_input_count,
        },
        "v001_to_v002_changes": [
            "version-qualified successor chunk IDs",
            "neutral source URL fields separated from official-only URL fields",
            "strict raw-LF preflight inventory and evidence binding",
        ],
        "source_count": len(all_sources),
        "chunk_count": len(records),
        "official_source_count": len(official_sources),
        "official_chunk_count": official_chunks,
        "research_source_count": len(all_sources) - len(official_sources),
        "research_chunk_count": len(records) - official_chunks,
        "text_changed_count": 0,
        "embedding_text_changed_count": 0,
        "chunk_id_changed_count": len(records),
        "superseded_v001_id_count": len(records),
        "successor_id_count": len(records),
        "review_row_count": len(review_rows),
        "mapping_warning_counts": dict(sorted(warning_counts.items())),
        "retrieval_block_reason_counts": dict(sorted(block_counts.items())),
        "status_changes_applied_automatically": False,
        "production_approved": False,
    }


def _validation_report(
    records: Sequence[dict[str, Any]],
    review_rows: Sequence[dict[str, Any]],
    *,
    inventory_sha256: str,
    prior_lock_sha256: str,
) -> dict[str, Any]:
    eligible = sum(record["retrieval_policy"]["retrieval_eligible"] for record in records)
    checks = [
        {"name": "chunk_count", "status": "PASS", "observed": len(records)},
        {
            "name": "unique_successor_ids",
            "status": "PASS",
            "observed": len({record["identity"]["chunk_id"] for record in records}),
        },
        {"name": "text_bytes_unchanged", "status": "PASS", "observed": len(records)},
        {
            "name": "embedding_text_bytes_unchanged",
            "status": "PASS",
            "observed": len(records),
        },
        {"name": "retrieval_eligible", "status": "PASS", "observed": eligible},
        {
            "name": "human_review_rows",
            "status": "PASS",
            "observed": len(review_rows),
        },
        {
            "name": "production_approved_false",
            "status": "PASS",
            "observed": len(records),
        },
        {"name": "prior_artifact_lock", "status": "PASS"},
    ]
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "preflight_version": PREFLIGHT_VERSION,
        "status": "PASS",
        "pass_count": len(checks),
        "fail_count": 0,
        "validation_input_inventory_sha256": inventory_sha256,
        "prior_artifact_lock_sha256": prior_lock_sha256,
        "checks": checks,
        "review_status": "needs_review",
        "production_approved": False,
    }


def _junit_testcase_summary(root: ET.Element) -> dict[str, Any]:
    identities: list[dict[str, str]] = []
    outcomes = {"failures": 0, "errors": 0, "skipped": 0}
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname")
        name = testcase.attrib.get("name")
        if not classname or not name:
            raise V2ArtifactError("pytest JUnit testcase identity is incomplete")
        identities.append({"classname": classname, "name": name})
        outcome_elements = [
            child.tag for child in testcase if child.tag in {"failure", "error", "skipped"}
        ]
        if len(outcome_elements) > 1:
            raise V2ArtifactError("pytest JUnit testcase has conflicting outcomes")
        if outcome_elements:
            outcome_key = {
                "failure": "failures",
                "error": "errors",
                "skipped": "skipped",
            }[outcome_elements[0]]
            outcomes[outcome_key] += 1
    identities.sort(key=lambda item: (item["classname"], item["name"]))
    identity_tokens = [_json_token(identity) for identity in identities]
    if len(identity_tokens) != len(set(identity_tokens)):
        raise V2ArtifactError("pytest JUnit testcase identities are not unique")
    return {"identities": identities, **outcomes}


def _test_evidence_document(
    path: Path,
    *,
    execution_receipt_path: Path,
    required: bool,
    repository_root: Path,
    validation_inventory_paths: Iterable[str],
    validation_input_inventory_sha256: str,
    preflight_inventory_path: str,
    preflight_inventory_file_sha256: str,
    prior_artifact_lock_sha256: str,
    prior_artifact_lock_path: str,
    prior_artifact_lock_file_sha256: str,
) -> dict[str, Any]:
    if not required:
        return {
            "schema_version": "1.0.0",
            "artifact_version": ARTIFACT_VERSION,
            "evidence_version": EVIDENCE_VERSION,
            "status": "NOT_REQUIRED",
            "evidence_path": TEST_EVIDENCE_PATH.as_posix(),
            "production_approved": False,
        }
    if not path.is_file():
        raise V2ArtifactError("pytest JUnit evidence is required before a formal candidate build")
    execution_receipt = _validated_execution_receipt(
        execution_receipt_path,
        junit_path=path,
        repository_root=repository_root,
        validation_input_inventory_sha256=validation_input_inventory_sha256,
        preflight_inventory_path=preflight_inventory_path,
        preflight_inventory_file_sha256=preflight_inventory_file_sha256,
        prior_artifact_lock_sha256=prior_artifact_lock_sha256,
        prior_artifact_lock_path=prior_artifact_lock_path,
        prior_artifact_lock_file_sha256=prior_artifact_lock_file_sha256,
    )
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise V2ArtifactError("pytest JUnit evidence is unreadable") from exc
    all_suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    suites = [suite for suite in all_suites if not list(suite.findall("testsuite"))]
    if not suites:
        raise V2ArtifactError("pytest JUnit evidence contains no test suites")
    try:
        totals = {
            name: sum(int(suite.attrib.get(name, "0")) for suite in suites)
            for name in ("tests", "failures", "errors", "skipped")
        }
        execution_time_seconds = sum(float(suite.attrib["time"]) for suite in suites)
    except (KeyError, TypeError, ValueError) as exc:
        raise V2ArtifactError("pytest JUnit evidence has invalid counts or time") from exc
    if totals["tests"] < 1:
        raise V2ArtifactError("pytest JUnit evidence contains no tests")
    if any(total < 0 for total in totals.values()):
        raise V2ArtifactError("pytest JUnit evidence contains a negative count")
    if not math.isfinite(execution_time_seconds) or execution_time_seconds < 0:
        raise V2ArtifactError("pytest JUnit evidence contains an invalid execution time")
    testcase_summary = _junit_testcase_summary(root)
    if len(testcase_summary["identities"]) != totals["tests"]:
        raise V2ArtifactError("pytest JUnit testcase count does not match suite totals")
    for field in ("failures", "errors", "skipped"):
        if testcase_summary[field] != totals[field]:
            raise V2ArtifactError(f"pytest JUnit testcase {field} do not match suite totals")
    if totals["failures"] or totals["errors"] or totals["skipped"]:
        raise V2ArtifactError("pytest JUnit evidence contains failed, errored, or skipped tests")

    collected_tests = _collect_test_node_ids(repository_root)
    if totals["tests"] != collected_tests["count"]:
        raise V2ArtifactError(
            "pytest JUnit evidence does not cover the complete collected test suite"
        )
    if testcase_summary["identities"] != collected_tests["testcase_identities"]:
        raise V2ArtifactError(
            "pytest JUnit testcase identities do not match independent collection"
        )
    collected_repository_paths = {
        f"services/rag-ingestion/{path}" for path in collected_tests["files"]
    }
    if not collected_repository_paths <= set(validation_inventory_paths):
        raise V2ArtifactError(
            "collected pytest file is missing from the validation input inventory"
        )

    property_values: dict[str, list[str | None]] = defaultdict(list)
    for element in root.iter("property"):
        name = element.attrib.get("name")
        if name:
            property_values[name].append(element.attrib.get("value"))
    expected_properties = {
        "validation_input_inventory_sha256": validation_input_inventory_sha256,
        "collected_test_node_ids_sha256": collected_tests["sha256"],
        "collected_test_node_count": str(collected_tests["count"]),
        "collected_test_node_hash_mode": COLLECTED_TEST_NODE_HASH_MODE,
    }
    if set(property_values) != set(expected_properties):
        raise V2ArtifactError("pytest JUnit contains missing or unexpected properties")
    for name, expected_value in expected_properties.items():
        if property_values[name] != [expected_value]:
            raise V2ArtifactError(f"pytest JUnit {name} property does not match")

    timestamps = sorted(
        {suite.attrib["timestamp"] for suite in suites if suite.attrib.get("timestamp")}
    )
    if (
        len(timestamps) != len({suite.attrib.get("timestamp") for suite in suites})
        or not timestamps
    ):
        raise V2ArtifactError("pytest JUnit evidence is missing an execution timestamp")
    for timestamp in timestamps:
        _validate_execution_timestamp(timestamp)
    receipt_started = _parse_execution_timestamp(
        execution_receipt["started_at"], "receipt started_at"
    )
    receipt_finished = _parse_execution_timestamp(
        execution_receipt["finished_at"], "receipt finished_at"
    )
    if any(
        not receipt_started
        <= _parse_execution_timestamp(timestamp, "JUnit execution timestamp")
        <= receipt_finished
        for timestamp in timestamps
    ):
        raise V2ArtifactError("pytest JUnit timestamp falls outside the execution receipt")

    testcase_identities = testcase_summary["identities"]
    testcase_identity_sha256 = _sha256_text(
        json.dumps(
            testcase_identities,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    testcase_classnames = sorted({identity["classname"] for identity in testcase_identities})
    return {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "preflight_version": PREFLIGHT_VERSION,
        "status": "PASS",
        "command": execution_receipt["display_command"],
        "evidence_runner_command": "python scripts/rag/build_v2_artifacts.py evidence",
        "evidence_path": TEST_EVIDENCE_PATH.as_posix(),
        "evidence_sha256": _sha256_file(path),
        "validation_input_inventory_sha256": validation_input_inventory_sha256,
        "junit_validation_input_inventory_sha256": validation_input_inventory_sha256,
        "preflight_inventory_path": preflight_inventory_path,
        "preflight_inventory_file_sha256": preflight_inventory_file_sha256,
        "prior_artifact_lock_sha256": prior_artifact_lock_sha256,
        "prior_artifact_lock_path": prior_artifact_lock_path,
        "prior_artifact_lock_file_sha256": prior_artifact_lock_file_sha256,
        "execution_receipt_path": TEST_EXECUTION_RECEIPT_PATH.as_posix(),
        "execution_receipt_sha256": _sha256_file(execution_receipt_path),
        "pytest_exit_code": execution_receipt["exit_code"],
        "pytest_started_at": execution_receipt["started_at"],
        "pytest_finished_at": execution_receipt["finished_at"],
        "testcase_identity_hash_mode": "sha256_canonical_json_v1",
        "testcase_identity_sha256": testcase_identity_sha256,
        "testcase_identity_count": len(testcase_identities),
        "testcase_files": collected_tests["files"],
        "testcase_classnames": testcase_classnames,
        "collection_command": ("python -m pytest services/rag-ingestion/tests --collect-only -q"),
        "collected_test_node_hash_mode": COLLECTED_TEST_NODE_HASH_MODE,
        "collected_test_node_ids_sha256": collected_tests["sha256"],
        "collected_test_node_count": collected_tests["count"],
        "execution_timestamp": timestamps[0],
        "execution_timestamps": timestamps,
        "execution_time_seconds": execution_time_seconds,
        **totals,
        "regression_result": "PASS",
        "production_approved": False,
    }


def _validated_execution_receipt(
    path: Path,
    *,
    junit_path: Path,
    repository_root: Path,
    validation_input_inventory_sha256: str,
    preflight_inventory_path: str,
    preflight_inventory_file_sha256: str,
    prior_artifact_lock_sha256: str,
    prior_artifact_lock_path: str,
    prior_artifact_lock_file_sha256: str,
) -> dict[str, Any]:
    if not path.is_file():
        raise V2ArtifactError("pytest execution receipt is required before a formal build")
    _canonical_lf_bytes(path)
    receipt = _read_json(path)
    if not isinstance(receipt, dict):
        raise V2ArtifactError("pytest execution receipt must be a JSON object")
    expected_values = {
        "schema_version": "1.0.0",
        "artifact_version": ARTIFACT_VERSION,
        "preflight_version": PREFLIGHT_VERSION,
        "evidence_version": EVIDENCE_VERSION,
        "status": "PASS",
        "display_command": (
            "python -m pytest services/rag-ingestion/tests --junitxml="
            f"{TEST_EVIDENCE_PATH.as_posix()}"
        ),
        "exit_code": 0,
        "validation_input_inventory_sha256": validation_input_inventory_sha256,
        "preflight_inventory_path": preflight_inventory_path,
        "preflight_inventory_file_sha256": preflight_inventory_file_sha256,
        "prior_artifact_lock_sha256": prior_artifact_lock_sha256,
        "prior_artifact_lock_path": prior_artifact_lock_path,
        "prior_artifact_lock_file_sha256": prior_artifact_lock_file_sha256,
        "junit_path": TEST_EVIDENCE_PATH.as_posix(),
        "junit_sha256": _sha256_file(junit_path),
        "failure_reasons": [],
        "production_approved": False,
    }
    for field, expected in expected_values.items():
        if receipt.get(field) != expected:
            raise V2ArtifactError(f"pytest execution receipt {field} does not match")
    _validate_executed_pytest_argv(receipt.get("executed_argv"), repository_root)
    expected_fields = set(expected_values) | {
        "executed_argv",
        "started_at",
        "finished_at",
    }
    if set(receipt) != expected_fields:
        raise V2ArtifactError("pytest execution receipt contains missing or unexpected fields")
    if type(receipt.get("exit_code")) is not int:
        raise V2ArtifactError("pytest execution receipt exit_code must be an integer")
    started = _parse_execution_timestamp(receipt.get("started_at"), "started_at")
    finished = _parse_execution_timestamp(receipt.get("finished_at"), "finished_at")
    if finished < started:
        raise V2ArtifactError("pytest execution receipt timestamps are out of order")
    return receipt


def _validate_executed_pytest_argv(value: Any, repository_root: Path) -> None:
    if (
        not isinstance(value, list)
        or len(value) != 5
        or any(not isinstance(argument, str) or not argument for argument in value)
    ):
        raise V2ArtifactError("pytest execution receipt executed_argv is invalid")
    interpreter = Path(value[0])
    if not interpreter.is_absolute() or not interpreter.name.lower().startswith("python"):
        raise V2ArtifactError("pytest execution receipt interpreter path is invalid")
    if value[1:4] != ["-m", "pytest", "services/rag-ingestion/tests"]:
        raise V2ArtifactError("pytest execution receipt argv does not run the full test suite")
    junit_prefix = "--junitxml="
    if not value[4].startswith(junit_prefix):
        raise V2ArtifactError("pytest execution receipt argv is missing JUnit output")
    executed_junit = Path(value[4][len(junit_prefix) :])
    if not executed_junit.is_absolute():
        raise V2ArtifactError("pytest execution receipt JUnit path is not absolute")
    resolved_junit = executed_junit.resolve()
    pending_root = (repository_root / "data/rag-v2/.pending").resolve()
    if (
        pending_root not in resolved_junit.parents
        or resolved_junit.name != TEST_EVIDENCE_PATH.name
        or resolved_junit.parent.name != EVIDENCE_VERSION
        or not resolved_junit.parent.parent.name.startswith(f"evidence-{EVIDENCE_VERSION}-")
    ):
        raise V2ArtifactError("pytest execution receipt JUnit path is outside its pending run")


def _clean_pytest_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"):
        environment.pop(name, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _testcase_identities_from_node_ids(
    node_ids: Sequence[str],
) -> list[dict[str, str]]:
    identities: list[dict[str, str]] = []
    for node_id in node_ids:
        parts = node_id.split("::")
        if len(parts) < 2 or not parts[0].endswith(".py") or not parts[-1]:
            raise V2ArtifactError("independent pytest collection returned an invalid node ID")
        module = parts[0][:-3].replace("/", ".")
        classname = ".".join((module, *parts[1:-1]))
        identities.append({"classname": classname, "name": parts[-1]})
    identities.sort(key=lambda item: (item["classname"], item["name"]))
    tokens = [_json_token(identity) for identity in identities]
    if len(tokens) != len(set(tokens)):
        raise V2ArtifactError("collected pytest node IDs map to duplicate testcase identities")
    return identities


def _normalize_collected_node_id(node_id: str) -> str:
    path, separator, test_name = node_id.partition("::")
    if not separator:
        raise V2ArtifactError("independent pytest collection returned an invalid node ID")
    normalized_path = path.replace("\\", "/")
    return f"{normalized_path}{separator}{test_name}"


def _collect_test_node_ids(repository_root: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "services/rag-ingestion/tests",
        "--collect-only",
        "-q",
    ]
    environment = _clean_pytest_environment()
    try:
        completed = subprocess.run(
            command,
            cwd=repository_root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise V2ArtifactError("independent pytest collection failed") from exc
    if completed.returncode != 0:
        raise V2ArtifactError(
            f"independent pytest collection failed with exit code {completed.returncode}"
        )
    node_ids = sorted(
        {
            _normalize_collected_node_id(line.strip())
            for line in completed.stdout.splitlines()
            if line.strip().startswith("tests/") and "::" in line.strip()
        }
    )
    if not node_ids:
        raise V2ArtifactError("independent pytest collection returned no test node IDs")
    payload = json.dumps(node_ids, ensure_ascii=False, separators=(",", ":"))
    return {
        "count": len(node_ids),
        "sha256": _sha256_text(payload),
        "files": sorted({node_id.split("::", maxsplit=1)[0] for node_id in node_ids}),
        "node_ids": node_ids,
        "testcase_identities": _testcase_identities_from_node_ids(node_ids),
    }


def _run_standalone_candidate_validator(
    repository_root: Path,
    candidate: Path,
    schema: Path,
) -> None:
    command = [
        sys.executable,
        str(repository_root / "scripts/rag/validate_v2_artifacts.py"),
        "--candidate",
        str(candidate),
        "--schema",
        str(schema),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=repository_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
        raise V2ArtifactError("standalone candidate validator could not complete") from exc
    if completed.returncode != 0:
        reason = _standalone_validator_failure_reason(completed.stderr)
        raise V2ArtifactError(f"standalone candidate validation failed: {reason}")
    try:
        summary = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise V2ArtifactError("standalone candidate validator returned invalid JSON") from exc
    if not isinstance(summary, dict) or summary.get("status") != "PASS":
        raise V2ArtifactError("standalone candidate validator did not report PASS")


def _standalone_validator_failure_reason(stderr: str) -> str:
    for line in reversed(stderr.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            reason = payload.get("failure_reason")
            if isinstance(reason, str) and reason and "\r" not in reason and "\n" not in reason:
                return reason[:500]
    return "validator exited non-zero"


def _validate_execution_timestamp(value: str) -> None:
    _parse_execution_timestamp(value, "execution timestamp")


def _parse_execution_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise V2ArtifactError(f"pytest {label} is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise V2ArtifactError(f"pytest {label} is not ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise V2ArtifactError(f"pytest {label} must include a timezone")
    return parsed


def _validate_records(
    records_by_source: Mapping[str, Sequence[dict[str, Any]]],
    prior_by_id: Mapping[str, ValidatedChunk],
) -> None:
    records = [record for values in records_by_source.values() for record in values]
    if len(records) != 726 or len(records_by_source) != 17:
        raise V2ArtifactError("selected dataset is not the frozen 17-source/726-chunk set")
    successor_ids = [record["identity"]["chunk_id"] for record in records]
    if len(successor_ids) != len(set(successor_ids)):
        raise V2ArtifactError("successor chunk IDs are not unique")
    for source_id, source_records in records_by_source.items():
        if any(record["identity"]["source_id"] != source_id for record in source_records):
            raise V2ArtifactError(f"record grouped under the wrong source: {source_id}")
        indexes = sorted(record["identity"]["chunk_index"] for record in source_records)
        if indexes != list(range(1, len(source_records) + 1)):
            raise V2ArtifactError(f"chunk indexes are not continuous for {source_id}")
    for record in records:
        identity = record["identity"]
        content = record["content"]
        citation = record["citation"]
        provenance = record["provenance"]
        prior = prior_by_id[identity["prior_chunk_id"]]
        if record["schema_version"] != SCHEMA_VERSION:
            raise V2ArtifactError(f"schema version mismatch for {identity['chunk_id']}")
        if record["artifact_version"] != ARTIFACT_VERSION:
            raise V2ArtifactError(f"artifact version mismatch for {identity['chunk_id']}")
        if (
            identity["source_id"] != prior.data["source_id"]
            or identity["chunk_index"] != prior.data["chunk_index"]
        ):
            raise V2ArtifactError(
                f"successor identity mapping mismatch for {identity['prior_chunk_id']}"
            )
        expected_chunk_id = (
            f"{identity['source_id']}_rag_v2_{ARTIFACT_VERSION}_" f"{identity['chunk_index']:04d}"
        )
        if identity["chunk_id"] != expected_chunk_id:
            raise V2ArtifactError(
                f"deterministic chunk ID mismatch for {identity['prior_chunk_id']}"
            )
        expected_chunk_file_id = f"{identity['source_id']}_rag_v2_{ARTIFACT_VERSION}"
        if identity["chunk_file_id"] != expected_chunk_file_id:
            raise V2ArtifactError(
                f"deterministic chunk file ID mismatch for {identity['chunk_id']}"
            )
        if content["text"].encode("utf-8") != prior.text.encode("utf-8"):
            raise V2ArtifactError(f"text bytes changed for {identity['prior_chunk_id']}")
        if content["embedding_text"].encode("utf-8") != prior.embedding_text.encode("utf-8"):
            raise V2ArtifactError(f"embedding_text bytes changed for {identity['prior_chunk_id']}")
        if content["char_count"] != len(content["text"]):
            raise V2ArtifactError(f"char_count mismatch for {identity['chunk_id']}")
        if content["embedding_char_count"] != len(content["embedding_text"]):
            raise V2ArtifactError(f"embedding_char_count mismatch for {identity['chunk_id']}")
        if content["text_sha256"] != _sha256_text(content["text"]):
            raise V2ArtifactError(f"text hash mismatch for {identity['chunk_id']}")
        if content["embedding_text_sha256"] != _sha256_text(content["embedding_text"]):
            raise V2ArtifactError(f"embedding hash mismatch for {identity['chunk_id']}")
        if provenance["is_official_source"]:
            if (
                citation["direct_official_source_url"] != citation["direct_source_url"]
                or citation["official_source_page_url"] != citation["source_page_url"]
            ):
                raise V2ArtifactError(
                    f"official source URL mapping mismatch for {identity['chunk_id']}"
                )
        elif (
            citation["direct_official_source_url"] is not None
            or citation["official_source_page_url"] is not None
        ):
            raise V2ArtifactError(
                f"non-official source uses an official-only URL for {identity['chunk_id']}"
            )
        policy = record["retrieval_policy"]
        if policy["retrieval_eligible"] is not (not policy["retrieval_block_reasons"]):
            raise V2ArtifactError(f"eligibility mismatch for {identity['chunk_id']}")
        if record["governance"]["review_status"] != "needs_review":
            raise V2ArtifactError("automatic review promotion is forbidden")
        if record["governance"]["production_approved"] is not False:
            raise V2ArtifactError("automatic production approval is forbidden")


def _validation_inventory_entries(root: Path) -> list[dict[str, Any]]:
    paths = set(_VALIDATION_FIXED_PATHS)
    paths.update(path.relative_to(root) for path in (root / CHUNKS_DIRECTORY).glob("*.jsonl"))
    paths.update(path.relative_to(root) for path in (root / "config/rag").glob("*"))
    paths.update(path.relative_to(root) for path in (root / "contracts/schemas/rag").glob("*.json"))
    paths.update(
        path.relative_to(root) for path in (root / "services/rag-ingestion/src").rglob("*.py")
    )
    paths.update(
        path.relative_to(root) for path in (root / "services/rag-ingestion/tests").rglob("*.py")
    )
    return _file_entries(root, paths)


def _prior_lock_entries(root: Path) -> list[dict[str, Any]]:
    paths = set(_PRIOR_FORMAL_PATHS)
    paths.update(path.relative_to(root) for path in (root / CHUNKS_DIRECTORY).glob("*.jsonl"))
    for family, active_version in (
        ("candidates", ARTIFACT_VERSION),
        ("preflight", PREFLIGHT_VERSION),
        ("evidence", EVIDENCE_VERSION),
    ):
        family_root = root / "data/rag-v2" / family
        if not family_root.is_dir():
            continue
        for version_root in sorted(family_root.iterdir(), key=lambda path: path.name):
            if (
                not version_root.is_dir()
                or not _is_version_directory(version_root.name)
                or version_root.name == active_version
            ):
                continue
            if family == "candidates":
                _assert_historical_candidate_checksums(version_root)
            paths.update(
                path.relative_to(root) for path in version_root.rglob("*") if path.is_file()
            )
    return _file_entries(root, paths)


def _is_version_directory(name: str) -> bool:
    return name.startswith("v") and name[1:].isdigit()


def _assert_historical_candidate_checksums(candidate: Path) -> None:
    checksum_path = candidate / "SHA256SUMS.txt"
    if not checksum_path.is_file():
        raise V2ArtifactError(f"historical candidate is missing SHA256SUMS.txt: {candidate.name}")
    lines = _canonical_lf_bytes(checksum_path).decode("utf-8").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    declared: dict[str, str] = {}
    for line_number, line in enumerate(lines, start=1):
        parts = line.split("  ", maxsplit=1)
        if (
            len(parts) != 2
            or len(parts[0]) != 64
            or any(character not in "0123456789abcdef" for character in parts[0])
        ):
            raise V2ArtifactError(
                f"invalid historical candidate checksum line: {candidate.name}:{line_number}"
            )
        relative_path = parts[1]
        pure_path = PurePosixPath(relative_path)
        if (
            pure_path.is_absolute()
            or ".." in pure_path.parts
            or pure_path.as_posix() != relative_path
            or relative_path in declared
        ):
            raise V2ArtifactError(
                f"unsafe or duplicate historical checksum path: {candidate.name}:{line_number}"
            )
        declared[relative_path] = parts[0]
    actual_paths = {
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if set(declared) != actual_paths:
        raise V2ArtifactError(f"historical candidate checksum inventory mismatch: {candidate.name}")
    candidate_root = candidate.resolve()
    for relative_path, expected_sha256 in declared.items():
        path = (candidate / Path(*PurePosixPath(relative_path).parts)).resolve()
        if candidate_root not in path.parents or not path.is_file():
            raise V2ArtifactError(
                f"historical candidate checksum path escapes candidate: {candidate.name}"
            )
        if _sha256_file(path) != expected_sha256:
            raise V2ArtifactError(
                f"historical candidate checksum mismatch: {candidate.name}/{relative_path}"
            )


def _file_entries(root: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    entries = []
    for relative in sorted(paths, key=lambda path: path.as_posix()):
        path = root / relative
        if not path.is_file():
            raise V2ArtifactError(f"inventory path is missing: {relative.as_posix()}")
        canonical_bytes = _canonical_lf_bytes(path)
        entries.append(
            {
                "path": relative.as_posix(),
                "size_bytes": len(canonical_bytes),
                "sha256": hashlib.sha256(canonical_bytes).hexdigest(),
                "hash_mode": CANONICAL_TEXT_HASH_MODE,
            }
        )
    return entries


def _inventory_document(kind: str, entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_version": PREFLIGHT_VERSION,
        "kind": kind,
        "hash_mode": CANONICAL_TEXT_HASH_MODE,
        "entry_count": len(entries),
        "inventory_sha256": _inventory_sha256(entries),
        "entries": list(entries),
    }
    if kind == "prior_artifact_immutable_lock":
        document["scope"] = (
            "prior V1 formal inputs and every non-active RagV2 candidate, preflight, "
            "and evidence file"
        )
        document["active_exclusions"] = [
            {
                "path": f"data/rag-v2/candidates/{ARTIFACT_VERSION}",
                "reason": "active successor candidate; excluded to avoid self-reference",
            },
            {
                "path": f"data/rag-v2/preflight/{PREFLIGHT_VERSION}",
                "reason": "active preflight; excluded to avoid self-reference",
            },
            {
                "path": f"data/rag-v2/evidence/{EVIDENCE_VERSION}",
                "reason": "active test evidence; bound separately after preflight",
            },
        ]
    return document


def _assert_inventory_matches(
    frozen: Mapping[str, Any],
    current_entries: Sequence[dict[str, Any]],
    label: str,
    *,
    expected_kind: str,
) -> None:
    expected = _inventory_document(expected_kind, current_entries)
    if dict(frozen) != expected:
        raise V2ArtifactError(f"{label} inventory changed after preflight")


def _assert_preflight_unchanged(
    repository_root: Path,
    *,
    inventory_path: Path,
    inventory: Mapping[str, Any],
    inventory_file_sha256: str,
    prior_lock_path: Path,
    prior_lock: Mapping[str, Any],
    prior_lock_file_sha256: str,
) -> None:
    _assert_file_sha256(
        inventory_path,
        inventory_file_sha256,
        "preflight validation inventory",
    )
    _assert_file_sha256(
        prior_lock_path,
        prior_lock_file_sha256,
        "preflight prior-artifact lock",
    )
    _assert_inventory_matches(
        inventory,
        _validation_inventory_entries(repository_root),
        "validation input",
        expected_kind="validation_input_inventory",
    )
    _assert_inventory_matches(
        prior_lock,
        _prior_lock_entries(repository_root),
        "prior artifact",
        expected_kind="prior_artifact_immutable_lock",
    )


def _inventory_sha256(entries: Sequence[dict[str, Any]]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(payload)


def _canonical_lf_bytes(path: Path) -> bytes:
    try:
        raw = path.read_bytes()
        raw.decode("utf-8")
    except OSError as exc:
        raise V2ArtifactError(f"cannot read inventory input: {path.name}") from exc
    except UnicodeDecodeError as exc:
        raise V2ArtifactError(f"inventory input is not valid UTF-8: {path.name}") from exc
    if b"\xef\xbb\xbf" in raw:
        raise V2ArtifactError(f"inventory input contains a UTF-8 BOM: {path.name}")
    if b"\r" in raw:
        raise V2ArtifactError(f"inventory input is not LF-only: {path.name}")
    return raw


def _assert_file_sha256(path: Path, expected: str, label: str) -> None:
    if _sha256_file(path) != expected:
        raise V2ArtifactError(f"{label} changed during candidate build")


def _assert_candidate_text_bytes(root: Path) -> None:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file():
            continue
        label = path.relative_to(root).as_posix()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise V2ArtifactError(f"cannot read candidate text file: {label}") from exc
        if b"\xef\xbb\xbf" in raw:
            raise V2ArtifactError(f"candidate text file contains a UTF-8 BOM: {label}")
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise V2ArtifactError(f"candidate text file is not valid UTF-8: {label}") from exc
        if b"\r" in raw:
            raise V2ArtifactError(f"candidate text file is not LF-only: {label}")


def _source_titles(path: Path) -> dict[str, str]:
    document = _read_json(path)
    titles = {}
    for item in document.get("candidates", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            title = item.get("title")
            if isinstance(title, str) and title.strip():
                titles[item["id"]] = title
    return titles


def _string_value(data: Mapping[str, Any], name: str, warnings: list[str]) -> str | None:
    values = _same_field_values(data, name)
    if len({_json_token(value) for _, value in values}) > 1:
        warnings.append(f"{name}_conflict")
    if not values:
        return None
    value = values[0][1]
    if not isinstance(value, str) or not value.strip():
        warnings.append(f"{name}_invalid_string")
        return None
    return value


def _bool_value(data: Mapping[str, Any], name: str, warnings: list[str]) -> bool | None:
    values = _same_field_values(data, name)
    if len({_json_token(value) for _, value in values}) > 1:
        warnings.append(f"{name}_conflict")
    if not values:
        return None
    value = values[0][1]
    if not isinstance(value, bool):
        warnings.append(f"{name}_invalid_boolean")
        return None
    return value


def _same_field_values(data: Mapping[str, Any], name: str) -> list[tuple[str, Any]]:
    values = []
    value = data.get(name)
    if value is not None:
        values.append((name, value))
    metadata = data.get("metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get(name)
        if value is not None:
            values.append((f"metadata.{name}", value))
    return values


def _first_string_alias(
    data: Mapping[str, Any], names: Sequence[str], warnings: list[str]
) -> str | None:
    for name in names:
        value = _string_value(data, name, warnings)
        if value is not None:
            return value
    return None


def _url_value(data: Mapping[str, Any], name: str, warnings: list[str]) -> str | None:
    value = _string_value(data, name, warnings)
    if value is None:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        warnings.append(f"{name}_invalid_url")
        return None
    return value


def _positive_int_value(
    data: Mapping[str, Any],
    names: Sequence[str],
    canonical_name: str,
    warnings: list[str],
) -> int | None:
    for name in names:
        values = _same_field_values(data, name)
        if not values:
            continue
        value = values[0][1]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            warnings.append(f"{canonical_name}_invalid_integer")
            return None
        return value
    return None


def _validate_page_pair(start: int | None, end: int | None, name: str, warnings: list[str]) -> None:
    if (start is None) != (end is None):
        warnings.append(f"{name}_half_populated")
    elif start is not None and end is not None and end < start:
        warnings.append(f"{name}_invalid_range")


def _normalize_language_locale(
    data: Mapping[str, Any], warnings: list[str]
) -> tuple[str | None, str | None]:
    raw_language = _string_value(data, "language", warnings)
    raw_locale = _string_value(data, "locale", warnings)
    if raw_language in {"zh-Hant", "zh-TW"}:
        language = "zh-Hant"
        locale = raw_locale or "zh-TW"
    elif raw_language == "en":
        language = "en"
        locale = raw_locale
    else:
        language = None
        locale = raw_locale
        warnings.append("language_missing_or_unsupported")
    if locale is not None and locale not in _CANONICAL_LOCALES:
        warnings.append("locale_not_in_v2_enum")
        locale = None
    if language is not None and language not in _CANONICAL_LANGUAGES:
        warnings.append("language_not_in_v2_enum")
        language = None
    return language, locale


def _unique_values(values: Iterable[Any]) -> list[Any]:
    tokens: dict[str, Any] = {}
    for value in values:
        if value is None or value == "":
            continue
        tokens[_json_token(value)] = value
    return [tokens[token] for token in sorted(tokens)]


def _json_token(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _candidate_readme() -> str:
    return (
        f"# RagChunkV2 {ARTIFACT_VERSION} candidate\n\n"
        "This directory is a local staging candidate generated from the immutable V1 "
        "bundle.\n\n"
        "- Review status: `needs_review`\n"
        "- Human source review: `not_completed`\n"
        "- Embedding status: `not_started`\n"
        "- Production approved: `false`\n"
        "- Storage target: `local_pending_upload`\n\n"
        "The 14 official Taiwanese sources follow the public-knowledge processing gates. "
        "The three sources remain explicitly non-official public research/scale sources and "
        "are never promoted to official authority. Their existing distribution scopes are "
        "preserved for human review. Existing V1 files, text, and embedding text are not "
        "modified.\n"
    )


def _write_checksums(root: Path) -> None:
    entries = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            entries.append(f"{_sha256_file(path)}  {path.relative_to(root).as_posix()}")
    _write_text(root / "SHA256SUMS.txt", "\n".join(entries) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _write_canonical_json(path: Path, payload: Any) -> None:
    _write_text(path, _canonical_json_bytes(payload).decode("utf-8"))


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_json_atomic_no_overwrite(path: Path, payload: Any) -> None:
    if path.exists():
        raise V2ArtifactError(f"evidence file already exists: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            raise V2ArtifactError(f"evidence file already exists: {path.name}")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _cleanup_owned_pending_directory(
    path: Path,
    pending_root: Path,
    *,
    expected_prefix: str,
) -> None:
    resolved_path = path.resolve()
    resolved_pending_root = pending_root.resolve()
    if (
        resolved_path.parent != resolved_pending_root
        or not resolved_path.name.startswith(expected_prefix)
        or len(resolved_path.name) <= len(expected_prefix)
    ):
        raise V2ArtifactError("refuse to clean an unowned pending directory")
    shutil.rmtree(resolved_path, ignore_errors=True)


def _publish_pending_directory(staged: Path, destination: Path, *, label: str) -> None:
    if destination.exists():
        raise V2ArtifactError(f"{label} appeared before atomic publish")
    try:
        staged.rename(destination)
    except OSError as exc:
        raise V2ArtifactError(f"{label} could not be atomically published") from exc


def _write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    lines = [
        json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for record in records
    ]
    _write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except _DuplicateJsonKey as exc:
        raise V2ArtifactError(f"duplicate JSON key in {path.name}: {exc.key}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise V2ArtifactError(f"cannot read JSON input {path.name}: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise V2ArtifactError(f"JSON input must be an object: {path.name}")
    return value


def _read_canonical_json(path: Path) -> dict[str, Any]:
    raw = _canonical_lf_bytes(path)
    document = _read_json(path)
    try:
        canonical = _canonical_json_bytes(document)
    except (TypeError, ValueError) as exc:
        raise V2ArtifactError(f"preflight JSON is not canonical: {path.name}") from exc
    if raw != canonical:
        raise V2ArtifactError(f"preflight JSON serialization is not canonical: {path.name}")
    return document


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

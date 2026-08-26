"""Build and validate an immutable, pending-only RagChunkV2 human-review package."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

PACKAGE_VERSION = "v001"
CANDIDATE_ARTIFACT_VERSION = "v002"
SOURCE_ASSIGNMENT_SCHEMA_VERSION = "1.0.0"
CHUNK_ASSIGNMENT_SCHEMA_VERSION = "1.0.0"
EXPECTED_SOURCE_COUNT = 17
EXPECTED_CHUNK_COUNT = 726
EXPECTED_FLAGGED_COUNT = 648
EXPECTED_OFFICIAL_SOURCE_COUNT = 14
EXPECTED_OFFICIAL_CHUNK_COUNT = 651

CANDIDATE_PATH = Path("data/rag-v2/candidates/v002")
SOURCE_ASSIGNMENT_SCHEMA_PATH = Path(
    "contracts/schemas/rag/human-review-source-assignment-v1.schema.json"
)
CHUNK_ASSIGNMENT_SCHEMA_PATH = Path(
    "contracts/schemas/rag/human-review-chunk-assignment-v1.schema.json"
)
SOURCE_MANIFEST_RELATIVE_PATH = Path("manifests/source-manifest-v002.json")
WORKSHEET_RELATIVE_PATH = Path("review/human-review-worksheet-v002.jsonl")
VALIDATION_INPUT_INVENTORY_FILENAME = "validation-input-inventory.json"
PRIOR_ARTIFACT_LOCK_FILENAME = "prior-artifact-lock.json"
SOURCE_ASSIGNMENTS_FILENAME = "source-assignments.jsonl"
SOURCE_FILE_INDEX_FILENAME = "source-file-index.json"
OWNER_ACCEPTANCE_FILENAME = "owner-acceptance.json"
MANIFEST_FILENAME = "manifest.json"
VALIDATION_REPORT_FILENAME = "validation-report.json"
CHECKSUM_FILENAME = "SHA256SUMS.txt"
HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"

_VALIDATION_FIXED_PATHS = (
    SOURCE_ASSIGNMENT_SCHEMA_PATH,
    CHUNK_ASSIGNMENT_SCHEMA_PATH,
    Path("services/rag-ingestion/src/rag_ingestion/human_review_package.py"),
    Path("services/rag-ingestion/tests/integration/test_human_review_package.py"),
    Path("scripts/rag/build_human_review_package.py"),
    Path("scripts/rag/validate_human_review_package.py"),
    Path("data/rag-v2/README.md"),
    Path("services/rag-ingestion/README.md"),
)
_HIGH_PRIORITY_BLOCKERS = frozenset(
    {
        "requires_official_assessment_missing",
        "requires_professional_assessment_missing",
        "risk_level_not_allowed",
    }
)


class HumanReviewPackageError(ValueError):
    """Raised when the assignment package cannot be built or validated safely."""


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HumanReviewPackageSummary:
    output_path: Path
    source_assignment_count: int
    chunk_assignment_count: int
    flagged_assignment_count: int
    baseline_assignment_count: int
    official_source_count: int
    official_chunk_count: int
    research_source_count: int
    research_chunk_count: int
    priority_counts: dict[str, int]
    validation_input_inventory_sha256: str
    prior_artifact_lock_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "READY_FOR_HUMAN_REVIEW",
            "package_version": PACKAGE_VERSION,
            "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
            "output_path": self.output_path.as_posix(),
            "source_assignment_count": self.source_assignment_count,
            "chunk_assignment_count": self.chunk_assignment_count,
            "flagged_assignment_count": self.flagged_assignment_count,
            "baseline_assignment_count": self.baseline_assignment_count,
            "official_source_count": self.official_source_count,
            "official_chunk_count": self.official_chunk_count,
            "research_source_count": self.research_source_count,
            "research_chunk_count": self.research_chunk_count,
            "priority_counts": self.priority_counts,
            "validation_input_inventory_sha256": (self.validation_input_inventory_sha256),
            "prior_artifact_lock_sha256": self.prior_artifact_lock_sha256,
            "review_completion_status": "NOT_COMPLETED",
            "project_owner_risk_acceptance": "NOT_SIGNED",
            "production_approved": False,
        }


def build_human_review_package(
    repository_root: Path,
    output_root: Path,
) -> HumanReviewPackageSummary:
    """Build the pending-only assignment package and refuse every overwrite."""

    root = repository_root.resolve()
    output_base = output_root.resolve()
    package = output_base / PACKAGE_VERSION
    if package.exists():
        raise HumanReviewPackageError("human-review package already exists; refuse to overwrite")

    candidate = root / CANDIDATE_PATH
    _validate_candidate_checksums(candidate)
    source_schema = _load_schema(root / SOURCE_ASSIGNMENT_SCHEMA_PATH)
    chunk_schema = _load_schema(root / CHUNK_ASSIGNMENT_SCHEMA_PATH)
    source_validator = Draft202012Validator(source_schema, format_checker=FormatChecker())
    chunk_validator = Draft202012Validator(chunk_schema, format_checker=FormatChecker())

    source_manifest = _read_json(candidate / SOURCE_MANIFEST_RELATIVE_PATH)
    worksheet_rows = _read_jsonl(candidate / WORKSHEET_RELATIVE_PATH)
    worksheet_by_chunk = _worksheet_by_chunk(worksheet_rows)
    records_by_source = _candidate_records(candidate)
    _validate_candidate_counts(source_manifest, records_by_source, worksheet_by_chunk)

    inventory_entries = _validation_input_entries(root)
    prior_lock_entries = _prior_lock_entries(root, output_base)
    validation_inventory = _inventory_document(
        "human_review_validation_input_inventory",
        inventory_entries,
    )
    prior_lock = _inventory_document(
        "human_review_prior_artifact_immutable_lock",
        prior_lock_entries,
    )

    output_base.mkdir(parents=True, exist_ok=True)
    pending_root = output_base / ".pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    temporary_prefix = f"human-review-{PACKAGE_VERSION}-"
    temporary_root = Path(tempfile.mkdtemp(prefix=temporary_prefix, dir=pending_root)).resolve()
    staged_package = temporary_root / PACKAGE_VERSION
    staged_package.mkdir()
    try:
        _write_json(
            staged_package / VALIDATION_INPUT_INVENTORY_FILENAME,
            validation_inventory,
        )
        _write_json(staged_package / PRIOR_ARTIFACT_LOCK_FILENAME, prior_lock)

        sources = sorted(source_manifest["sources"], key=lambda item: item["source_number"])
        source_assignments = [_source_assignment(source) for source in sources]
        for assignment in source_assignments:
            _validate_schema(source_validator, assignment, "source assignment")
        _write_jsonl(staged_package / SOURCE_ASSIGNMENTS_FILENAME, source_assignments)
        _write_json(
            staged_package / SOURCE_FILE_INDEX_FILENAME,
            _source_file_index(sources),
        )
        _write_json(staged_package / OWNER_ACCEPTANCE_FILENAME, _owner_acceptance())
        _write_text(staged_package / "README.md", _package_readme())

        source_by_id = {source["source_id"]: source for source in sources}
        chunk_assignments: list[dict[str, Any]] = []
        assignment_files: list[Path] = []
        for source in sources:
            source_id = source["source_id"]
            rows = []
            for line_number, record, relative_path in records_by_source[source_id]:
                assignment = _chunk_assignment(
                    source,
                    record,
                    relative_path=relative_path,
                    line_number=line_number,
                    worksheet=worksheet_by_chunk.get(record["identity"]["chunk_id"]),
                )
                _validate_schema(chunk_validator, assignment, "chunk assignment")
                rows.append(assignment)
                chunk_assignments.append(assignment)
            assignment_path = staged_package / "assignments" / f"{source_id}.jsonl"
            _write_jsonl(assignment_path, rows)
            assignment_files.append(assignment_path)

        counts = _assignment_counts(source_assignments, chunk_assignments)
        _validate_expected_counts(counts)
        manifest = _package_manifest(
            staged_package,
            source_by_id=source_by_id,
            assignment_files=assignment_files,
            counts=counts,
            validation_inventory_sha256=validation_inventory["inventory_sha256"],
            prior_lock_sha256=prior_lock["inventory_sha256"],
        )
        _write_json(staged_package / MANIFEST_FILENAME, manifest)
        _write_json(
            staged_package / VALIDATION_REPORT_FILENAME,
            _validation_report(counts),
        )
        _write_checksums(staged_package)

        summary = validate_human_review_package(
            root,
            staged_package,
            output_root=output_base,
        )
        _publish_directory(staged_package, package)
        return HumanReviewPackageSummary(
            output_path=package,
            source_assignment_count=summary["source_assignment_count"],
            chunk_assignment_count=summary["chunk_assignment_count"],
            flagged_assignment_count=summary["flagged_assignment_count"],
            baseline_assignment_count=summary["baseline_assignment_count"],
            official_source_count=summary["official_source_count"],
            official_chunk_count=summary["official_chunk_count"],
            research_source_count=summary["research_source_count"],
            research_chunk_count=summary["research_chunk_count"],
            priority_counts=summary["priority_counts"],
            validation_input_inventory_sha256=validation_inventory["inventory_sha256"],
            prior_artifact_lock_sha256=prior_lock["inventory_sha256"],
        )
    finally:
        _cleanup_pending_directory(
            temporary_root,
            pending_root,
            expected_prefix=temporary_prefix,
        )


def validate_human_review_package(
    repository_root: Path,
    package: Path,
    *,
    output_root: Path | None = None,
    _validate_build_snapshot: bool = False,
) -> dict[str, Any]:
    """Validate assignment coverage, immutable locks, schemas, and pending-only gates."""

    root = repository_root.resolve()
    package_root = package.resolve()
    if not package_root.is_dir() or package_root.name != PACKAGE_VERSION:
        raise HumanReviewPackageError("human-review package path/version is invalid")
    review_root = output_root.resolve() if output_root else package_root.parent

    _assert_text_tree(package_root)
    _validate_checksums(package_root)
    if _validate_build_snapshot:
        _validate_inventory_snapshot_document(
            package_root / VALIDATION_INPUT_INVENTORY_FILENAME,
            expected_kind="human_review_validation_input_inventory",
        )
    else:
        _validate_inventory_document(
            package_root / VALIDATION_INPUT_INVENTORY_FILENAME,
            expected_kind="human_review_validation_input_inventory",
            current_entries=_validation_input_entries(root),
        )
    _validate_inventory_document(
        package_root / PRIOR_ARTIFACT_LOCK_FILENAME,
        expected_kind="human_review_prior_artifact_immutable_lock",
        current_entries=_prior_lock_entries(root, review_root),
    )
    _validate_candidate_checksums(root / CANDIDATE_PATH)

    source_schema = _load_schema(root / SOURCE_ASSIGNMENT_SCHEMA_PATH)
    chunk_schema = _load_schema(root / CHUNK_ASSIGNMENT_SCHEMA_PATH)
    source_validator = Draft202012Validator(source_schema, format_checker=FormatChecker())
    chunk_validator = Draft202012Validator(chunk_schema, format_checker=FormatChecker())

    candidate = root / CANDIDATE_PATH
    source_manifest = _read_json(candidate / SOURCE_MANIFEST_RELATIVE_PATH)
    worksheet_by_chunk = _worksheet_by_chunk(_read_jsonl(candidate / WORKSHEET_RELATIVE_PATH))
    records_by_source = _candidate_records(candidate)
    _validate_candidate_counts(source_manifest, records_by_source, worksheet_by_chunk)
    sources = sorted(source_manifest["sources"], key=lambda item: item["source_number"])
    source_by_id = {source["source_id"]: source for source in sources}

    source_assignments = _read_jsonl(package_root / SOURCE_ASSIGNMENTS_FILENAME)
    expected_source_assignments = [_source_assignment(source) for source in sources]
    if source_assignments != expected_source_assignments:
        raise HumanReviewPackageError("source assignments differ from the candidate manifest")
    for assignment in source_assignments:
        _validate_schema(source_validator, assignment, "source assignment")

    chunk_assignments: list[dict[str, Any]] = []
    assignment_files: list[Path] = []
    expected_paths = _required_package_paths(sources)
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        raise HumanReviewPackageError("human-review package file inventory is incomplete")
    for source in sources:
        source_id = source["source_id"]
        path = package_root / "assignments" / f"{source_id}.jsonl"
        assignment_files.append(path)
        actual_rows = _read_jsonl(path)
        expected_rows = [
            _chunk_assignment(
                source,
                record,
                relative_path=relative_path,
                line_number=line_number,
                worksheet=worksheet_by_chunk.get(record["identity"]["chunk_id"]),
            )
            for line_number, record, relative_path in records_by_source[source_id]
        ]
        if actual_rows != expected_rows:
            raise HumanReviewPackageError(
                f"chunk assignments differ from candidate bytes: {source_id}"
            )
        for assignment in actual_rows:
            _validate_schema(chunk_validator, assignment, "chunk assignment")
        chunk_assignments.extend(actual_rows)

    counts = _assignment_counts(source_assignments, chunk_assignments)
    _validate_expected_counts(counts)
    inventory = _read_json(package_root / VALIDATION_INPUT_INVENTORY_FILENAME)
    prior_lock = _read_json(package_root / PRIOR_ARTIFACT_LOCK_FILENAME)
    expected_manifest = _package_manifest(
        package_root,
        source_by_id=source_by_id,
        assignment_files=assignment_files,
        counts=counts,
        validation_inventory_sha256=inventory["inventory_sha256"],
        prior_lock_sha256=prior_lock["inventory_sha256"],
    )
    if _read_json(package_root / MANIFEST_FILENAME) != expected_manifest:
        raise HumanReviewPackageError("human-review manifest does not match assignments")
    if _read_json(package_root / SOURCE_FILE_INDEX_FILENAME) != _source_file_index(sources):
        raise HumanReviewPackageError("source-file index differs from the candidate manifest")
    if _read_json(package_root / OWNER_ACCEPTANCE_FILENAME) != _owner_acceptance():
        raise HumanReviewPackageError("owner acceptance must remain unsigned")
    if (package_root / "README.md").read_text(encoding="utf-8") != _package_readme():
        raise HumanReviewPackageError("human-review README differs from the contract")
    if _read_json(package_root / VALIDATION_REPORT_FILENAME) != _validation_report(counts):
        raise HumanReviewPackageError("human-review validation report is inconsistent")

    return {
        "status": "PASS",
        "package_status": "READY_FOR_HUMAN_REVIEW",
        "package_version": PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        **counts,
        "review_completion_status": "NOT_COMPLETED",
        "project_owner_risk_acceptance": "NOT_SIGNED",
        "production_approved": False,
    }


def validate_human_review_package_build_snapshot(
    repository_root: Path,
    package: Path,
    *,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Validate historical build inputs without claiming current-input equality."""

    return validate_human_review_package(
        repository_root,
        package,
        output_root=output_root,
        _validate_build_snapshot=True,
    )


def _source_assignment(source: Mapping[str, Any]) -> dict[str, Any]:
    source_id = source["source_id"]
    return {
        "schema_version": SOURCE_ASSIGNMENT_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "assignment_id": f"human_review_{PACKAGE_VERSION}_source_{source_id}",
        "source_number": source["source_number"],
        "source_id": source_id,
        "title": source["title"],
        "authority_level": source["authority_level"],
        "source_type": source["source_type"],
        "is_official_source": source["is_official_source"],
        "review_track": (
            "official_source" if source["is_official_source"] else "research_evidence"
        ),
        "chunk_count": source["chunk_count"],
        "source_versions": source["source_versions"],
        "direct_source_urls": source["direct_source_urls"],
        "source_page_urls": source["source_page_urls"],
        "license_evidence_urls": source["license_evidence_urls"],
        "storage_urls": source["storage_urls"],
        "local_source_status": "not_available",
        "human_decision": {
            "decision_status": "pending",
            "source_comparison_status": "not_started",
            "reviewer_id": None,
            "reviewed_at": None,
            "evidence_references": [],
            "current_status_recommendation": None,
            "version_check_recommendation": None,
            "license_status_recommendation": None,
            "notes": None,
        },
        "production_approved": False,
    }


def _chunk_assignment(
    source: Mapping[str, Any],
    record: Mapping[str, Any],
    *,
    relative_path: str,
    line_number: int,
    worksheet: Mapping[str, Any] | None,
) -> dict[str, Any]:
    identity = record["identity"]
    citation = record["citation"]
    content = record["content"]
    governance = record["governance"]
    retrieval = record["retrieval_policy"]
    provenance = record["provenance"]
    blockers = list(retrieval["retrieval_block_reasons"])
    warnings = list(provenance["mapping_warnings"])
    if worksheet is not None and (
        worksheet["retrieval_block_reasons"] != blockers
        or worksheet["mapping_warnings"] != warnings
    ):
        raise HumanReviewPackageError(
            f"worksheet evidence differs from chunk: {identity['chunk_id']}"
        )
    source_id = identity["source_id"]
    return {
        "schema_version": CHUNK_ASSIGNMENT_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "assignment_id": f"human_review_{PACKAGE_VERSION}_chunk_{identity['chunk_id']}",
        "source_assignment_id": f"human_review_{PACKAGE_VERSION}_source_{source_id}",
        "batch_id": f"human_review_{PACKAGE_VERSION}_batch_{source['source_number']:02d}",
        "source_number": source["source_number"],
        "source_id": source_id,
        "successor_chunk_id": identity["chunk_id"],
        "prior_chunk_id": identity["prior_chunk_id"],
        "chunk_index": identity["chunk_index"],
        "candidate_chunk_path": relative_path,
        "candidate_line_number": line_number,
        "review_track": (
            "official_source" if provenance["is_official_source"] else "research_evidence"
        ),
        "review_scope": "flagged" if worksheet is not None else "baseline",
        "priority": _review_priority(record, blockers),
        "citation": {
            "title": citation["title"],
            "section": citation["section"],
            "source_locator": citation["source_locator"],
            "physical_page_start": citation["physical_page_start"],
            "physical_page_end": citation["physical_page_end"],
            "printed_page_start": citation["printed_page_start"],
            "printed_page_end": citation["printed_page_end"],
            "direct_source_url": citation["direct_source_url"],
            "source_page_url": citation["source_page_url"],
            "license_evidence_url": citation["license_evidence_url"],
            "storage_url": citation["storage_url"],
        },
        "content_evidence": {
            "text_sha256": content["text_sha256"],
            "embedding_text_sha256": content["embedding_text_sha256"],
            "char_count": content["char_count"],
        },
        "governance_snapshot": {
            "review_status": governance["review_status"],
            "current_status": governance["current_status"],
            "version_check_status": governance["version_check_status"],
            "license_status": governance["license_status"],
            "human_source_review": governance["human_source_review"],
        },
        "retrieval_snapshot": {
            "risk_level": retrieval["risk_level"],
            "requires_official_assessment": retrieval["requires_official_assessment"],
            "requires_professional_assessment": retrieval["requires_professional_assessment"],
            "requires_human_review": retrieval["requires_human_review"],
            "stop_normal_rag": retrieval["stop_normal_rag"],
            "retrieval_eligible": retrieval["retrieval_eligible"],
            "retrieval_block_reasons": blockers,
        },
        "mapping_warnings": warnings,
        "human_decision": {
            "decision_status": "pending",
            "source_fidelity_status": "not_reviewed",
            "exact_fact_status": "not_reviewed",
            "risk_status": "not_reviewed",
            "assessment_status": "not_reviewed",
            "reviewer_id": None,
            "reviewed_at": None,
            "evidence_references": [],
            "correction_notes": None,
            "recommended_review_status": "needs_review",
        },
        "production_approved": False,
    }


def _review_priority(record: Mapping[str, Any], blockers: Sequence[str]) -> str:
    retrieval = record["retrieval_policy"]
    provenance = record["provenance"]
    governance = record["governance"]
    if (
        retrieval["stop_normal_rag"] is True
        or retrieval["risk_level"] == "high_red_line"
        or provenance["source_type"] == "risk_rule"
    ):
        return "P0"
    if (
        retrieval["risk_level"] == "high"
        or governance["current_status"] != "current"
        or bool(_HIGH_PRIORITY_BLOCKERS.intersection(blockers))
    ):
        return "P1"
    if blockers or provenance["mapping_warnings"]:
        return "P2"
    return "P3"


def _assignment_counts(
    source_assignments: Sequence[Mapping[str, Any]],
    chunk_assignments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    priority_counts = Counter(row["priority"] for row in chunk_assignments)
    official_sources = sum(row["review_track"] == "official_source" for row in source_assignments)
    official_chunks = sum(row["review_track"] == "official_source" for row in chunk_assignments)
    flagged = sum(row["review_scope"] == "flagged" for row in chunk_assignments)
    return {
        "source_assignment_count": len(source_assignments),
        "chunk_assignment_count": len(chunk_assignments),
        "flagged_assignment_count": flagged,
        "baseline_assignment_count": len(chunk_assignments) - flagged,
        "official_source_count": official_sources,
        "official_chunk_count": official_chunks,
        "research_source_count": len(source_assignments) - official_sources,
        "research_chunk_count": len(chunk_assignments) - official_chunks,
        "priority_counts": {
            priority: priority_counts.get(priority, 0) for priority in ("P0", "P1", "P2", "P3")
        },
    }


def _validate_expected_counts(counts: Mapping[str, Any]) -> None:
    expected = {
        "source_assignment_count": EXPECTED_SOURCE_COUNT,
        "chunk_assignment_count": EXPECTED_CHUNK_COUNT,
        "flagged_assignment_count": EXPECTED_FLAGGED_COUNT,
        "baseline_assignment_count": EXPECTED_CHUNK_COUNT - EXPECTED_FLAGGED_COUNT,
        "official_source_count": EXPECTED_OFFICIAL_SOURCE_COUNT,
        "official_chunk_count": EXPECTED_OFFICIAL_CHUNK_COUNT,
        "research_source_count": EXPECTED_SOURCE_COUNT - EXPECTED_OFFICIAL_SOURCE_COUNT,
        "research_chunk_count": EXPECTED_CHUNK_COUNT - EXPECTED_OFFICIAL_CHUNK_COUNT,
    }
    for field, value in expected.items():
        if counts.get(field) != value:
            raise HumanReviewPackageError(f"unexpected human-review count: {field}")


def _package_manifest(
    package: Path,
    *,
    source_by_id: Mapping[str, Mapping[str, Any]],
    assignment_files: Sequence[Path],
    counts: Mapping[str, Any],
    validation_inventory_sha256: str,
    prior_lock_sha256: str,
) -> dict[str, Any]:
    batches = []
    for path in assignment_files:
        source_id = path.stem
        rows = _read_jsonl(path)
        source = source_by_id[source_id]
        batches.append(
            {
                "batch_id": f"human_review_{PACKAGE_VERSION}_batch_{source['source_number']:02d}",
                "source_number": source["source_number"],
                "source_id": source_id,
                "review_track": (
                    "official_source" if source["is_official_source"] else "research_evidence"
                ),
                "path": path.relative_to(package).as_posix(),
                "row_count": len(rows),
                "flagged_count": sum(row["review_scope"] == "flagged" for row in rows),
                "size_bytes": len(_raw_lf_bytes(path)),
                "sha256": _sha256_file(path),
            }
        )
    return {
        "schema_version": "1.0.0",
        "package_version": PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "READY_FOR_HUMAN_REVIEW",
        "review_completion_status": "NOT_COMPLETED",
        "project_owner_risk_acceptance": "NOT_SIGNED",
        **dict(counts),
        "validation_input_inventory_sha256": validation_inventory_sha256,
        "prior_artifact_lock_sha256": prior_lock_sha256,
        "source_assignments_path": SOURCE_ASSIGNMENTS_FILENAME,
        "source_file_index_path": SOURCE_FILE_INDEX_FILENAME,
        "owner_acceptance_path": OWNER_ACCEPTANCE_FILENAME,
        "batches": batches,
        "external_access_performed": False,
        "embedding_status": "NOT_STARTED",
        "opensearch_indexing_status": "NOT_STARTED",
        "production_status": "BLOCKED",
        "production_approved": False,
    }


def _source_file_index(sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "package_version": PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "source_count": len(sources),
        "local_source_file_count": 0,
        "external_access_performed": False,
        "sources": [
            {
                "source_number": source["source_number"],
                "source_id": source["source_id"],
                "is_official_source": source["is_official_source"],
                "direct_source_urls": source["direct_source_urls"],
                "source_page_urls": source["source_page_urls"],
                "license_evidence_urls": source["license_evidence_urls"],
                "storage_urls": source["storage_urls"],
                "local_source_status": "not_available",
                "local_source_files": [],
                "source_bytes_sha256": None,
            }
            for source in sources
        ],
        "production_approved": False,
    }


def _owner_acceptance() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "package_version": PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "NOT_SIGNED",
        "project_owner_id": None,
        "signed_at": None,
        "accepted_manifest_sha256": None,
        "human_source_review": "NOT_COMPLETED",
        "allowed_use": "INTERNAL_HUMAN_REVIEW_ONLY",
        "production_status": "BLOCKED",
        "production_approved": False,
    }


def _validation_report(counts: Mapping[str, Any]) -> dict[str, Any]:
    checks = [
        {
            "name": "source_assignment_count",
            "status": "PASS",
            "observed": counts["source_assignment_count"],
        },
        {
            "name": "chunk_assignment_count",
            "status": "PASS",
            "observed": counts["chunk_assignment_count"],
        },
        {
            "name": "flagged_assignment_count",
            "status": "PASS",
            "observed": counts["flagged_assignment_count"],
        },
        {
            "name": "baseline_assignment_count",
            "status": "PASS",
            "observed": counts["baseline_assignment_count"],
        },
        {
            "name": "pending_human_decisions",
            "status": "PASS",
            "observed": counts["chunk_assignment_count"],
        },
        {
            "name": "production_approved_false",
            "status": "PASS",
            "observed": counts["chunk_assignment_count"],
        },
        {"name": "external_access_not_performed", "status": "PASS", "observed": True},
    ]
    return {
        "schema_version": "1.0.0",
        "package_version": PACKAGE_VERSION,
        "candidate_artifact_version": CANDIDATE_ARTIFACT_VERSION,
        "status": "PASS",
        "pass_count": len(checks),
        "fail_count": 0,
        "checks": checks,
        "review_completion_status": "NOT_COMPLETED",
        "project_owner_risk_acceptance": "NOT_SIGNED",
        "production_approved": False,
    }


def _package_readme() -> str:
    return (
        "# RagChunkV2 human-review assignment v001\n\n"
        "This is an immutable, local-only assignment package for candidate v002.\n"
        "It covers all 726 chunks: 648 flagged rows and 78 baseline rows.\n\n"
        "- Every source and chunk decision remains pending.\n"
        "- No source file was fetched or verified while building this package.\n"
        "- The 14 official sources and three research sources use separate review tracks.\n"
        "- Do not edit this v001 package in place. Record human decisions in a new, "
        "versioned successor submission.\n"
        "- Only a named human reviewer may recommend `verified`.\n"
        "- Only the project owner may sign risk acceptance.\n"
        "- Embedding, indexing, and Production remain blocked.\n\n"
        "Review source-by-source using `source-assignments.jsonl`, "
        "`source-file-index.json`, and the 17 files under `assignments/`. "
        "Review P0 before P1, P2, and P3. Compare against immutable source bytes or "
        "official pages before recording any approval.\n"
    )


def _candidate_records(
    candidate: Path,
) -> dict[str, list[tuple[int, dict[str, Any], str]]]:
    records: dict[str, list[tuple[int, dict[str, Any], str]]] = defaultdict(list)
    for path in sorted((candidate / "chunks").glob("*.jsonl"), key=lambda item: item.name):
        relative_path = path.relative_to(candidate.parents[3]).as_posix()
        for line_number, record in enumerate(_read_jsonl(path), start=1):
            source_id = record["identity"]["source_id"]
            records[source_id].append((line_number, record, relative_path))
    return dict(records)


def _worksheet_by_chunk(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        chunk_id = row.get("successor_chunk_id")
        if not isinstance(chunk_id, str) or chunk_id in result:
            raise HumanReviewPackageError("worksheet chunk IDs are invalid or duplicated")
        result[chunk_id] = row
    return result


def _validate_candidate_counts(
    source_manifest: Mapping[str, Any],
    records_by_source: Mapping[str, Sequence[Any]],
    worksheet_by_chunk: Mapping[str, Any],
) -> None:
    if source_manifest.get("artifact_version") != CANDIDATE_ARTIFACT_VERSION:
        raise HumanReviewPackageError("candidate source manifest version mismatch")
    if source_manifest.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise HumanReviewPackageError("candidate source count mismatch")
    if source_manifest.get("chunk_count") != EXPECTED_CHUNK_COUNT:
        raise HumanReviewPackageError("candidate chunk count mismatch")
    if sum(len(rows) for rows in records_by_source.values()) != EXPECTED_CHUNK_COUNT:
        raise HumanReviewPackageError("candidate chunk files are incomplete")
    if len(records_by_source) != EXPECTED_SOURCE_COUNT:
        raise HumanReviewPackageError("candidate source files are incomplete")
    if len(worksheet_by_chunk) != EXPECTED_FLAGGED_COUNT:
        raise HumanReviewPackageError("candidate worksheet count mismatch")


def _validation_input_entries(root: Path) -> list[dict[str, Any]]:
    paths = set(_VALIDATION_FIXED_PATHS)
    paths.update(
        path.relative_to(root) for path in (root / CANDIDATE_PATH).rglob("*") if path.is_file()
    )
    return _file_entries(root, paths)


def _prior_lock_entries(root: Path, output_root: Path) -> list[dict[str, Any]]:
    paths = {
        path.relative_to(root) for path in (root / CANDIDATE_PATH).rglob("*") if path.is_file()
    }
    canonical_review_root = (root / "data/rag-v2/human-review").resolve()
    if output_root.resolve() == canonical_review_root and canonical_review_root.is_dir():
        for version_root in canonical_review_root.iterdir():
            if (
                version_root.is_dir()
                and version_root.name.startswith("v")
                and version_root.name[1:].isdigit()
                and version_root.name != PACKAGE_VERSION
            ):
                paths.update(
                    path.relative_to(root) for path in version_root.rglob("*") if path.is_file()
                )
    return _file_entries(root, paths)


def _inventory_document(kind: str, entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact_version": PACKAGE_VERSION,
        "kind": kind,
        "hash_mode": HASH_MODE,
        "entry_count": len(entries),
        "inventory_sha256": _inventory_sha256(entries),
        "entries": list(entries),
        "production_approved": False,
    }


def _validate_inventory_document(
    path: Path,
    *,
    expected_kind: str,
    current_entries: Sequence[dict[str, Any]],
) -> None:
    document = _read_json(path)
    expected = _inventory_document(expected_kind, current_entries)
    if document != expected:
        raise HumanReviewPackageError(f"{expected_kind} changed after packaging")
    expected_bytes = _json_bytes(expected)
    if path.read_bytes() != expected_bytes:
        raise HumanReviewPackageError(f"{expected_kind} is not deterministic JSON")


def _validate_inventory_snapshot_document(path: Path, *, expected_kind: str) -> None:
    document = _read_json(path)
    if document.get("kind") != expected_kind:
        raise HumanReviewPackageError(f"{expected_kind} kind mismatch")
    entries = document.get("entries")
    if not isinstance(entries, list) or document.get("entry_count") != len(entries):
        raise HumanReviewPackageError(f"{expected_kind} entry count mismatch")
    if document.get("inventory_sha256") != _inventory_sha256(entries):
        raise HumanReviewPackageError(f"{expected_kind} stored digest mismatch")
    if document.get("production_approved") is not False:
        raise HumanReviewPackageError(f"{expected_kind} approved Production")
    if path.read_bytes() != _json_bytes(document):
        raise HumanReviewPackageError(f"{expected_kind} is not deterministic JSON")


def _required_package_paths(sources: Sequence[Mapping[str, Any]]) -> set[str]:
    paths = {
        "README.md",
        VALIDATION_INPUT_INVENTORY_FILENAME,
        PRIOR_ARTIFACT_LOCK_FILENAME,
        SOURCE_ASSIGNMENTS_FILENAME,
        SOURCE_FILE_INDEX_FILENAME,
        OWNER_ACCEPTANCE_FILENAME,
        MANIFEST_FILENAME,
        VALIDATION_REPORT_FILENAME,
        CHECKSUM_FILENAME,
    }
    paths.update(f"assignments/{source['source_id']}.jsonl" for source in sources)
    return paths


def _validate_candidate_checksums(candidate: Path) -> None:
    checksum_path = candidate / CHECKSUM_FILENAME
    if not checksum_path.is_file():
        raise HumanReviewPackageError("candidate checksum file is missing")
    declared: dict[str, str] = {}
    for line in _raw_lf_bytes(checksum_path).decode("utf-8").splitlines():
        parts = line.split("  ", maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise HumanReviewPackageError("candidate checksum line is invalid")
        relative_path = parts[1]
        if relative_path in declared:
            raise HumanReviewPackageError("candidate checksum path is duplicated")
        declared[relative_path] = parts[0]
    actual = {
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if set(declared) != actual:
        raise HumanReviewPackageError("candidate checksum inventory mismatch")
    for relative_path, expected_sha256 in declared.items():
        path = candidate / Path(*PurePosixPath(relative_path).parts)
        if _sha256_file(path) != expected_sha256:
            raise HumanReviewPackageError(f"candidate checksum mismatch: {relative_path}")


def _validate_schema(
    validator: Draft202012Validator,
    document: Mapping[str, Any],
    label: str,
) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        path = ".".join(str(part) for part in errors[0].absolute_path) or "<root>"
        raise HumanReviewPackageError(f"{label} schema failure at {path}: {errors[0].message}")


def _load_schema(path: Path) -> dict[str, Any]:
    schema = _read_json(path)
    Draft202012Validator.check_schema(schema)
    return schema


def _file_entries(root: Path, paths: Iterable[Path]) -> list[dict[str, Any]]:
    entries = []
    for relative_path in sorted(paths, key=lambda item: item.as_posix()):
        path = root / relative_path
        if not path.is_file():
            raise HumanReviewPackageError(
                f"human-review inventory input is missing: {relative_path.as_posix()}"
            )
        raw = _raw_lf_bytes(path)
        entries.append(
            {
                "path": relative_path.as_posix(),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "hash_mode": HASH_MODE,
            }
        )
    return entries


def _inventory_sha256(entries: Sequence[Mapping[str, Any]]) -> str:
    payload = json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_checksums(package: Path) -> None:
    lines = [
        f"{_sha256_file(path)}  {path.relative_to(package).as_posix()}"
        for path in sorted(package.rglob("*"), key=lambda item: item.as_posix())
        if path.is_file() and path.name != CHECKSUM_FILENAME
    ]
    _write_text(package / CHECKSUM_FILENAME, "\n".join(lines) + "\n")


def _validate_checksums(package: Path) -> None:
    checksum_path = package / CHECKSUM_FILENAME
    declared: dict[str, str] = {}
    for line in _raw_lf_bytes(checksum_path).decode("utf-8").splitlines():
        parts = line.split("  ", maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64 or parts[1] in declared:
            raise HumanReviewPackageError("human-review checksum line is invalid")
        declared[parts[1]] = parts[0]
    actual = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if set(declared) != actual:
        raise HumanReviewPackageError("human-review checksum inventory mismatch")
    for relative_path, expected_sha256 in declared.items():
        path = package / Path(*PurePosixPath(relative_path).parts)
        if _sha256_file(path) != expected_sha256:
            raise HumanReviewPackageError(f"human-review checksum mismatch: {relative_path}")


def _assert_text_tree(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise HumanReviewPackageError("human-review package symlinks are forbidden")
        if path.is_file():
            _raw_lf_bytes(path)


def _raw_lf_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if raw.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        raise HumanReviewPackageError(f"text file contains a BOM: {path.name}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HumanReviewPackageError(f"text file is not UTF-8: {path.name}") from exc
    if b"\r" in raw:
        raise HumanReviewPackageError(f"text file is not LF-only: {path.name}")
    return raw


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            _raw_lf_bytes(path).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        )
    except (_DuplicateJsonKey, json.JSONDecodeError, ValueError) as exc:
        raise HumanReviewPackageError(f"invalid JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise HumanReviewPackageError(f"JSON root must be an object: {path.name}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    raw = _raw_lf_bytes(path).decode("utf-8")
    if not raw.endswith("\n") or not raw:
        raise HumanReviewPackageError(f"JSONL must end with LF: {path.name}")
    rows = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line:
            raise HumanReviewPackageError(f"blank JSONL line: {path.name}:{line_number}")
        try:
            value = json.loads(
                line,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
            )
        except (_DuplicateJsonKey, json.JSONDecodeError, ValueError) as exc:
            raise HumanReviewPackageError(f"invalid JSONL: {path.name}:{line_number}") from exc
        if not isinstance(value, dict):
            raise HumanReviewPackageError(f"JSONL row must be an object: {path.name}:{line_number}")
        rows.append(value)
    return rows


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(payload))


def _json_bytes(payload: Any) -> bytes:
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


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    path.write_text(content, encoding="utf-8", newline="\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _publish_directory(staged: Path, destination: Path) -> None:
    if destination.exists():
        raise HumanReviewPackageError("human-review package appeared before publish")
    try:
        os.replace(staged, destination)
    except OSError as exc:
        raise HumanReviewPackageError("human-review package atomic publish failed") from exc


def _cleanup_pending_directory(
    temporary_root: Path,
    pending_root: Path,
    *,
    expected_prefix: str,
) -> None:
    resolved = temporary_root.resolve()
    expected_parent = pending_root.resolve()
    if resolved.parent != expected_parent or not resolved.name.startswith(expected_prefix):
        raise HumanReviewPackageError("refuse to clean an unowned pending directory")
    if resolved.exists():
        shutil.rmtree(resolved)

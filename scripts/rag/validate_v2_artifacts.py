"""Validate a RagChunkV2 candidate without changing it or calling external services."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SOURCE_COUNT = 17
EXPECTED_CHUNK_COUNT = 726
_VERSION_PATTERN = re.compile(r"^v[0-9]{3}$")
_ALLOWLIST_PATTERN = re.compile(r"^embedding-staging-allowlist-(v[0-9]{3})\.json$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_HASH_MODE = "sha256_utf8_lf_raw_bytes_v1"
_TESTCASE_HASH_MODE = "sha256_canonical_json_v1"
_COLLECTED_TEST_NODE_HASH_MODE = "sha256_canonical_json_v1"
_COLLECTION_COMMAND = [
    sys.executable,
    "-m",
    "pytest",
    "services/rag-ingestion/tests",
    "--collect-only",
    "-q",
]
_COLLECTION_COMMAND_EVIDENCE = (
    "python -m pytest services/rag-ingestion/tests --collect-only -q"
)
_TEST_EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_version",
        "evidence_version",
        "preflight_version",
        "status",
        "command",
        "evidence_runner_command",
        "evidence_path",
        "evidence_sha256",
        "validation_input_inventory_sha256",
        "junit_validation_input_inventory_sha256",
        "preflight_inventory_path",
        "preflight_inventory_file_sha256",
        "prior_artifact_lock_sha256",
        "prior_artifact_lock_path",
        "prior_artifact_lock_file_sha256",
        "execution_receipt_path",
        "execution_receipt_sha256",
        "pytest_exit_code",
        "pytest_started_at",
        "pytest_finished_at",
        "testcase_identity_hash_mode",
        "testcase_identity_sha256",
        "testcase_identity_count",
        "testcase_files",
        "testcase_classnames",
        "collection_command",
        "collected_test_node_hash_mode",
        "collected_test_node_ids_sha256",
        "collected_test_node_count",
        "execution_timestamp",
        "execution_timestamps",
        "execution_time_seconds",
        "tests",
        "failures",
        "errors",
        "skipped",
        "regression_result",
        "production_approved",
    }
)
_ACTIVE_ARTIFACT_VERSION = "v002"
_ACTIVE_PREFLIGHT_VERSION = "v003"
_ACTIVE_EVIDENCE_VERSION = "v003"
_PRIOR_ALLOWLIST_PATH = Path(
    "data/rag-manifest/AI_Reviewed_Embedding_Staging_Allowlist_v002.json"
)
_PRIOR_SOURCE_REVIEW_PATH = Path(
    "data/rag-manifest/AWS長照_RAG_AI_Source_Review_Current_Candidates_v002.json"
)
_PRIOR_FORMAL_PATHS = (
    Path("data/rag-chunks/README.md"),
    Path("data/rag-chunks/SHA256SUMS.txt"),
    _PRIOR_ALLOWLIST_PATH,
    Path("data/rag-manifest/all_current_chunk_catalog_20260802.json"),
    _PRIOR_SOURCE_REVIEW_PATH,
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
    Path("contracts/schemas/rag/rag-chunk-v2.1.schema.json"),
)


class CandidateValidationError(ValueError):
    """Raised when any candidate invariant fails closed."""


class _DuplicateJsonKey(ValueError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="validate a RagChunkV2 local candidate"
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=REPO_ROOT / "data" / "rag-v2" / "candidates" / "v002",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=REPO_ROOT
        / "contracts"
        / "schemas"
        / "rag"
        / "rag-chunk-v2.1.schema.json",
    )
    args = parser.parse_args(argv)

    try:
        summary = validate_candidate(
            args.candidate.resolve(),
            args.schema.resolve(),
            require_test_evidence=True,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "error_type": type(exc).__name__,
                    "failure_reason": str(exc),
                    "production_approved": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def validate_candidate(
    candidate: Path,
    schema_path: Path,
    *,
    require_test_evidence: bool = False,
) -> dict[str, Any]:
    if not candidate.is_dir():
        raise CandidateValidationError("candidate directory does not exist")
    _validate_candidate_text_bytes(candidate)
    candidate_version = _candidate_version(candidate)
    repository_root = REPO_ROOT.resolve()
    canonical_schema = (
        repository_root / "contracts" / "schemas" / "rag" / "rag-chunk-v2.1.schema.json"
    ).resolve()
    if require_test_evidence and schema_path.resolve() != canonical_schema:
        raise CandidateValidationError(
            "formal validation requires the repository RagChunkV2 schema"
        )
    _validate_required_artifact_paths(
        candidate,
        candidate_version,
        require_test_evidence=require_test_evidence,
    )
    schema = _read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    chunk_files = sorted(
        (candidate / "chunks").rglob("*.jsonl"), key=lambda path: path.as_posix()
    )
    if len(chunk_files) != EXPECTED_SOURCE_COUNT:
        raise CandidateValidationError(
            f"expected {EXPECTED_SOURCE_COUNT} chunk files, found {len(chunk_files)}"
        )

    records: list[dict[str, Any]] = []
    records_by_path: dict[str, list[dict[str, Any]]] = {}
    failures: list[str] = []
    for path in chunk_files:
        relative_path = path.relative_to(candidate).as_posix()
        if path.parent != candidate / "chunks":
            raise CandidateValidationError(
                f"nested chunk file is forbidden: {relative_path}"
            )
        file_records: list[dict[str, Any]] = []
        for line_number, record in _read_jsonl(path):
            for error in validator.iter_errors(record):
                field = ".".join(str(item) for item in error.absolute_path) or "<root>"
                failures.append(f"{path.name}:{line_number}:{field}: {error.message}")
                if len(failures) >= 20:
                    break
            records.append(record)
            file_records.append(record)
            if len(failures) >= 20:
                break
        records_by_path[relative_path] = file_records
        if len(failures) >= 20:
            break
    if failures:
        raise CandidateValidationError(
            "schema validation failed: " + " | ".join(failures)
        )
    if len(records) != EXPECTED_CHUNK_COUNT:
        raise CandidateValidationError(
            f"expected {EXPECTED_CHUNK_COUNT} chunks, found {len(records)}"
        )

    records_by_id: dict[str, dict[str, Any]] = {}
    records_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prior_cache: dict[str, dict[str, dict[str, Any]]] = {}
    for relative_path, file_records in records_by_path.items():
        if not file_records:
            raise CandidateValidationError(f"chunk file is empty: {relative_path}")
        file_sources = {record["identity"]["source_id"] for record in file_records}
        if len(file_sources) != 1:
            raise CandidateValidationError(
                f"chunk file contains multiple sources: {relative_path}"
            )
        source_id = next(iter(file_sources))
        expected_path = f"chunks/{source_id}.rag-chunk-v2.{candidate_version}.jsonl"
        if relative_path != expected_path:
            raise CandidateValidationError(
                f"chunk filename does not match source/version: {relative_path}"
            )
        for record in file_records:
            _validate_record_integrity(
                record,
                candidate_version=candidate_version,
                repository_root=repository_root,
                prior_cache=prior_cache,
            )
            identity = record["identity"]
            chunk_id = identity["chunk_id"]
            if chunk_id in records_by_id:
                raise CandidateValidationError(
                    f"duplicate successor chunk ID: {chunk_id}"
                )
            records_by_id[chunk_id] = record
            records_by_source[identity["source_id"]].append(record)

    if len(records_by_source) != EXPECTED_SOURCE_COUNT:
        raise CandidateValidationError(
            f"expected {EXPECTED_SOURCE_COUNT} sources, found {len(records_by_source)}"
        )
    schema_versions = {record["schema_version"] for record in records}
    if len(schema_versions) != 1:
        raise CandidateValidationError(
            "candidate contains multiple chunk schema versions"
        )
    for source_id, source_records in records_by_source.items():
        indexes = sorted(record["identity"]["chunk_index"] for record in source_records)
        if indexes != list(range(1, len(source_records) + 1)):
            raise CandidateValidationError(
                f"chunk indexes are not continuous for source: {source_id}"
            )

    source_manifest = _read_json(
        candidate / "manifests" / f"source-manifest-{candidate_version}.json"
    )
    chunk_manifest = _read_json(
        candidate / "manifests" / f"chunk-file-manifest-{candidate_version}.json"
    )
    allowlist_path = _find_allowlist(candidate)
    allowlist = _read_json(allowlist_path)
    source_numbers = _validate_allowlist(
        allowlist,
        allowlist_path=allowlist_path,
        candidate_version=candidate_version,
        repository_root=repository_root,
        records_by_id=records_by_id,
        records_by_source=records_by_source,
    )
    _validate_source_manifest(
        source_manifest,
        candidate_version=candidate_version,
        records_by_source=records_by_source,
        source_numbers=source_numbers,
    )
    _validate_chunk_manifest(
        chunk_manifest,
        candidate=candidate,
        candidate_version=candidate_version,
        records_by_path=records_by_path,
    )
    _validate_crosswalk(
        candidate / "crosswalk" / f"chunk-id-crosswalk-{candidate_version}.jsonl",
        candidate_version=candidate_version,
        records_by_id=records_by_id,
    )
    _validate_review_worksheet(
        candidate / "review" / f"human-review-worksheet-{candidate_version}.jsonl",
        candidate_version=candidate_version,
        records_by_id=records_by_id,
    )
    _validate_test_evidence(
        candidate,
        candidate_version=candidate_version,
        repository_root=repository_root,
        require_test_evidence=require_test_evidence,
        prior_artifact_paths={
            record["provenance"]["prior_artifact_path"] for record in records
        },
    )
    _validate_checksums(candidate)
    if require_test_evidence and candidate_version == _ACTIVE_ARTIFACT_VERSION:
        _validate_deterministic_rebuild(candidate, repository_root=repository_root)

    if any(
        record["governance"]["production_approved"] is not False for record in records
    ):
        raise CandidateValidationError("candidate contains production-approved chunks")

    official_chunks = sum(
        record["provenance"]["is_official_source"] for record in records
    )
    official_sources = {
        record["identity"]["source_id"]
        for record in records
        if record["provenance"]["is_official_source"]
    }
    return {
        "status": "PASS",
        "artifact_version": candidate_version,
        "schema_version": next(iter(schema_versions)),
        "source_count": len(records_by_source),
        "chunk_count": len(records),
        "official_source_count": len(official_sources),
        "official_chunk_count": official_chunks,
        "research_source_count": EXPECTED_SOURCE_COUNT - len(official_sources),
        "research_chunk_count": EXPECTED_CHUNK_COUNT - official_chunks,
        "production_approved": False,
    }


def _candidate_version(candidate: Path) -> str:
    version = candidate.name
    if not _VERSION_PATTERN.fullmatch(version):
        raise CandidateValidationError(
            "candidate directory name must be a version such as v001 or v002"
        )
    return version


def _validate_candidate_text_bytes(candidate: Path) -> None:
    """Require every candidate artifact to use plain UTF-8 and LF bytes."""

    root = candidate.resolve()
    for path in sorted(candidate.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise CandidateValidationError(
                f"candidate symbolic links are forbidden: {path.name}"
            )
        if not path.is_file():
            continue
        resolved = path.resolve()
        if root not in resolved.parents:
            raise CandidateValidationError(
                f"candidate file escapes candidate directory: {path.name}"
            )
        raw = path.read_bytes()
        relative_path = path.relative_to(candidate).as_posix()
        if b"\xef\xbb\xbf" in raw:
            raise CandidateValidationError(
                f"candidate file contains a UTF-8 BOM: {relative_path}"
            )
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise CandidateValidationError(
                f"candidate file is not UTF-8: {relative_path}"
            ) from exc
        if b"\r" in raw:
            raise CandidateValidationError(
                f"candidate file must be LF-only (CR byte found): {relative_path}"
            )


def _validate_required_artifact_paths(
    candidate: Path,
    candidate_version: str,
    *,
    require_test_evidence: bool,
) -> None:
    required_paths = [
        Path("README.md"),
        Path("governance") / f"enum-evidence-{candidate_version}.json",
        Path("reports") / f"test-evidence-{candidate_version}.json",
        Path("reports") / f"validation-report-{candidate_version}.json",
        Path("reports") / f"version-difference-summary-{candidate_version}.json",
        Path("review") / f"human-review-worksheet-{candidate_version}.jsonl",
        Path("crosswalk") / f"chunk-id-crosswalk-{candidate_version}.jsonl",
        Path("manifests") / f"source-manifest-{candidate_version}.json",
        Path("manifests") / f"chunk-file-manifest-{candidate_version}.json",
        Path("SHA256SUMS.txt"),
    ]
    if require_test_evidence:
        required_paths.extend(
            (
                Path("reports") / f"pytest-rag-ingestion-{candidate_version}.xml",
                Path("reports") / f"pytest-execution-receipt-{candidate_version}.json",
            )
        )
    missing = [
        path.as_posix() for path in required_paths if not (candidate / path).is_file()
    ]
    if missing:
        raise CandidateValidationError(
            "candidate required artifacts are missing: " + ", ".join(missing)
        )
    if not (candidate / "README.md").read_text(encoding="utf-8").strip():
        raise CandidateValidationError("candidate README is empty")
    enum_evidence = _read_json(
        candidate / "governance" / f"enum-evidence-{candidate_version}.json"
    )
    version_difference = _read_json(
        candidate / "reports" / f"version-difference-summary-{candidate_version}.json"
    )
    if enum_evidence.get("artifact_version") != candidate_version:
        raise CandidateValidationError("enum evidence artifact version mismatch")
    if version_difference.get("artifact_version") != candidate_version:
        raise CandidateValidationError("version-difference artifact version mismatch")
    if version_difference.get("production_approved") is not False:
        raise CandidateValidationError(
            "version-difference report grants production approval"
        )


def _validate_record_integrity(
    record: dict[str, Any],
    *,
    candidate_version: str,
    repository_root: Path,
    prior_cache: dict[str, dict[str, dict[str, Any]]],
) -> None:
    identity = record["identity"]
    content = record["content"]
    citation = record["citation"]
    provenance = record["provenance"]
    chunk_id = identity["chunk_id"]
    if record["artifact_version"] != candidate_version:
        raise CandidateValidationError(f"artifact version mismatch for {chunk_id}")
    if candidate_version == "v001":
        expected_chunk_id = (
            f"{identity['source_id']}_rag_v2_{identity['chunk_index']:04d}"
        )
    else:
        expected_chunk_id = (
            f"{identity['source_id']}_rag_v2_{candidate_version}_"
            f"{identity['chunk_index']:04d}"
        )
    if chunk_id != expected_chunk_id:
        raise CandidateValidationError(
            f"deterministic chunk_id mismatch for {chunk_id}"
        )
    expected_chunk_file_id = f"{identity['source_id']}_rag_v2_{candidate_version}"
    if identity["chunk_file_id"] != expected_chunk_file_id:
        raise CandidateValidationError(
            f"deterministic chunk_file_id mismatch for {chunk_id}"
        )

    text = content["text"]
    embedding_text = content["embedding_text"]
    if content["char_count"] != len(text):
        raise CandidateValidationError(f"char_count mismatch for {chunk_id}")
    if content["embedding_char_count"] != len(embedding_text):
        raise CandidateValidationError(f"embedding_char_count mismatch for {chunk_id}")
    if content["text_sha256"] != _sha256_text(text):
        raise CandidateValidationError(f"text_sha256 mismatch for {chunk_id}")
    if content["embedding_text_sha256"] != _sha256_text(embedding_text):
        raise CandidateValidationError(f"embedding_text_sha256 mismatch for {chunk_id}")

    _validate_citation_pages(
        citation,
        candidate_version=candidate_version,
        chunk_id=chunk_id,
    )
    if candidate_version != "v001":
        is_official = provenance["is_official_source"]
        if not is_official and (
            citation["direct_official_source_url"] is not None
            or citation["official_source_page_url"] is not None
        ):
            raise CandidateValidationError(
                f"research source uses an official-only citation URL for {chunk_id}"
            )
        if is_official and (
            citation["direct_official_source_url"] != citation.get("direct_source_url")
            or citation["official_source_page_url"] != citation.get("source_page_url")
        ):
            raise CandidateValidationError(
                f"official citation URL aliases differ for {chunk_id}"
            )

    prior_path = provenance["prior_artifact_path"]
    prior_records = _load_prior_records(
        repository_root,
        prior_path,
        prior_cache=prior_cache,
    )
    prior_chunk_id = identity["prior_chunk_id"]
    prior = prior_records.get(prior_chunk_id)
    if prior is None:
        raise CandidateValidationError(
            f"prior chunk is missing for {chunk_id}: {prior_chunk_id}"
        )
    if prior.get("text") != text:
        raise CandidateValidationError(f"V1 text differs for {chunk_id}")
    if prior.get("embedding_text") != embedding_text:
        raise CandidateValidationError(f"V1 embedding_text differs for {chunk_id}")
    if prior.get("source_id") != identity["source_id"]:
        raise CandidateValidationError(f"V1 source_id differs for {chunk_id}")
    if prior.get("chunk_index") != identity["chunk_index"]:
        raise CandidateValidationError(f"V1 chunk_index differs for {chunk_id}")


def _validate_citation_pages(
    citation: Mapping[str, Any],
    *,
    candidate_version: str,
    chunk_id: str,
) -> None:
    page_fields = (
        ("physical_page_start", "physical_page_end"),
        ("printed_page_start", "printed_page_end"),
    )
    has_page_range = False
    for start_field, end_field in page_fields:
        start = citation.get(start_field)
        end = citation.get(end_field)
        if (start is None) != (end is None):
            raise CandidateValidationError(
                f"citation page range is incomplete for {chunk_id}: "
                f"{start_field}/{end_field}"
            )
        if start is None:
            continue
        has_page_range = True
        if type(start) is not int or type(end) is not int or start < 1 or end < 1:
            raise CandidateValidationError(
                f"citation page range must use positive integers for {chunk_id}"
            )
        if end < start:
            raise CandidateValidationError(
                f"citation page range is reversed for {chunk_id}: "
                f"{start_field}/{end_field}"
            )
    if has_page_range:
        return

    locator = citation.get("source_locator")
    if isinstance(locator, str) and locator.strip():
        return
    url_fields = (
        ("direct_official_source_url", "official_source_page_url")
        if candidate_version == "v001"
        else ("direct_source_url", "source_page_url")
    )
    if not any(
        isinstance(citation.get(field), str) and citation[field].strip()
        for field in url_fields
    ):
        raise CandidateValidationError(
            f"citation without page numbers lacks a source locator or URL for {chunk_id}"
        )


def _load_prior_records(
    repository_root: Path,
    relative_path: str,
    *,
    prior_cache: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    if relative_path in prior_cache:
        return prior_cache[relative_path]
    pure_path = PurePosixPath(relative_path)
    if (
        pure_path.is_absolute()
        or ".." in pure_path.parts
        or pure_path.parts[:3] != ("data", "rag-chunks", "approved")
        or pure_path.suffix != ".jsonl"
    ):
        raise CandidateValidationError(f"invalid prior artifact path: {relative_path}")
    approved_root = (repository_root / "data" / "rag-chunks" / "approved").resolve()
    path = (repository_root / Path(*pure_path.parts)).resolve()
    if approved_root not in path.parents or not path.is_file():
        raise CandidateValidationError(
            f"prior artifact is unavailable: {relative_path}"
        )

    by_id: dict[str, dict[str, Any]] = {}
    for line_number, record in _read_jsonl(path):
        chunk_id = record.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id:
            raise CandidateValidationError(
                f"prior chunk_id is invalid: {relative_path}:{line_number}"
            )
        if chunk_id in by_id:
            raise CandidateValidationError(
                f"duplicate prior chunk ID in {relative_path}: {chunk_id}"
            )
        if not isinstance(record.get("text"), str) or not isinstance(
            record.get("embedding_text"), str
        ):
            raise CandidateValidationError(
                f"prior text fields are invalid: {relative_path}:{line_number}"
            )
        by_id[chunk_id] = record
    prior_cache[relative_path] = by_id
    return by_id


def _find_allowlist(candidate: Path) -> Path:
    paths = sorted(
        (candidate / "manifests").glob("embedding-staging-allowlist-v*.json"),
        key=lambda path: path.name,
    )
    if len(paths) != 1 or _ALLOWLIST_PATTERN.fullmatch(paths[0].name) is None:
        raise CandidateValidationError(
            "candidate must contain exactly one versioned embedding staging allowlist"
        )
    return paths[0]


def _validate_allowlist(
    document: dict[str, Any],
    *,
    allowlist_path: Path,
    candidate_version: str,
    repository_root: Path,
    records_by_id: Mapping[str, dict[str, Any]],
    records_by_source: Mapping[str, Sequence[dict[str, Any]]],
) -> dict[str, int]:
    match = _ALLOWLIST_PATTERN.fullmatch(allowlist_path.name)
    assert match is not None
    if document.get("schema_version") != match.group(1):
        raise CandidateValidationError("allowlist filename/schema version mismatch")
    if candidate_version == "v002" and match.group(1) != "v003":
        raise CandidateValidationError("v002 candidate requires allowlist v003")
    if document.get("artifact_version") != candidate_version:
        raise CandidateValidationError("allowlist artifact version mismatch")
    if document.get("source_count") != len(records_by_source) or document.get(
        "chunk_count"
    ) != len(records_by_id):
        raise CandidateValidationError(
            "allowlist count declaration does not match candidate"
        )

    sources = document.get("sources")
    entries = document.get("entries")
    if not isinstance(sources, list) or not isinstance(entries, list):
        raise CandidateValidationError("allowlist sources/entries must be arrays")
    source_by_id: dict[str, dict[str, Any]] = {}
    source_numbers: dict[str, int] = {}
    seen_numbers: set[int] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise CandidateValidationError("allowlist source must be an object")
        source_id = source.get("source_id")
        source_number = source.get("source_number")
        if not isinstance(source_id, str) or source_id in source_by_id:
            raise CandidateValidationError(
                "allowlist source IDs are invalid or duplicated"
            )
        if (
            isinstance(source_number, bool)
            or not isinstance(source_number, int)
            or source_number in seen_numbers
        ):
            raise CandidateValidationError(
                "allowlist source numbers are invalid or duplicated"
            )
        source_by_id[source_id] = source
        source_numbers[source_id] = source_number
        seen_numbers.add(source_number)
    if set(source_by_id) != set(records_by_source):
        raise CandidateValidationError(
            "allowlist source IDs do not exactly match candidate"
        )

    entry_by_id: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = defaultdict(int)
    for entry in entries:
        if not isinstance(entry, dict):
            raise CandidateValidationError("allowlist entry must be an object")
        chunk_id = entry.get("chunk_id")
        if not isinstance(chunk_id, str) or chunk_id in entry_by_id:
            raise CandidateValidationError(
                "allowlist chunk IDs are invalid or duplicated"
            )
        entry_by_id[chunk_id] = entry
        source_id = entry.get("source_id")
        if isinstance(source_id, str):
            counts[source_id] += 1
    if set(entry_by_id) != set(records_by_id):
        raise CandidateValidationError(
            "allowlist chunk IDs do not exactly match candidate"
        )

    for chunk_id, record in records_by_id.items():
        entry = entry_by_id[chunk_id]
        identity = record["identity"]
        content = record["content"]
        source_id = identity["source_id"]
        expected = {
            "source_id": source_id,
            "source_number": source_numbers[source_id],
            "prior_chunk_id": identity["prior_chunk_id"],
            "chunk_index": identity["chunk_index"],
            "text_sha256": content["text_sha256"],
            "embedding_text_sha256": content["embedding_text_sha256"],
            "retrieval_eligible": record["retrieval_policy"]["retrieval_eligible"],
        }
        if candidate_version == "v002":
            expected.update(
                {
                    "supersedes_artifact_version": "v001",
                    "supersedes_chunk_id": (
                        f"{source_id}_rag_v2_{identity['chunk_index']:04d}"
                    ),
                }
            )
        for field, value in expected.items():
            if entry.get(field) != value:
                raise CandidateValidationError(
                    f"allowlist {field} linkage mismatch for {chunk_id}"
                )
        if entry.get("production_gate") != "BLOCKED":
            raise CandidateValidationError(
                f"allowlist production gate is open for {chunk_id}"
            )
        fixed_entry_governance = {
            "allowed_use": "INTERNAL_EMERGENCY_DEMO_ONLY",
            "signature_required": True,
            "review_status": "needs_review",
            "human_source_review": "NOT_COMPLETED",
            "embedding_status": "NOT_STARTED",
            "opensearch_indexing_status": "NOT_STARTED",
            "production_gate": "BLOCKED",
        }
        if any(
            entry.get(field) != value for field, value in fixed_entry_governance.items()
        ):
            raise CandidateValidationError(
                f"allowlist entry governance mismatch for {chunk_id}"
            )
        if candidate_version == "v002" and entry != {
            "chunk_id": chunk_id,
            **expected,
            **fixed_entry_governance,
        }:
            raise CandidateValidationError(
                f"allowlist entry contains unexpected linkage for {chunk_id}"
            )

    for source_id, source in source_by_id.items():
        if source.get("chunk_count") != len(records_by_source[source_id]):
            raise CandidateValidationError(
                f"allowlist source chunk_count mismatch for {source_id}"
            )
        if counts.get(source_id, 0) != len(records_by_source[source_id]):
            raise CandidateValidationError(
                f"allowlist entry source count mismatch for {source_id}"
            )
        if source.get("successor_artifact_version") != candidate_version:
            raise CandidateValidationError(
                f"allowlist successor version mismatch for {source_id}"
            )
        if source.get("production_gate") != "BLOCKED":
            raise CandidateValidationError(
                f"allowlist source production gate is open for {source_id}"
            )
        fixed_source_governance = {
            "review_status": "needs_review",
            "human_source_review": "NOT_COMPLETED",
            "production_gate": "BLOCKED",
            "storage_target": "local_pending_upload",
        }
        if any(
            source.get(field) != value
            for field, value in fixed_source_governance.items()
        ):
            raise CandidateValidationError(
                f"allowlist source governance mismatch for {source_id}"
            )
    fixed_document_governance = {
        "status": "DRAFT_FIXED_HASH_NOT_EFFECTIVE_UNTIL_PROJECT_OWNER_SIGNATURE",
        "allowed_use": "INTERNAL_EMERGENCY_DEMO_ONLY",
        "public_redistribution_allowed": False,
        "project_owner_risk_acceptance": "NOT_SIGNED",
        "human_source_review": "NOT_COMPLETED",
        "embedding_status": "NOT_STARTED",
        "opensearch_indexing_status": "NOT_STARTED",
        "production_status": "BLOCKED",
    }
    if any(
        document.get(field) != value
        for field, value in fixed_document_governance.items()
    ):
        raise CandidateValidationError("allowlist document governance mismatch")
    if candidate_version == "v002" and document.get(
        "supersedes_allowlist_sha256"
    ) != _sha256_file(repository_root / _PRIOR_ALLOWLIST_PATH):
        raise CandidateValidationError("allowlist superseded V1 hash mismatch")
    return source_numbers


def _validate_source_manifest(
    document: dict[str, Any],
    *,
    candidate_version: str,
    records_by_source: Mapping[str, Sequence[dict[str, Any]]],
    source_numbers: Mapping[str, int],
) -> None:
    if document.get("artifact_version") != candidate_version:
        raise CandidateValidationError("source manifest artifact version mismatch")
    if document.get("source_count") != len(records_by_source) or document.get(
        "chunk_count"
    ) != sum(map(len, records_by_source.values())):
        raise CandidateValidationError(
            "source manifest count declaration does not match candidate"
        )
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise CandidateValidationError("source manifest sources must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            raise CandidateValidationError("source manifest entry must be an object")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or source_id in by_id:
            raise CandidateValidationError(
                "source manifest IDs are invalid or duplicated"
            )
        by_id[source_id] = source
    if set(by_id) != set(records_by_source):
        raise CandidateValidationError(
            "source manifest IDs do not exactly match candidate"
        )

    for source_id, records in records_by_source.items():
        source = by_id[source_id]
        first = records[0]
        expected_scalars = {
            "source_number": source_numbers[source_id],
            "chunk_count": len(records),
            "authority_level": first["provenance"]["authority_level"],
            "source_type": first["provenance"]["source_type"],
            "is_official_source": first["provenance"]["is_official_source"],
        }
        for field, value in expected_scalars.items():
            if source.get(field) != value:
                raise CandidateValidationError(
                    f"source manifest {field} linkage mismatch for {source_id}"
                )
        expected_lists = {
            "source_versions": _unique_non_null(
                record["provenance"]["source_version"] for record in records
            ),
            "direct_official_source_urls": _unique_non_null(
                record["citation"]["direct_official_source_url"] for record in records
            ),
            "official_source_page_urls": _unique_non_null(
                record["citation"]["official_source_page_url"] for record in records
            ),
            "license_evidence_urls": _unique_non_null(
                record["citation"]["license_evidence_url"] for record in records
            ),
            "storage_urls": _unique_non_null(
                record["citation"]["storage_url"] for record in records
            ),
        }
        if candidate_version != "v001":
            expected_lists.update(
                {
                    "direct_source_urls": _unique_non_null(
                        record["citation"]["direct_source_url"] for record in records
                    ),
                    "source_page_urls": _unique_non_null(
                        record["citation"]["source_page_url"] for record in records
                    ),
                }
            )
        for field, values in expected_lists.items():
            actual = source.get(field)
            if (
                not isinstance(actual, list)
                or any(not isinstance(value, str) for value in actual)
                or sorted(actual) != values
            ):
                raise CandidateValidationError(
                    f"source manifest {field} linkage mismatch for {source_id}"
                )
        if source.get("production_approved") is not False:
            raise CandidateValidationError(
                f"source manifest production approval is open for {source_id}"
            )
        fixed_governance = {
            "review_status": "needs_review",
            "ingestion_status": "staging",
            "production_approved": False,
            "storage_target": "local_pending_upload",
        }
        if any(source.get(field) != value for field, value in fixed_governance.items()):
            raise CandidateValidationError(
                f"source manifest governance mismatch for {source_id}"
            )


def _validate_chunk_manifest(
    document: dict[str, Any],
    *,
    candidate: Path,
    candidate_version: str,
    records_by_path: Mapping[str, Sequence[dict[str, Any]]],
) -> None:
    if document.get("artifact_version") != candidate_version:
        raise CandidateValidationError("chunk manifest artifact version mismatch")
    if document.get("chunk_file_count") != len(records_by_path) or document.get(
        "chunk_count"
    ) != sum(map(len, records_by_path.values())):
        raise CandidateValidationError(
            "chunk manifest count declaration does not match candidate"
        )
    files = document.get("files")
    if not isinstance(files, list):
        raise CandidateValidationError("chunk manifest files must be an array")
    by_path: dict[str, dict[str, Any]] = {}
    for item in files:
        if not isinstance(item, dict):
            raise CandidateValidationError("chunk manifest entry must be an object")
        relative_path = item.get("path")
        if not isinstance(relative_path, str) or relative_path in by_path:
            raise CandidateValidationError(
                "chunk manifest paths are invalid or duplicated"
            )
        by_path[relative_path] = item
    if set(by_path) != set(records_by_path):
        raise CandidateValidationError(
            "chunk manifest paths do not exactly match candidate"
        )

    for relative_path, records in records_by_path.items():
        item = by_path[relative_path]
        source_ids = {record["identity"]["source_id"] for record in records}
        chunk_file_ids = {record["identity"]["chunk_file_id"] for record in records}
        schema_versions = {record["schema_version"] for record in records}
        if (
            len(source_ids) != 1
            or len(chunk_file_ids) != 1
            or len(schema_versions) != 1
        ):
            raise CandidateValidationError(
                f"inconsistent chunk file linkage: {relative_path}"
            )
        expected = {
            "source_id": next(iter(source_ids)),
            "chunk_file_id": next(iter(chunk_file_ids)),
            "chunk_count": len(records),
            "schema_version": next(iter(schema_versions)),
            "artifact_version": candidate_version,
            "size_bytes": (candidate / relative_path).stat().st_size,
            "sha256": _sha256_file(candidate / relative_path),
        }
        for field, value in expected.items():
            if item.get(field) != value:
                raise CandidateValidationError(
                    f"chunk manifest {field} linkage mismatch for {relative_path}"
                )
        if item.get("production_approved") is not False:
            raise CandidateValidationError(
                f"chunk manifest production approval is open for {relative_path}"
            )
        fixed_governance = {
            "review_status": "needs_review",
            "ingestion_status": "staging",
            "embedding_status": "not_started",
            "production_approved": False,
            "storage_target": "local_pending_upload",
        }
        if any(item.get(field) != value for field, value in fixed_governance.items()):
            raise CandidateValidationError(
                f"chunk manifest governance mismatch for {relative_path}"
            )


def _validate_crosswalk(
    path: Path,
    *,
    candidate_version: str,
    records_by_id: Mapping[str, dict[str, Any]],
) -> None:
    rows = _read_jsonl(path)
    if len(rows) != len(records_by_id):
        raise CandidateValidationError("crosswalk row count does not match candidate")
    by_successor: dict[str, dict[str, Any]] = {}
    prior_ids: set[str] = set()
    for _, row in rows:
        successor_id = row.get("successor_chunk_id")
        prior_id = row.get("prior_chunk_id")
        if not isinstance(successor_id, str) or successor_id in by_successor:
            raise CandidateValidationError(
                "crosswalk successor IDs are invalid or duplicated"
            )
        if not isinstance(prior_id, str) or prior_id in prior_ids:
            raise CandidateValidationError(
                "crosswalk prior IDs are invalid or duplicated"
            )
        by_successor[successor_id] = row
        prior_ids.add(prior_id)
    if set(by_successor) != set(records_by_id):
        raise CandidateValidationError(
            "crosswalk successor IDs do not exactly match candidate"
        )
    expected_prior_ids = {
        record["identity"]["prior_chunk_id"] for record in records_by_id.values()
    }
    if prior_ids != expected_prior_ids:
        raise CandidateValidationError(
            "crosswalk prior IDs do not exactly match candidate"
        )

    for chunk_id, record in records_by_id.items():
        row = by_successor[chunk_id]
        identity = record["identity"]
        expected = {
            "schema_version": "1.0.0",
            "artifact_version": candidate_version,
            "source_id": identity["source_id"],
            "prior_chunk_id": identity["prior_chunk_id"],
            "successor_chunk_id": chunk_id,
            "prior_artifact_path": record["provenance"]["prior_artifact_path"],
            "relationship": "metadata_successor",
            "text_sha256_equal": True,
            "embedding_text_sha256_equal": True,
            "status_change_recommendation": "human_review_required",
            "status_changed_automatically": False,
        }
        if candidate_version == "v002":
            expected.update(
                {
                    "supersedes_artifact_version": "v001",
                    "supersedes_chunk_id": (
                        f"{identity['source_id']}_rag_v2_"
                        f"{identity['chunk_index']:04d}"
                    ),
                }
            )
        if row != expected:
            raise CandidateValidationError(f"crosswalk linkage mismatch for {chunk_id}")


def _validate_review_worksheet(
    path: Path,
    *,
    candidate_version: str,
    records_by_id: Mapping[str, dict[str, Any]],
) -> None:
    expected_by_id: dict[str, dict[str, Any]] = {}
    for chunk_id, record in records_by_id.items():
        warnings = record["provenance"]["mapping_warnings"]
        block_reasons = record["retrieval_policy"]["retrieval_block_reasons"]
        if warnings or block_reasons:
            identity = record["identity"]
            expected_by_id[chunk_id] = {
                "schema_version": "1.0.0",
                "worksheet_version": candidate_version,
                "source_id": identity["source_id"],
                "prior_chunk_id": identity["prior_chunk_id"],
                "successor_chunk_id": chunk_id,
                "retrieval_block_reasons": block_reasons,
                "mapping_warnings": warnings,
                "review_status": "needs_review",
                "production_approved": False,
            }

    actual_by_id: dict[str, dict[str, Any]] = {}
    for _, row in _read_jsonl(path):
        successor_id = row.get("successor_chunk_id")
        if not isinstance(successor_id, str) or successor_id in actual_by_id:
            raise CandidateValidationError(
                "review worksheet successor IDs are invalid or duplicated"
            )
        actual_by_id[successor_id] = row
    if set(actual_by_id) != set(expected_by_id):
        raise CandidateValidationError(
            "review worksheet IDs do not exactly match review-required chunks"
        )
    for chunk_id, expected in expected_by_id.items():
        if actual_by_id[chunk_id] != expected:
            raise CandidateValidationError(
                f"review worksheet linkage mismatch for {chunk_id}"
            )


def _validate_test_evidence(
    candidate: Path,
    *,
    candidate_version: str,
    repository_root: Path,
    require_test_evidence: bool,
    prior_artifact_paths: set[str] | None = None,
) -> None:
    evidence = _read_json(
        candidate / "reports" / f"test-evidence-{candidate_version}.json"
    )
    status = evidence.get("status")
    if status == "NOT_REQUIRED":
        if require_test_evidence:
            raise CandidateValidationError(
                "formal validation requires passing test evidence"
            )
        return
    if status != "PASS":
        raise CandidateValidationError(
            "test evidence status must be PASS or NOT_REQUIRED"
        )
    if (
        not require_test_evidence
        and candidate_version == "v001"
        and "evidence_version" not in evidence
    ):
        return
    if evidence.get("schema_version") != "1.0.0":
        raise CandidateValidationError("test evidence schema version mismatch")
    if evidence.get("artifact_version") != candidate_version:
        raise CandidateValidationError("test evidence artifact version mismatch")
    if set(evidence) != _TEST_EVIDENCE_FIELDS:
        raise CandidateValidationError(
            "test evidence contains missing or unexpected fields"
        )

    preflight_version = _required_version(
        evidence, "preflight_version", "test evidence"
    )
    evidence_version = _required_version(evidence, "evidence_version", "test evidence")
    if candidate_version == "v002" and (
        preflight_version != "v003" or evidence_version != "v003"
    ):
        raise CandidateValidationError(
            "v002 candidate requires preflight v003 and evidence v003"
        )
    expected_evidence_path = (
        f"data/rag-v2/evidence/{evidence_version}/pytest-rag-ingestion.xml"
    )
    if evidence.get("evidence_path") != expected_evidence_path:
        raise CandidateValidationError("test evidence JUnit path/version mismatch")
    expected_inventory_path = (
        f"data/rag-v2/preflight/{preflight_version}/validation-input-inventory.json"
    )
    expected_lock_path = (
        f"data/rag-v2/preflight/{preflight_version}/prior-artifact-lock.json"
    )
    if evidence.get("preflight_inventory_path") != expected_inventory_path:
        raise CandidateValidationError(
            "test evidence preflight inventory path mismatch"
        )
    if evidence.get("prior_artifact_lock_path") != expected_lock_path:
        raise CandidateValidationError("test evidence prior-lock path mismatch")

    inventory_digest = _required_sha256(
        evidence,
        "validation_input_inventory_sha256",
        "test evidence",
    )
    inventory_file_sha256 = _required_sha256(
        evidence,
        "preflight_inventory_file_sha256",
        "test evidence",
    )
    prior_digest = _required_sha256(
        evidence,
        "prior_artifact_lock_sha256",
        "test evidence",
    )
    prior_file_sha256 = _required_sha256(
        evidence,
        "prior_artifact_lock_file_sha256",
        "test evidence",
    )
    inventory_paths = _validate_inventory_evidence(
        repository_root / Path(*PurePosixPath(expected_inventory_path).parts),
        repository_root=repository_root,
        expected_version=preflight_version,
        expected_kind="validation_input_inventory",
        expected_file_sha256=inventory_file_sha256,
        expected_inventory_sha256=inventory_digest,
    )
    locked_paths = _validate_inventory_evidence(
        repository_root / Path(*PurePosixPath(expected_lock_path).parts),
        repository_root=repository_root,
        expected_version=preflight_version,
        expected_kind="prior_artifact_immutable_lock",
        expected_file_sha256=prior_file_sha256,
        expected_inventory_sha256=prior_digest,
    )
    if prior_artifact_paths is not None and not prior_artifact_paths <= locked_paths:
        raise CandidateValidationError(
            "prior-artifact lock does not cover every candidate provenance path"
        )

    validation_report = _read_json(
        candidate / "reports" / f"validation-report-{candidate_version}.json"
    )
    expected_report_values = {
        "artifact_version": candidate_version,
        "preflight_version": preflight_version,
        "status": "PASS",
        "fail_count": 0,
        "validation_input_inventory_sha256": inventory_digest,
        "prior_artifact_lock_sha256": prior_digest,
        "production_approved": False,
    }
    for field, value in expected_report_values.items():
        if validation_report.get(field) != value:
            raise CandidateValidationError(
                f"validation report {field} does not match test/preflight evidence"
            )

    evidence_sha256 = _required_sha256(evidence, "evidence_sha256", "test evidence")
    copied_junit = (
        candidate / "reports" / f"pytest-rag-ingestion-{candidate_version}.xml"
    )
    active_junit = repository_root / Path(*PurePosixPath(expected_evidence_path).parts)
    if _sha256_file(copied_junit) != evidence_sha256:
        raise CandidateValidationError(
            "copied JUnit SHA-256 does not match test evidence"
        )
    if _sha256_file(active_junit) != evidence_sha256:
        raise CandidateValidationError(
            "active JUnit SHA-256 does not match test evidence"
        )
    execution_receipt = _validate_execution_receipt(
        candidate,
        candidate_version=candidate_version,
        repository_root=repository_root,
        evidence=evidence,
        evidence_version=evidence_version,
        preflight_version=preflight_version,
        junit_sha256=evidence_sha256,
        inventory_digest=inventory_digest,
        inventory_path=expected_inventory_path,
        inventory_file_sha256=inventory_file_sha256,
        prior_digest=prior_digest,
        prior_path=expected_lock_path,
        prior_file_sha256=prior_file_sha256,
    )
    if evidence.get("command") != execution_receipt["display_command"]:
        raise CandidateValidationError(
            "test evidence command differs from the validated execution receipt"
        )
    if (
        evidence.get("evidence_runner_command")
        != "python scripts/rag/build_v2_artifacts.py evidence"
    ):
        raise CandidateValidationError("test evidence runner command mismatch")

    junit = _junit_evidence(copied_junit)
    if junit["property_values"].get("validation_input_inventory_sha256") != [
        inventory_digest
    ]:
        raise CandidateValidationError(
            "JUnit validation inventory property does not match test evidence"
        )
    if evidence.get("junit_validation_input_inventory_sha256") != inventory_digest:
        raise CandidateValidationError("test evidence JUnit inventory digest mismatch")
    for field in ("tests", "failures", "errors", "skipped"):
        if evidence.get(field) != junit[field]:
            raise CandidateValidationError(
                f"test evidence {field} does not match JUnit"
            )
    if junit["failures"] != 0 or junit["errors"] != 0:
        raise CandidateValidationError("JUnit contains failed tests")
    if evidence.get("regression_result") != "PASS":
        raise CandidateValidationError("test evidence regression result is not PASS")
    if evidence.get("testcase_identity_hash_mode") != _TESTCASE_HASH_MODE:
        raise CandidateValidationError("testcase identity hash mode is unsupported")
    if evidence.get("testcase_identity_count") != len(junit["testcase_identities"]):
        raise CandidateValidationError("testcase identity count does not match JUnit")
    if evidence.get("testcase_identity_sha256") != junit["testcase_identity_sha256"]:
        raise CandidateValidationError("testcase identity digest does not match JUnit")
    if (
        not require_test_evidence
        and evidence.get("testcase_files") != junit["testcase_files"]
    ):
        raise CandidateValidationError("testcase file inventory does not match JUnit")
    if evidence.get("testcase_classnames") != junit["testcase_classnames"]:
        raise CandidateValidationError(
            "testcase classname inventory does not match JUnit"
        )
    if evidence.get("execution_timestamps") != junit["execution_timestamps"]:
        raise CandidateValidationError("test execution timestamps do not match JUnit")
    if evidence.get("execution_timestamp") != junit["execution_timestamps"][0]:
        raise CandidateValidationError("test execution timestamp does not match JUnit")
    if evidence.get("execution_time_seconds") != junit["execution_time_seconds"]:
        raise CandidateValidationError("test execution time does not match JUnit")
    if evidence.get("production_approved") is not False:
        raise CandidateValidationError("test evidence grants production approval")
    if require_test_evidence:
        collected = _collect_test_node_evidence(repository_root)
        expected_collected_fields = {
            "collected_test_node_hash_mode": _COLLECTED_TEST_NODE_HASH_MODE,
            "collected_test_node_ids_sha256": collected["sha256"],
            "collected_test_node_count": collected["count"],
            "collection_command": _COLLECTION_COMMAND_EVIDENCE,
        }
        for field, value in expected_collected_fields.items():
            if evidence.get(field) != value:
                raise CandidateValidationError(
                    f"test evidence {field} does not match independent collection"
                )
        expected_junit_properties = {
            "collected_test_node_hash_mode": _COLLECTED_TEST_NODE_HASH_MODE,
            "collected_test_node_ids_sha256": collected["sha256"],
            "collected_test_node_count": str(collected["count"]),
        }
        for name, value in expected_junit_properties.items():
            if junit["property_values"].get(name) != [value]:
                raise CandidateValidationError(
                    f"JUnit {name} property does not match independent collection"
                )
        if junit["tests"] != collected["count"]:
            raise CandidateValidationError(
                "JUnit test count does not match independent collection"
            )
        if junit["testcase_identities"] != collected["testcase_identities"]:
            raise CandidateValidationError(
                "JUnit testcase identities do not match independent collection"
            )
        if evidence.get("testcase_files") != collected["test_files"]:
            raise CandidateValidationError(
                "testcase file inventory does not match independent collection"
            )
        collected_inventory_paths = {
            f"services/rag-ingestion/{path}" for path in collected["test_files"]
        }
        if not collected_inventory_paths <= inventory_paths:
            raise CandidateValidationError(
                "collected test file is absent from the frozen validation inventory"
            )


def _validate_execution_receipt(
    candidate: Path,
    *,
    candidate_version: str,
    repository_root: Path,
    evidence: Mapping[str, Any],
    evidence_version: str,
    preflight_version: str,
    junit_sha256: str,
    inventory_digest: str,
    inventory_path: str,
    inventory_file_sha256: str,
    prior_digest: str,
    prior_path: str,
    prior_file_sha256: str,
) -> dict[str, Any]:
    expected_active_path = (
        f"data/rag-v2/evidence/{evidence_version}/pytest-execution-receipt.json"
    )
    if evidence.get("execution_receipt_path") != expected_active_path:
        raise CandidateValidationError("test evidence execution receipt path mismatch")
    expected_sha256 = _required_sha256(
        evidence,
        "execution_receipt_sha256",
        "test evidence",
    )
    active_path = repository_root / Path(*PurePosixPath(expected_active_path).parts)
    copied_path = (
        candidate / "reports" / f"pytest-execution-receipt-{candidate_version}.json"
    )
    _raw_lf_bytes(active_path)
    if _sha256_file(active_path) != expected_sha256:
        raise CandidateValidationError(
            "active execution receipt SHA-256 does not match test evidence"
        )
    if _sha256_file(copied_path) != expected_sha256:
        raise CandidateValidationError(
            "copied execution receipt SHA-256 does not match test evidence"
        )
    if active_path.read_bytes() != copied_path.read_bytes():
        raise CandidateValidationError(
            "active and copied execution receipt bytes differ"
        )

    receipt = _read_json(copied_path)
    expected_values = {
        "schema_version": "1.0.0",
        "artifact_version": candidate_version,
        "preflight_version": preflight_version,
        "evidence_version": evidence_version,
        "status": "PASS",
        "display_command": (
            "python -m pytest services/rag-ingestion/tests --junitxml="
            f"data/rag-v2/evidence/{evidence_version}/pytest-rag-ingestion.xml"
        ),
        "exit_code": 0,
        "validation_input_inventory_sha256": inventory_digest,
        "preflight_inventory_path": inventory_path,
        "preflight_inventory_file_sha256": inventory_file_sha256,
        "prior_artifact_lock_sha256": prior_digest,
        "prior_artifact_lock_path": prior_path,
        "prior_artifact_lock_file_sha256": prior_file_sha256,
        "junit_path": (
            f"data/rag-v2/evidence/{evidence_version}/pytest-rag-ingestion.xml"
        ),
        "junit_sha256": junit_sha256,
        "failure_reasons": [],
        "production_approved": False,
    }
    for field, value in expected_values.items():
        if receipt.get(field) != value:
            raise CandidateValidationError(
                f"execution receipt {field} does not match formal evidence"
            )
    _validate_recorded_pytest_argv(
        receipt.get("executed_argv"),
        evidence_version=evidence_version,
    )
    expected_receipt_fields = set(expected_values) | {
        "executed_argv",
        "started_at",
        "finished_at",
    }
    if set(receipt) != expected_receipt_fields:
        raise CandidateValidationError(
            "execution receipt contains missing or unexpected fields"
        )
    if type(receipt.get("exit_code")) is not int:
        raise CandidateValidationError("execution receipt exit_code must be an integer")
    if (
        type(evidence.get("pytest_exit_code")) is not int
        or evidence.get("pytest_exit_code") != 0
    ):
        raise CandidateValidationError("test evidence pytest exit code is invalid")
    started = _parse_execution_timestamp(
        receipt.get("started_at"), "receipt started_at"
    )
    finished = _parse_execution_timestamp(
        receipt.get("finished_at"), "receipt finished_at"
    )
    if finished < started:
        raise CandidateValidationError("execution receipt timestamps are out of order")
    if evidence.get("pytest_started_at") != receipt.get("started_at"):
        raise CandidateValidationError(
            "test evidence pytest start timestamp differs from receipt"
        )
    if evidence.get("pytest_finished_at") != receipt.get("finished_at"):
        raise CandidateValidationError(
            "test evidence pytest finish timestamp differs from receipt"
        )
    return receipt


def _validate_recorded_pytest_argv(value: Any, *, evidence_version: str) -> None:
    if (
        not isinstance(value, list)
        or len(value) != 5
        or any(not isinstance(argument, str) or not argument for argument in value)
    ):
        raise CandidateValidationError("execution receipt executed_argv is invalid")
    interpreter = value[0]
    interpreter_name = interpreter.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if not (
        PurePosixPath(interpreter).is_absolute()
        or PureWindowsPath(interpreter).is_absolute()
    ) or not interpreter_name.lower().startswith("python"):
        raise CandidateValidationError("execution receipt interpreter path is invalid")
    if value[1:4] != ["-m", "pytest", "services/rag-ingestion/tests"]:
        raise CandidateValidationError(
            "execution receipt argv does not run the full suite"
        )
    junit_prefix = "--junitxml="
    if not value[4].startswith(junit_prefix):
        raise CandidateValidationError("execution receipt argv is missing JUnit output")
    junit_path = value[4][len(junit_prefix) :]
    normalized = junit_path.replace("\\", "/")
    if (
        not (
            PurePosixPath(junit_path).is_absolute()
            or PureWindowsPath(junit_path).is_absolute()
        )
        or ".." in PurePosixPath(normalized).parts
    ):
        raise CandidateValidationError("execution receipt JUnit path is invalid")
    pending_marker = f"/data/rag-v2/.pending/evidence-{evidence_version}-"
    expected_suffix = f"/{evidence_version}/pytest-rag-ingestion.xml"
    if pending_marker not in normalized or not normalized.endswith(expected_suffix):
        raise CandidateValidationError(
            "execution receipt JUnit path is outside its recorded pending run"
        )


def _validate_inventory_evidence(
    path: Path,
    *,
    repository_root: Path,
    expected_version: str,
    expected_kind: str,
    expected_file_sha256: str,
    expected_inventory_sha256: str,
) -> set[str]:
    _raw_lf_bytes(path)
    if _sha256_file(path) != expected_file_sha256:
        raise CandidateValidationError(f"{expected_kind} file SHA-256 mismatch")
    document = _read_json(path)
    if document.get("artifact_version") != expected_version:
        raise CandidateValidationError(f"{expected_kind} version mismatch")
    if document.get("kind") != expected_kind:
        raise CandidateValidationError(f"{expected_kind} kind mismatch")
    if document.get("hash_mode") != _CANONICAL_HASH_MODE:
        raise CandidateValidationError(f"{expected_kind} hash mode is unsupported")
    entries = document.get("entries")
    if not isinstance(entries, list) or document.get("entry_count") != len(entries):
        raise CandidateValidationError(f"{expected_kind} entry count mismatch")
    if document.get("inventory_sha256") != expected_inventory_sha256:
        raise CandidateValidationError(f"{expected_kind} digest mismatch")
    if _inventory_sha256(entries) != expected_inventory_sha256:
        raise CandidateValidationError(f"{expected_kind} entries do not match digest")

    seen_paths: set[str] = set()
    root = repository_root.resolve()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise CandidateValidationError(
                f"{expected_kind} entry {index} is not an object"
            )
        relative_path = entry.get("path")
        if not isinstance(relative_path, str) or relative_path in seen_paths:
            raise CandidateValidationError(
                f"{expected_kind} paths are invalid or duplicated"
            )
        seen_paths.add(relative_path)
        if entry.get("hash_mode") != _CANONICAL_HASH_MODE:
            raise CandidateValidationError(
                f"{expected_kind} entry hash mode is unsupported: {relative_path}"
            )
        pure_path = PurePosixPath(relative_path)
        if pure_path.is_absolute() or ".." in pure_path.parts:
            raise CandidateValidationError(f"unsafe inventory path: {relative_path}")
        current_path = (root / Path(*pure_path.parts)).resolve()
        if root not in current_path.parents or not current_path.is_file():
            raise CandidateValidationError(
                f"inventory path is unavailable: {relative_path}"
            )
        raw_bytes = _raw_lf_bytes(current_path)
        if entry.get("size_bytes") != len(raw_bytes):
            raise CandidateValidationError(f"inventory size mismatch: {relative_path}")
        if entry.get("sha256") != hashlib.sha256(raw_bytes).hexdigest():
            raise CandidateValidationError(
                f"inventory SHA-256 mismatch: {relative_path}"
            )
    expected_paths = _expected_inventory_paths(root, expected_kind)
    if seen_paths != expected_paths:
        missing = sorted(expected_paths - seen_paths)
        unexpected = sorted(seen_paths - expected_paths)
        details = []
        if missing:
            details.append("missing=" + ",".join(missing[:10]))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected[:10]))
        raise CandidateValidationError(
            f"{expected_kind} path set is incomplete or unexpected: "
            + "; ".join(details)
        )
    if expected_kind == "prior_artifact_immutable_lock":
        _validate_historical_candidate_checksums(root)
    current_entries = []
    for relative_path in sorted(expected_paths):
        raw = _raw_lf_bytes(root / Path(*PurePosixPath(relative_path).parts))
        current_entries.append(
            {
                "path": relative_path,
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "hash_mode": _CANONICAL_HASH_MODE,
            }
        )
    expected_document: dict[str, Any] = {
        "schema_version": "1.0.0",
        "artifact_version": expected_version,
        "kind": expected_kind,
        "hash_mode": _CANONICAL_HASH_MODE,
        "entry_count": len(current_entries),
        "inventory_sha256": _inventory_sha256(current_entries),
        "entries": current_entries,
    }
    if expected_kind == "prior_artifact_immutable_lock":
        expected_document["scope"] = (
            "prior V1 formal inputs and every non-active RagV2 candidate, preflight, "
            "and evidence file"
        )
        expected_document["active_exclusions"] = [
            {
                "path": f"data/rag-v2/candidates/{_ACTIVE_ARTIFACT_VERSION}",
                "reason": "active successor candidate; excluded to avoid self-reference",
            },
            {
                "path": f"data/rag-v2/preflight/{_ACTIVE_PREFLIGHT_VERSION}",
                "reason": "active preflight; excluded to avoid self-reference",
            },
            {
                "path": f"data/rag-v2/evidence/{_ACTIVE_EVIDENCE_VERSION}",
                "reason": "active test evidence; bound separately after preflight",
            },
        ]
    if document != expected_document:
        raise CandidateValidationError(
            f"{expected_kind} document differs from the current deterministic inventory"
        )
    expected_bytes = (
        json.dumps(
            expected_document,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    if path.read_bytes() != expected_bytes:
        raise CandidateValidationError(
            f"{expected_kind} bytes are not in deterministic JSON form"
        )
    return seen_paths


def _expected_inventory_paths(repository_root: Path, kind: str) -> set[str]:
    """Rebuild the exact path set used by the active deterministic builder."""

    root = repository_root.resolve()
    if kind == "validation_input_inventory":
        paths = set(_VALIDATION_FIXED_PATHS)
        paths.update(
            path.relative_to(root)
            for path in (root / "data/rag-chunks/approved").glob("*.jsonl")
        )
        paths.update(path.relative_to(root) for path in (root / "config/rag").glob("*"))
        paths.update(
            path.relative_to(root)
            for path in (root / "contracts/schemas/rag").glob("*.json")
        )
        paths.update(
            path.relative_to(root)
            for path in (root / "services/rag-ingestion/src").rglob("*.py")
        )
        paths.update(
            path.relative_to(root)
            for path in (root / "services/rag-ingestion/tests").rglob("*.py")
        )
        return {path.as_posix() for path in paths}
    if kind != "prior_artifact_immutable_lock":
        raise CandidateValidationError(f"unsupported inventory kind: {kind}")

    paths = set(_PRIOR_FORMAL_PATHS)
    paths.update(
        path.relative_to(root)
        for path in (root / "data/rag-chunks/approved").glob("*.jsonl")
    )
    for family, active_version in (
        ("candidates", _ACTIVE_ARTIFACT_VERSION),
        ("preflight", _ACTIVE_PREFLIGHT_VERSION),
        ("evidence", _ACTIVE_EVIDENCE_VERSION),
    ):
        family_root = root / "data/rag-v2" / family
        if not family_root.is_dir():
            continue
        for version_root in sorted(family_root.iterdir(), key=lambda path: path.name):
            if (
                not version_root.is_dir()
                or not version_root.name.startswith("v")
                or not version_root.name[1:].isdigit()
                or version_root.name == active_version
            ):
                continue
            paths.update(
                path.relative_to(root)
                for path in version_root.rglob("*")
                if path.is_file()
            )
    return {path.as_posix() for path in paths}


def _validate_historical_candidate_checksums(repository_root: Path) -> None:
    family_root = repository_root / "data" / "rag-v2" / "candidates"
    if not family_root.is_dir():
        return
    for version_root in sorted(family_root.iterdir(), key=lambda path: path.name):
        if (
            version_root.is_dir()
            and version_root.name.startswith("v")
            and version_root.name[1:].isdigit()
            and version_root.name != _ACTIVE_ARTIFACT_VERSION
        ):
            _validate_checksums(version_root)


def _junit_testcase_summary(root: ET.Element) -> dict[str, Any]:
    identities: list[dict[str, str]] = []
    outcomes = {"failures": 0, "errors": 0, "skipped": 0}
    for testcase in root.iter("testcase"):
        classname = testcase.attrib.get("classname")
        name = testcase.attrib.get("name")
        if not classname or not name:
            raise CandidateValidationError(
                "copied JUnit testcase identity is incomplete"
            )
        identities.append({"classname": classname, "name": name})
        outcome_elements = [
            child.tag
            for child in testcase
            if child.tag in {"failure", "error", "skipped"}
        ]
        if len(outcome_elements) > 1:
            raise CandidateValidationError(
                "copied JUnit testcase has conflicting outcomes"
            )
        if outcome_elements:
            outcome_key = {
                "failure": "failures",
                "error": "errors",
                "skipped": "skipped",
            }[outcome_elements[0]]
            outcomes[outcome_key] += 1
    identities.sort(key=lambda item: (item["classname"], item["name"]))
    tokens = [_json_token(identity) for identity in identities]
    if len(tokens) != len(set(tokens)):
        raise CandidateValidationError(
            "copied JUnit testcase identities are duplicated"
        )
    return {"identities": identities, **outcomes}


def _junit_evidence(path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise CandidateValidationError("copied JUnit XML is invalid") from exc
    all_suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    suites = [suite for suite in all_suites if not list(suite.findall("testsuite"))]
    if not suites:
        raise CandidateValidationError("copied JUnit contains no test suites")
    try:
        totals = {
            field: sum(int(suite.attrib.get(field, "0")) for suite in suites)
            for field in ("tests", "failures", "errors", "skipped")
        }
        execution_time = sum(float(suite.attrib["time"]) for suite in suites)
    except (KeyError, TypeError, ValueError) as exc:
        raise CandidateValidationError(
            "copied JUnit has invalid counts or time"
        ) from exc
    if totals["tests"] < 1 or any(value < 0 for value in totals.values()):
        raise CandidateValidationError("copied JUnit contains no tests")
    if not math.isfinite(execution_time) or execution_time < 0:
        raise CandidateValidationError("copied JUnit execution time is invalid")
    testcase_summary = _junit_testcase_summary(root)
    if len(testcase_summary["identities"]) != totals["tests"]:
        raise CandidateValidationError(
            "copied JUnit testcase count does not match totals"
        )
    for field in ("failures", "errors", "skipped"):
        if testcase_summary[field] != totals[field]:
            raise CandidateValidationError(
                f"copied JUnit testcase {field} do not match suite totals"
            )
    if totals["failures"] or totals["errors"] or totals["skipped"]:
        raise CandidateValidationError(
            "copied JUnit contains failed, errored, or skipped tests"
        )

    property_values: dict[str, list[str | None]] = defaultdict(list)
    for element in root.iter("property"):
        name = element.attrib.get("name")
        if name:
            property_values[name].append(element.attrib.get("value"))
    expected_property_names = {
        "validation_input_inventory_sha256",
        "collected_test_node_hash_mode",
        "collected_test_node_ids_sha256",
        "collected_test_node_count",
    }
    if set(property_values) != expected_property_names:
        raise CandidateValidationError(
            "copied JUnit contains missing or unexpected properties"
        )
    timestamps = sorted(
        {suite.attrib["timestamp"] for suite in suites if suite.attrib.get("timestamp")}
    )
    if not timestamps or len(timestamps) != len(
        {suite.attrib.get("timestamp") for suite in suites}
    ):
        raise CandidateValidationError("copied JUnit is missing an execution timestamp")
    for timestamp in timestamps:
        _validate_execution_timestamp(timestamp)

    testcase_identities = testcase_summary["identities"]
    testcase_digest = _sha256_text(
        json.dumps(
            testcase_identities,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return {
        **totals,
        "execution_time_seconds": execution_time,
        "execution_timestamps": timestamps,
        "property_values": dict(property_values),
        "testcase_identities": testcase_identities,
        "testcase_identity_sha256": testcase_digest,
        "testcase_files": sorted(
            {identity["file"] for identity in testcase_identities if "file" in identity}
        ),
        "testcase_classnames": sorted(
            {identity["classname"] for identity in testcase_identities}
        ),
    }


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
            raise CandidateValidationError(
                "independent pytest collection returned an invalid node ID"
            )
        module = parts[0][:-3].replace("/", ".")
        classname = ".".join((module, *parts[1:-1]))
        identities.append({"classname": classname, "name": parts[-1]})
    identities.sort(key=lambda item: (item["classname"], item["name"]))
    tokens = [_json_token(identity) for identity in identities]
    if len(tokens) != len(set(tokens)):
        raise CandidateValidationError(
            "collected pytest node IDs map to duplicate testcase identities"
        )
    return identities


def _normalize_collected_node_id(node_id: str) -> str:
    path, separator, test_name = node_id.partition("::")
    if not separator:
        raise CandidateValidationError(
            "independent pytest collection returned an invalid node ID"
        )
    normalized_path = path.replace("\\", "/")
    return f"{normalized_path}{separator}{test_name}"


def _collect_test_node_evidence(repository_root: Path) -> dict[str, Any]:
    environment = _clean_pytest_environment()
    try:
        completed = subprocess.run(
            _COLLECTION_COMMAND,
            cwd=repository_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError) as exc:
        raise CandidateValidationError(
            "independent pytest collection could not be completed"
        ) from exc
    if completed.returncode != 0:
        raise CandidateValidationError(
            "independent pytest collection failed with exit code "
            f"{completed.returncode}"
        )
    node_ids = [
        _normalize_collected_node_id(line.strip())
        for line in completed.stdout.splitlines()
        if line.strip().startswith("tests/") and "::" in line.strip()
    ]
    if not node_ids:
        raise CandidateValidationError("independent pytest collection found no tests")
    if len(node_ids) != len(set(node_ids)):
        raise CandidateValidationError(
            "independent pytest collection returned duplicate node IDs"
        )
    node_ids.sort()
    payload = json.dumps(
        node_ids,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "count": len(node_ids),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "test_files": sorted({node_id.split("::", 1)[0] for node_id in node_ids}),
        "node_ids": node_ids,
        "testcase_identities": _testcase_identities_from_node_ids(node_ids),
    }


def _required_version(document: Mapping[str, Any], field: str, label: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or _VERSION_PATTERN.fullmatch(value) is None:
        raise CandidateValidationError(f"{label} {field} is not a valid version")
    return value


def _parse_execution_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise CandidateValidationError(f"{label} must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CandidateValidationError(f"{label} is not ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CandidateValidationError(f"{label} must include a timezone")
    return parsed


def _validate_execution_timestamp(value: str) -> None:
    _parse_execution_timestamp(value, "JUnit timestamp")


def _required_sha256(document: Mapping[str, Any], field: str, label: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise CandidateValidationError(f"{label} {field} is not a SHA-256 digest")
    return value


def _inventory_sha256(entries: Sequence[Any]) -> str:
    return _sha256_text(
        json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )


def _raw_lf_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    if b"\xef\xbb\xbf" in raw:
        raise CandidateValidationError(f"inventory input contains a BOM: {path.name}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CandidateValidationError(
            f"inventory input is not UTF-8: {path.name}"
        ) from exc
    if b"\r" in raw:
        raise CandidateValidationError(f"inventory input is not LF-only: {path.name}")
    return raw


def _json_token(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_deterministic_rebuild(
    candidate: Path,
    *,
    repository_root: Path,
) -> None:
    """Compare the formal candidate with a fresh build from the locked inputs."""

    service_source = repository_root / "services" / "rag-ingestion" / "src"
    service_source_text = str(service_source)
    if service_source_text not in sys.path:
        sys.path.insert(0, service_source_text)
    try:
        from rag_ingestion.v2_artifacts import (  # noqa: PLC0415
            build_v2_artifacts,
            prepare_preflight,
        )
    except ImportError as exc:
        raise CandidateValidationError(
            "deterministic RagChunkV2 builder is unavailable"
        ) from exc

    with tempfile.TemporaryDirectory(prefix="rag-v2-validator-") as temporary:
        output_root = Path(temporary)
        try:
            prepare_preflight(repository_root, output_root)
            build_v2_artifacts(
                repository_root,
                output_root,
                require_test_evidence=False,
            )
        except (OSError, ValueError) as exc:
            raise CandidateValidationError(
                f"deterministic candidate rebuild failed: {exc}"
            ) from exc
        rebuilt = output_root / "candidates" / _ACTIVE_ARTIFACT_VERSION
        excluded = {
            "SHA256SUMS.txt",
            f"reports/test-evidence-{_ACTIVE_ARTIFACT_VERSION}.json",
            f"reports/pytest-rag-ingestion-{_ACTIVE_ARTIFACT_VERSION}.xml",
            f"reports/pytest-execution-receipt-{_ACTIVE_ARTIFACT_VERSION}.json",
        }
        candidate_paths = {
            path.relative_to(candidate).as_posix()
            for path in candidate.rglob("*")
            if path.is_file() and path.relative_to(candidate).as_posix() not in excluded
        }
        rebuilt_paths = {
            path.relative_to(rebuilt).as_posix()
            for path in rebuilt.rglob("*")
            if path.is_file() and path.relative_to(rebuilt).as_posix() not in excluded
        }
        if candidate_paths != rebuilt_paths:
            raise CandidateValidationError(
                "candidate deterministic path set differs from a fresh locked rebuild"
            )
        for relative_path in sorted(candidate_paths):
            if (candidate / relative_path).read_bytes() != (
                rebuilt / relative_path
            ).read_bytes():
                raise CandidateValidationError(
                    "candidate deterministic artifact differs from a fresh locked "
                    f"rebuild: {relative_path}"
                )


def _validate_checksums(candidate: Path) -> None:
    checksum_path = candidate / "SHA256SUMS.txt"
    declared: dict[str, str] = {}
    for line_number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        parts = line.split("  ", maxsplit=1)
        if len(parts) != 2 or _SHA256_PATTERN.fullmatch(parts[0]) is None:
            raise CandidateValidationError(f"invalid checksum line {line_number}")
        relative_path = parts[1]
        pure_path = PurePosixPath(relative_path)
        if (
            pure_path.is_absolute()
            or ".." in pure_path.parts
            or pure_path.as_posix() != relative_path
        ):
            raise CandidateValidationError(f"unsafe checksum path: {relative_path}")
        if relative_path in declared:
            raise CandidateValidationError(f"duplicate checksum path: {relative_path}")
        declared[relative_path] = parts[0]
    actual_paths = {
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if set(declared) != actual_paths:
        raise CandidateValidationError(
            "checksum inventory does not exactly match candidate files"
        )
    candidate_root = candidate.resolve()
    for relative_path, expected in declared.items():
        path = (candidate / Path(*PurePosixPath(relative_path).parts)).resolve()
        if candidate_root not in path.parents or not path.is_file():
            raise CandidateValidationError(
                f"checksum path escapes candidate: {relative_path}"
            )
        if _sha256_file(path) != expected:
            raise CandidateValidationError(f"checksum mismatch: {relative_path}")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(value, dict):
        raise CandidateValidationError(f"JSON document must be an object: {path.name}")
    return value


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        if not line.strip():
            raise CandidateValidationError(
                f"blank JSONL line: {path.name}:{line_number}"
            )
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
        except _DuplicateJsonKey as exc:
            raise CandidateValidationError(
                f"{exc} at {path.name}:{line_number}"
            ) from exc
        if not isinstance(value, dict):
            raise CandidateValidationError(
                f"JSONL row must be an object: {path.name}:{line_number}"
            )
        records.append((line_number, value))
    return records


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _unique_non_null(values: Iterable[Any]) -> list[Any]:
    return sorted({value for value in values if value is not None and value != ""})


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate a RagChunkV2 candidate without changing it or calling external services."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

REPO_ROOT = Path(__file__).resolve().parents[2]


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
        default=REPO_ROOT / "data" / "rag-v2" / "candidates" / "v001",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=REPO_ROOT
        / "contracts"
        / "schemas"
        / "rag"
        / "rag-chunk-v2.schema.json",
    )
    args = parser.parse_args(argv)

    try:
        summary = validate_candidate(args.candidate.resolve(), args.schema.resolve())
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


def validate_candidate(candidate: Path, schema_path: Path) -> dict[str, Any]:
    if not candidate.is_dir():
        raise CandidateValidationError("candidate directory does not exist")
    schema = _read_json(schema_path)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    chunk_files = sorted(
        (candidate / "chunks").glob("*.jsonl"), key=lambda path: path.name
    )
    if len(chunk_files) != 17:
        raise CandidateValidationError(
            f"expected 17 chunk files, found {len(chunk_files)}"
        )
    records: list[dict[str, Any]] = []
    failures: list[str] = []
    for path in chunk_files:
        for line_number, record in _read_jsonl(path):
            for error in validator.iter_errors(record):
                field = ".".join(str(item) for item in error.absolute_path) or "<root>"
                failures.append(f"{path.name}:{line_number}:{field}: {error.message}")
                if len(failures) >= 20:
                    break
            records.append(record)
            if len(failures) >= 20:
                break
        if len(failures) >= 20:
            break
    if failures:
        raise CandidateValidationError(
            "schema validation failed: " + " | ".join(failures)
        )
    if len(records) != 726:
        raise CandidateValidationError(f"expected 726 chunks, found {len(records)}")

    chunk_ids = [record["identity"]["chunk_id"] for record in records]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise CandidateValidationError("successor chunk IDs are not unique")
    if any(
        record["governance"]["production_approved"] is not False for record in records
    ):
        raise CandidateValidationError("candidate contains production-approved chunks")

    source_manifest = _read_json(candidate / "manifests" / "source-manifest-v001.json")
    chunk_manifest = _read_json(
        candidate / "manifests" / "chunk-file-manifest-v001.json"
    )
    allowlist = _read_json(
        candidate / "manifests" / "embedding-staging-allowlist-v003.json"
    )
    for name, document in (
        ("source manifest", source_manifest),
        ("allowlist", allowlist),
    ):
        if document.get("source_count") != 17 or document.get("chunk_count") != 726:
            raise CandidateValidationError(
                f"{name} count declaration does not match 17/726"
            )
    if (
        chunk_manifest.get("chunk_file_count") != 17
        or chunk_manifest.get("chunk_count") != 726
    ):
        raise CandidateValidationError(
            "chunk manifest count declaration does not match 17 files/726 chunks"
        )

    crosswalk = list(
        _read_jsonl(candidate / "crosswalk" / "chunk-id-crosswalk-v001.jsonl")
    )
    if len(crosswalk) != 726:
        raise CandidateValidationError("crosswalk does not contain 726 rows")
    if any(
        row["text_sha256_equal"] is not True
        or row["embedding_text_sha256_equal"] is not True
        or row["status_changed_automatically"] is not False
        for _, row in crosswalk
    ):
        raise CandidateValidationError(
            "crosswalk reports a content or automatic-status change"
        )
    _validate_checksums(candidate)

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
        "schema_version": schema.get("properties", {})
        .get("schema_version", {})
        .get("const"),
        "source_count": len({record["identity"]["source_id"] for record in records}),
        "chunk_count": len(records),
        "official_source_count": len(official_sources),
        "official_chunk_count": official_chunks,
        "research_source_count": 17 - len(official_sources),
        "research_chunk_count": 726 - official_chunks,
        "production_approved": False,
    }


def _validate_checksums(candidate: Path) -> None:
    checksum_path = candidate / "SHA256SUMS.txt"
    declared: dict[str, str] = {}
    for line_number, line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        parts = line.split("  ", maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise CandidateValidationError(f"invalid checksum line {line_number}")
        if parts[1] in declared:
            raise CandidateValidationError(f"duplicate checksum path: {parts[1]}")
        declared[parts[1]] = parts[0]
    actual_paths = {
        path.relative_to(candidate).as_posix()
        for path in candidate.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if set(declared) != actual_paths:
        raise CandidateValidationError(
            "checksum inventory does not exactly match candidate files"
        )
    for relative_path, expected in declared.items():
        if _sha256_file(candidate / relative_path) != expected:
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
        value = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

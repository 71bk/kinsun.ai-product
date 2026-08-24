"""Fail-closed RagChunkV2 projection into the isolated public RAG schema."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from psycopg import Connection
from psycopg.types.json import Jsonb

_VERSION_PATTERN = re.compile(r"^v[0-9]{3}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CHECKSUM_LINE_PATTERN = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")


class ProjectionImportError(ValueError):
    """Raised before commit when projection evidence is incomplete or inconsistent."""


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectionChunk:
    chunk_id: str
    source_id: str
    chunk_index: int
    artifact_version: str
    schema_version: str
    document_title: str
    section_title: str | None
    content_type: str
    language: str
    locale: str
    chunk_text: str
    embedding_text: str
    text_sha256: str
    embedding_text_sha256: str
    record_sha256: str
    source_version: str | None
    review_status: str
    current_status: str
    risk_level: str | None
    production_approved: bool
    retrieval_eligible: bool
    stop_normal_rag: bool | None
    requires_human_review: bool
    requires_official_assessment: bool | None
    requires_professional_assessment: bool | None
    allowed_audiences: tuple[str, ...]
    allowed_purposes: tuple[str, ...]
    citation: dict[str, Any]
    governance: dict[str, Any]
    provenance: dict[str, Any]
    retrieval_policy: dict[str, Any]

    def database_values(self, release_id: str) -> tuple[Any, ...]:
        return (
            release_id,
            self.chunk_id,
            self.source_id,
            self.chunk_index,
            self.artifact_version,
            self.schema_version,
            self.document_title,
            self.section_title,
            self.content_type,
            self.language,
            self.locale,
            self.chunk_text,
            self.embedding_text,
            self.text_sha256,
            self.embedding_text_sha256,
            self.record_sha256,
            self.source_version,
            self.review_status,
            self.current_status,
            self.risk_level,
            self.production_approved,
            self.retrieval_eligible,
            self.stop_normal_rag,
            self.requires_human_review,
            self.requires_official_assessment,
            self.requires_professional_assessment,
            list(self.allowed_audiences),
            list(self.allowed_purposes),
            Jsonb(self.citation),
            Jsonb(self.governance),
            Jsonb(self.provenance),
            Jsonb(self.retrieval_policy),
        )


@dataclass(frozen=True, slots=True)
class ProjectionBatch:
    release_id: str
    artifact_version: str
    candidate_sha256: str
    source_count: int
    chunk_count: int
    review_status: str
    human_source_review: str
    production_approved: bool
    chunks: tuple[ProjectionChunk, ...]


@dataclass(frozen=True, slots=True)
class ProjectionImportReceipt:
    schema_version: str
    run_id: str
    release_id: str
    candidate_sha256: str
    status: str
    source_count: int
    chunk_count: int
    inserted_chunk_count: int
    existing_chunk_count: int
    stored_embedding_count: int
    production_approved: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_projection_batch(
    candidate_dir: Path,
    schema_path: Path,
    *,
    expected_source_count: int | None = None,
    expected_chunk_count: int | None = None,
) -> ProjectionBatch:
    """Validate a complete immutable candidate before any database call."""

    candidate = candidate_dir.expanduser().resolve()
    schema_file = schema_path.expanduser().resolve()
    if not candidate.is_dir():
        raise ProjectionImportError("candidate directory does not exist")
    artifact_version = candidate.name
    if _VERSION_PATTERN.fullmatch(artifact_version) is None:
        raise ProjectionImportError("candidate directory must be a version such as v002")

    candidate_sha256 = _validate_checksum_inventory(candidate)
    schema = _read_json(schema_file)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    source_manifest = _read_json(
        candidate / "manifests" / f"source-manifest-{artifact_version}.json"
    )
    chunk_manifest = _read_json(
        candidate / "manifests" / f"chunk-file-manifest-{artifact_version}.json"
    )
    allowlist_paths = sorted((candidate / "manifests").glob("embedding-staging-allowlist-*.json"))
    if len(allowlist_paths) != 1:
        raise ProjectionImportError(
            "candidate must contain exactly one embedding staging allowlist"
        )
    allowlist = _read_json(allowlist_paths[0])

    _assert_equal(source_manifest, "artifact_version", artifact_version, "source manifest")
    _assert_equal(chunk_manifest, "artifact_version", artifact_version, "chunk manifest")
    _assert_equal(allowlist, "artifact_version", artifact_version, "allowlist")

    source_count = _positive_int(source_manifest, "source_count", "source manifest")
    chunk_count = _positive_int(source_manifest, "chunk_count", "source manifest")
    if expected_source_count is not None and source_count != expected_source_count:
        raise ProjectionImportError("candidate source count differs from the required count")
    if expected_chunk_count is not None and chunk_count != expected_chunk_count:
        raise ProjectionImportError("candidate chunk count differs from the required count")

    sources = _object_list(source_manifest, "sources", "source manifest")
    if len(sources) != source_count:
        raise ProjectionImportError("source manifest count does not match sources")
    source_ids = {_required_string(item, "source_id", "source manifest source") for item in sources}
    if len(source_ids) != source_count:
        raise ProjectionImportError("source manifest contains duplicate source IDs")

    manifest_files = _object_list(chunk_manifest, "files", "chunk manifest")
    if _positive_int(chunk_manifest, "chunk_file_count", "chunk manifest") != source_count:
        raise ProjectionImportError("chunk manifest file count does not match source count")
    if _positive_int(chunk_manifest, "chunk_count", "chunk manifest") != chunk_count:
        raise ProjectionImportError("chunk manifest count does not match source manifest")
    if len(manifest_files) != source_count:
        raise ProjectionImportError("chunk manifest file inventory is incomplete")

    records: list[ProjectionChunk] = []
    record_ids: set[str] = set()
    manifest_paths: set[str] = set()
    for file_entry in manifest_files:
        source_id = _required_string(file_entry, "source_id", "chunk manifest file")
        if source_id not in source_ids:
            raise ProjectionImportError("chunk manifest references an unknown source")
        relative_path = _safe_relative_path(
            _required_string(file_entry, "path", "chunk manifest file")
        )
        if relative_path in manifest_paths:
            raise ProjectionImportError("chunk manifest contains duplicate paths")
        manifest_paths.add(relative_path)
        file_path = (candidate / PurePosixPath(relative_path)).resolve()
        if file_path.parent != candidate / "chunks" or not file_path.is_file():
            raise ProjectionImportError("chunk file must be a direct child of the chunks directory")
        expected_file_sha256 = _required_sha256(file_entry, "sha256", "chunk manifest file")
        if _sha256_file(file_path) != expected_file_sha256:
            raise ProjectionImportError("chunk file hash does not match its manifest")

        file_records = _read_jsonl(file_path)
        if len(file_records) != _positive_int(file_entry, "chunk_count", "chunk manifest file"):
            raise ProjectionImportError("chunk file row count does not match its manifest")
        for line_number, record in file_records:
            errors = sorted(validator.iter_errors(record), key=lambda item: list(item.path))
            if errors:
                raise ProjectionImportError(
                    f"RagChunkV2 schema validation failed at {file_path.name}:{line_number}"
                )
            chunk = _projection_chunk(record, source_id, artifact_version)
            if chunk.chunk_id in record_ids:
                raise ProjectionImportError("candidate contains duplicate chunk IDs")
            record_ids.add(chunk.chunk_id)
            records.append(chunk)

    actual_paths = {
        path.relative_to(candidate).as_posix() for path in (candidate / "chunks").glob("*.jsonl")
    }
    if manifest_paths != actual_paths:
        raise ProjectionImportError("chunk manifest does not exactly cover the chunks directory")
    if len(records) != chunk_count:
        raise ProjectionImportError("candidate chunk count does not match loaded records")

    _validate_allowlist(allowlist, records, source_count, chunk_count)
    review_statuses = {chunk.review_status for chunk in records}
    if len(review_statuses) != 1:
        raise ProjectionImportError("candidate release has mixed review status")
    if any(chunk.production_approved for chunk in records):
        raise ProjectionImportError(
            "candidate projection cannot contain production-approved chunks"
        )

    human_source_review = _required_string(allowlist, "human_source_review", "allowlist")
    release_id = f"rag-v2-{artifact_version}-{candidate_sha256[:12]}"
    return ProjectionBatch(
        release_id=release_id,
        artifact_version=artifact_version,
        candidate_sha256=candidate_sha256,
        source_count=source_count,
        chunk_count=chunk_count,
        review_status=next(iter(review_statuses)),
        human_source_review=human_source_review,
        production_approved=False,
        chunks=tuple(records),
    )


def import_projection(connection: Connection, batch: ProjectionBatch) -> ProjectionImportReceipt:
    """Idempotently store one immutable candidate in a single transaction."""

    run_id = uuid.uuid4()
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rag_public.rag_release (
                    release_id, artifact_version, candidate_sha256, source_count,
                    chunk_count, release_status, review_status, human_source_review,
                    production_approved
                ) VALUES (%s, %s, %s, %s, %s, 'STAGING_CANDIDATE', %s, %s, false)
                ON CONFLICT (release_id) DO NOTHING
                """,
                (
                    batch.release_id,
                    batch.artifact_version,
                    batch.candidate_sha256,
                    batch.source_count,
                    batch.chunk_count,
                    batch.review_status,
                    batch.human_source_review,
                ),
            )
            cursor.execute(
                """
                SELECT artifact_version, candidate_sha256, source_count, chunk_count,
                       release_status, review_status, human_source_review,
                       production_approved
                FROM rag_public.rag_release
                WHERE release_id = %s
                """,
                (batch.release_id,),
            )
            release_row = cursor.fetchone()
            expected_release = (
                batch.artifact_version,
                batch.candidate_sha256,
                batch.source_count,
                batch.chunk_count,
                "STAGING_CANDIDATE",
                batch.review_status,
                batch.human_source_review,
                False,
            )
            if release_row != expected_release:
                raise ProjectionImportError("existing release differs from immutable candidate")

            cursor.execute(
                """
                INSERT INTO rag_public.ingestion_run (
                    run_id, release_id, operation, status, candidate_sha256,
                    expected_source_count, expected_chunk_count
                ) VALUES (%s, %s, 'PROJECT_CHUNKS', 'STARTED', %s, %s, %s)
                """,
                (
                    run_id,
                    batch.release_id,
                    batch.candidate_sha256,
                    batch.source_count,
                    batch.chunk_count,
                ),
            )
            cursor.execute(
                "SELECT count(*) FROM rag_public.chunk_projection WHERE release_id = %s",
                (batch.release_id,),
            )
            existing_count = int(cursor.fetchone()[0])

            cursor.executemany(
                """
                INSERT INTO rag_public.chunk_projection (
                    release_id, chunk_id, source_id, chunk_index, artifact_version,
                    schema_version, document_title, section_title, content_type,
                    language, locale, chunk_text, embedding_text, text_sha256,
                    embedding_text_sha256, record_sha256, source_version,
                    review_status, current_status, risk_level, production_approved,
                    retrieval_eligible, stop_normal_rag, requires_human_review,
                    requires_official_assessment, requires_professional_assessment,
                    allowed_audiences, allowed_purposes, citation, governance,
                    provenance, retrieval_policy
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (release_id, chunk_id) DO NOTHING
                """,
                [chunk.database_values(batch.release_id) for chunk in batch.chunks],
            )
            cursor.execute(
                """
                SELECT chunk_id, record_sha256
                FROM rag_public.chunk_projection
                WHERE release_id = %s
                """,
                (batch.release_id,),
            )
            stored_records = dict(cursor.fetchall())
            expected_records = {chunk.chunk_id: chunk.record_sha256 for chunk in batch.chunks}
            if stored_records != expected_records:
                raise ProjectionImportError("stored projection differs from immutable candidate")

            inserted_count = batch.chunk_count - existing_count
            if inserted_count < 0:
                raise ProjectionImportError("stored projection count exceeds candidate count")
            cursor.execute(
                """
                UPDATE rag_public.ingestion_run
                SET status = 'COMPLETED',
                    processed_chunk_count = %s,
                    inserted_chunk_count = %s,
                    existing_chunk_count = %s,
                    failure_count = 0,
                    completed_at = now()
                WHERE run_id = %s
                """,
                (batch.chunk_count, inserted_count, existing_count, run_id),
            )

    return ProjectionImportReceipt(
        schema_version="1.0.0",
        run_id=str(run_id),
        release_id=batch.release_id,
        candidate_sha256=batch.candidate_sha256,
        status="COMPLETED",
        source_count=batch.source_count,
        chunk_count=batch.chunk_count,
        inserted_chunk_count=inserted_count,
        existing_chunk_count=existing_count,
        stored_embedding_count=0,
        production_approved=False,
    )


def dry_run_receipt(batch: ProjectionBatch) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "VALIDATED_DRY_RUN",
        "release_id": batch.release_id,
        "candidate_sha256": batch.candidate_sha256,
        "source_count": batch.source_count,
        "chunk_count": batch.chunk_count,
        "stored_embedding_count": 0,
        "production_approved": batch.production_approved,
    }


def _projection_chunk(
    record: dict[str, Any], expected_source_id: str, artifact_version: str
) -> ProjectionChunk:
    identity = _required_object(record, "identity", "chunk")
    content = _required_object(record, "content", "chunk")
    citation = _required_object(record, "citation", "chunk")
    governance = _required_object(record, "governance", "chunk")
    provenance = _required_object(record, "provenance", "chunk")
    retrieval = _required_object(record, "retrieval_policy", "chunk")

    source_id = _required_string(identity, "source_id", "chunk identity")
    if source_id != expected_source_id:
        raise ProjectionImportError("chunk source differs from chunk manifest")
    if _required_string(record, "artifact_version", "chunk") != artifact_version:
        raise ProjectionImportError("chunk artifact version differs from candidate")

    chunk_text = _required_string(content, "text", "chunk content")
    embedding_text = _required_string(content, "embedding_text", "chunk content")
    text_sha256 = _required_sha256(content, "text_sha256", "chunk content")
    embedding_text_sha256 = _required_sha256(content, "embedding_text_sha256", "chunk content")
    if _sha256_text(chunk_text) != text_sha256:
        raise ProjectionImportError("chunk text hash mismatch")
    if _sha256_text(embedding_text) != embedding_text_sha256:
        raise ProjectionImportError("chunk embedding text hash mismatch")

    return ProjectionChunk(
        chunk_id=_required_string(identity, "chunk_id", "chunk identity"),
        source_id=source_id,
        chunk_index=_positive_int(identity, "chunk_index", "chunk identity"),
        artifact_version=artifact_version,
        schema_version=_required_string(record, "schema_version", "chunk"),
        document_title=_required_string(citation, "title", "chunk citation"),
        section_title=_optional_string(citation, "section", "chunk citation"),
        content_type=_required_string(content, "content_type", "chunk content"),
        language=_required_string(content, "language", "chunk content"),
        locale=_required_string(content, "locale", "chunk content"),
        chunk_text=chunk_text,
        embedding_text=embedding_text,
        text_sha256=text_sha256,
        embedding_text_sha256=embedding_text_sha256,
        record_sha256=_sha256_canonical_json(record),
        source_version=_optional_string(provenance, "source_version", "chunk provenance"),
        review_status=_required_string(governance, "review_status", "chunk governance"),
        current_status=_required_string(governance, "current_status", "chunk governance"),
        risk_level=_optional_string(retrieval, "risk_level", "chunk retrieval policy"),
        production_approved=_required_bool(governance, "production_approved", "chunk governance"),
        retrieval_eligible=_required_bool(
            retrieval, "retrieval_eligible", "chunk retrieval policy"
        ),
        stop_normal_rag=_optional_bool(retrieval, "stop_normal_rag", "chunk retrieval policy"),
        requires_human_review=_required_bool(
            retrieval, "requires_human_review", "chunk retrieval policy"
        ),
        requires_official_assessment=_optional_bool(
            retrieval, "requires_official_assessment", "chunk retrieval policy"
        ),
        requires_professional_assessment=_optional_bool(
            retrieval, "requires_professional_assessment", "chunk retrieval policy"
        ),
        allowed_audiences=_string_tuple(retrieval, "allowed_audiences", "chunk retrieval policy"),
        allowed_purposes=_string_tuple(retrieval, "allowed_purposes", "chunk retrieval policy"),
        citation=citation,
        governance=governance,
        provenance=provenance,
        retrieval_policy=retrieval,
    )


def _validate_allowlist(
    allowlist: dict[str, Any],
    chunks: list[ProjectionChunk],
    source_count: int,
    chunk_count: int,
) -> None:
    if _positive_int(allowlist, "source_count", "allowlist") != source_count:
        raise ProjectionImportError("allowlist source count mismatch")
    if _positive_int(allowlist, "chunk_count", "allowlist") != chunk_count:
        raise ProjectionImportError("allowlist chunk count mismatch")
    if _required_string(allowlist, "production_status", "allowlist") != "BLOCKED":
        raise ProjectionImportError("candidate allowlist must remain production blocked")
    if _required_string(allowlist, "embedding_status", "allowlist") != "NOT_STARTED":
        raise ProjectionImportError("candidate allowlist embedding status must be NOT_STARTED")

    entries = _object_list(allowlist, "entries", "allowlist")
    if len(entries) != chunk_count:
        raise ProjectionImportError("allowlist entry count mismatch")
    expected = {
        chunk.chunk_id: (chunk.text_sha256, chunk.embedding_text_sha256) for chunk in chunks
    }
    actual: dict[str, tuple[str, str]] = {}
    for entry in entries:
        chunk_id = _required_string(entry, "chunk_id", "allowlist entry")
        if chunk_id in actual:
            raise ProjectionImportError("allowlist contains duplicate chunk IDs")
        actual[chunk_id] = (
            _required_sha256(entry, "text_sha256", "allowlist entry"),
            _required_sha256(entry, "embedding_text_sha256", "allowlist entry"),
        )
    if actual != expected:
        raise ProjectionImportError("allowlist does not exactly attest candidate chunks")


def _validate_checksum_inventory(candidate: Path) -> str:
    checksum_path = candidate / "SHA256SUMS.txt"
    try:
        checksum_bytes = checksum_path.read_bytes()
        checksum_text = checksum_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectionImportError("candidate checksum inventory is unreadable") from exc
    if b"\r" in checksum_bytes or checksum_bytes.startswith(b"\xef\xbb\xbf"):
        raise ProjectionImportError("candidate checksum inventory must be UTF-8 LF-only")

    declared: dict[str, str] = {}
    for line_number, line in enumerate(checksum_text.splitlines(), start=1):
        match = _CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None:
            raise ProjectionImportError(f"invalid checksum inventory line {line_number}")
        digest, relative_path = match.groups()
        relative_path = _safe_relative_path(relative_path)
        if relative_path in declared:
            raise ProjectionImportError("checksum inventory contains duplicate paths")
        declared[relative_path] = digest

    actual_paths: set[str] = set()
    for path in candidate.rglob("*"):
        if path == checksum_path or not path.is_file():
            continue
        if path.is_symlink():
            raise ProjectionImportError("candidate checksum inventory cannot contain symlinks")
        resolved = path.resolve()
        if candidate not in resolved.parents:
            raise ProjectionImportError("candidate file resolves outside candidate directory")
        actual_paths.add(path.relative_to(candidate).as_posix())
    if set(declared) != actual_paths:
        raise ProjectionImportError("checksum inventory does not exactly cover candidate files")
    for relative_path, expected in declared.items():
        if _sha256_file(candidate / PurePosixPath(relative_path)) != expected:
            raise ProjectionImportError("candidate file does not match checksum inventory")
    return hashlib.sha256(checksum_bytes).hexdigest()


def _safe_relative_path(value: str) -> str:
    if "\\" in value:
        raise ProjectionImportError("candidate paths must use canonical POSIX separators")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ProjectionImportError("candidate path is unsafe")
    return path.as_posix()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKey) as exc:
        raise ProjectionImportError(f"cannot read required JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise ProjectionImportError(f"JSON artifact must be an object: {path.name}")
    return value


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records: list[tuple[int, dict[str, Any]]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    raise ProjectionImportError(f"blank JSONL line at {path.name}:{line_number}")
                value = json.loads(line, object_pairs_hook=_reject_keys)
                if not isinstance(value, dict):
                    raise ProjectionImportError(
                        f"JSONL record must be an object at {path.name}:{line_number}"
                    )
                records.append((line_number, value))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, _DuplicateJsonKey) as exc:
        raise ProjectionImportError(f"cannot read candidate JSONL: {path.name}") from exc
    return records


def _reject_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise _DuplicateJsonKey(key)
        value[key] = child
    return value


def _required_object(value: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise ProjectionImportError(f"{label}.{key} must be an object")
    return child


def _object_list(value: dict[str, Any], key: str, label: str) -> list[dict[str, Any]]:
    child = value.get(key)
    if not isinstance(child, list) or not all(isinstance(item, dict) for item in child):
        raise ProjectionImportError(f"{label}.{key} must be an object array")
    return child


def _required_string(value: dict[str, Any], key: str, label: str) -> str:
    child = value.get(key)
    if not isinstance(child, str) or not child:
        raise ProjectionImportError(f"{label}.{key} must be a non-empty string")
    return child


def _optional_string(value: dict[str, Any], key: str, label: str) -> str | None:
    child = value.get(key)
    if child is None:
        return None
    if not isinstance(child, str) or not child:
        raise ProjectionImportError(f"{label}.{key} must be null or a non-empty string")
    return child


def _required_bool(value: dict[str, Any], key: str, label: str) -> bool:
    child = value.get(key)
    if not isinstance(child, bool):
        raise ProjectionImportError(f"{label}.{key} must be boolean")
    return child


def _optional_bool(value: dict[str, Any], key: str, label: str) -> bool | None:
    child = value.get(key)
    if child is None:
        return None
    if not isinstance(child, bool):
        raise ProjectionImportError(f"{label}.{key} must be boolean or null")
    return child


def _positive_int(value: dict[str, Any], key: str, label: str) -> int:
    child = value.get(key)
    if not isinstance(child, int) or isinstance(child, bool) or child <= 0:
        raise ProjectionImportError(f"{label}.{key} must be a positive integer")
    return child


def _string_tuple(value: dict[str, Any], key: str, label: str) -> tuple[str, ...]:
    child = value.get(key)
    if not isinstance(child, list) or not all(isinstance(item, str) and item for item in child):
        raise ProjectionImportError(f"{label}.{key} must be a string array")
    if len(child) != len(set(child)):
        raise ProjectionImportError(f"{label}.{key} must not contain duplicates")
    return tuple(child)


def _required_sha256(value: dict[str, Any], key: str, label: str) -> str:
    child = _required_string(value, key, label)
    if _SHA256_PATTERN.fullmatch(child) is None:
        raise ProjectionImportError(f"{label}.{key} must be a lowercase SHA-256")
    return child


def _assert_equal(value: dict[str, Any], key: str, expected: Any, label: str) -> None:
    if value.get(key) != expected:
        raise ProjectionImportError(f"{label}.{key} differs from candidate")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_canonical_json(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(payload)

"""Fail-closed import of fixed-hash document embeddings into ``rag_public``."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from psycopg import Connection

from app.rag_projection_importer import ProjectionBatch

REQUIRED_EMBEDDING_DIMENSION = 1024
REQUIRED_DOCUMENT_TASK_TYPE = "RETRIEVAL_DOCUMENT"
EMBEDDING_ARTIFACT_SCHEMA_VERSION = "2.0.0"

_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class EmbeddingImportError(ValueError):
    """Raised before commit when embedding evidence is incomplete or inconsistent."""


class _DuplicateJsonKey(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EmbeddingProfileBinding:
    """One immutable provider/model/task identity for a complete RAG release."""

    provider: str
    model_id: str
    dimension: int
    document_task_type: str
    config_version: str

    def __post_init__(self) -> None:
        if not _IDENTIFIER_PATTERN.fullmatch(self.provider):
            raise EmbeddingImportError("embedding provider identifier is invalid")
        if not self.model_id.strip() or len(self.model_id) > 256:
            raise EmbeddingImportError("embedding model ID is invalid")
        if self.dimension != REQUIRED_EMBEDDING_DIMENSION:
            raise EmbeddingImportError(
                f"embedding dimension must be {REQUIRED_EMBEDDING_DIMENSION}"
            )
        if self.document_task_type != REQUIRED_DOCUMENT_TASK_TYPE:
            raise EmbeddingImportError(f"document task type must be {REQUIRED_DOCUMENT_TASK_TYPE}")
        if not self.config_version.strip() or len(self.config_version) > 80:
            raise EmbeddingImportError("embedding config version is invalid")

    @property
    def profile_id(self) -> str:
        canonical = json.dumps(
            {
                "config_version": self.config_version,
                "dimension": self.dimension,
                "document_task_type": self.document_task_type,
                "model_id": self.model_id,
                "provider": self.provider,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        return f"ep-{self.provider}-{digest[:24]}"

    def database_values(self) -> tuple[str, str, str, int, str, str]:
        return (
            self.profile_id,
            self.provider,
            self.model_id,
            self.dimension,
            self.document_task_type,
            self.config_version,
        )


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    chunk_id: str
    embedding_text_sha256: str
    vector: tuple[float, ...]
    vector_fingerprint: str

    def database_values(
        self,
        release_id: str,
        embedding_profile_id: str,
    ) -> tuple[str, str, str, str, str]:
        return (
            release_id,
            self.chunk_id,
            embedding_profile_id,
            self.embedding_text_sha256,
            _vector_literal(self.vector),
        )


@dataclass(frozen=True, slots=True)
class EmbeddingImportBatch:
    release_id: str
    artifact_version: str
    candidate_sha256: str
    allowlist_sha256: str
    artifact_sha256: str
    source_count: int
    chunk_count: int
    review_status: str
    human_source_review: str
    production_approved: bool
    profile: EmbeddingProfileBinding
    records: tuple[EmbeddingRecord, ...]


@dataclass(frozen=True, slots=True)
class EmbeddingImportReceipt:
    run_id: str
    release_id: str
    candidate_sha256: str
    artifact_sha256: str
    embedding_profile_id: str
    embedding_provider: str
    embedding_model_id: str
    embedding_dimension: int
    document_task_type: str
    config_version: str
    chunk_count: int
    inserted_embedding_count: int
    existing_embedding_count: int
    stored_embedding_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "status": "COMPLETED",
            "run_id": self.run_id,
            "release_id": self.release_id,
            "candidate_sha256": self.candidate_sha256,
            "embedding_artifact_sha256": self.artifact_sha256,
            "embedding_profile_id": self.embedding_profile_id,
            "embedding_provider": self.embedding_provider,
            "embedding_model_id": self.embedding_model_id,
            "embedding_dimension": self.embedding_dimension,
            "document_task_type": self.document_task_type,
            "config_version": self.config_version,
            "chunk_count": self.chunk_count,
            "inserted_embedding_count": self.inserted_embedding_count,
            "existing_embedding_count": self.existing_embedding_count,
            "stored_embedding_count": self.stored_embedding_count,
            "review_status": "needs_review",
            "retrieval_activation_status": "NOT_AUTHORIZED",
            "production_approved": False,
        }


def load_embedding_import_batch(
    artifact_path: Path,
    *,
    repository_root: Path,
    projection: ProjectionBatch,
    expected_artifact_sha256: str,
    expected_allowlist_sha256: str,
    expected_profile_id: str,
) -> EmbeddingImportBatch:
    """Validate an external embedding artifact against the immutable projection."""

    if projection.production_approved:
        raise EmbeddingImportError("staging embedding import cannot target Production")
    _require_sha256(expected_artifact_sha256, "expected embedding artifact SHA-256")
    _require_sha256(expected_allowlist_sha256, "authorized allowlist SHA-256")
    if not expected_profile_id.strip():
        raise EmbeddingImportError("expected embedding profile ID is required")

    artifact = artifact_path.expanduser().resolve()
    root = repository_root.expanduser().resolve()
    if artifact == root or root in artifact.parents:
        raise EmbeddingImportError("embedding artifact must remain outside the repository")
    try:
        payload = artifact.read_bytes()
    except OSError as exc:
        raise EmbeddingImportError(f"cannot read embedding artifact: {type(exc).__name__}") from exc
    actual_artifact_sha256 = hashlib.sha256(payload).hexdigest()
    if not hmac.compare_digest(actual_artifact_sha256, expected_artifact_sha256):
        raise EmbeddingImportError("embedding artifact SHA-256 attestation does not match")
    if payload.startswith(b"\xef\xbb\xbf") or b"\r" in payload:
        raise EmbeddingImportError("embedding artifact must be UTF-8, LF-only, and BOM-free")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EmbeddingImportError("embedding artifact is not valid UTF-8") from exc
    if not text.endswith("\n"):
        raise EmbeddingImportError("embedding artifact must end with one LF-delimited row")
    lines = text.splitlines()
    if not lines or any(not line for line in lines):
        raise EmbeddingImportError("embedding artifact contains a missing or blank row")

    manifest = _parse_json_row(lines[0], 1)
    manifest_keys = {
        "record_type",
        "schema_version",
        "allowlist_sha256",
        "embedding_provider",
        "embedding_model_id",
        "embedding_dimension",
        "document_task_type",
        "config_version",
        "chunk_count",
    }
    if set(manifest) != manifest_keys or manifest.get("record_type") != "manifest":
        raise EmbeddingImportError("embedding artifact manifest shape is invalid")
    if manifest.get("schema_version") != EMBEDDING_ARTIFACT_SCHEMA_VERSION:
        raise EmbeddingImportError("embedding artifact schema version is unsupported")
    if manifest.get("allowlist_sha256") != expected_allowlist_sha256:
        raise EmbeddingImportError("embedding artifact allowlist hash is not authorized")
    if manifest.get("chunk_count") != projection.chunk_count:
        raise EmbeddingImportError("embedding artifact chunk count differs from projection")

    profile = EmbeddingProfileBinding(
        provider=_required_string(manifest, "embedding_provider", "artifact manifest"),
        model_id=_required_string(manifest, "embedding_model_id", "artifact manifest"),
        dimension=_required_int(manifest, "embedding_dimension", "artifact manifest"),
        document_task_type=_required_string(manifest, "document_task_type", "artifact manifest"),
        config_version=_required_string(manifest, "config_version", "artifact manifest"),
    )
    if not hmac.compare_digest(profile.profile_id, expected_profile_id):
        raise EmbeddingImportError("embedding artifact profile is not attested")
    expected_chunks = {chunk.chunk_id: chunk for chunk in projection.chunks}
    records: dict[str, EmbeddingRecord] = {}
    row_keys = {
        "record_type",
        "chunk_id",
        "embedding_text_sha256",
        "allowlist_sha256",
        "embedding_model_id",
        "embedding_dimension",
        "embedding",
    }
    for line_number, line in enumerate(lines[1:], start=2):
        row = _parse_json_row(line, line_number)
        if set(row) != row_keys or row.get("record_type") != "embedding":
            raise EmbeddingImportError(f"embedding artifact row shape is invalid: {line_number}")
        if row.get("allowlist_sha256") != expected_allowlist_sha256:
            raise EmbeddingImportError(f"embedding artifact allowlist mismatch: {line_number}")
        if row.get("embedding_model_id") != profile.model_id:
            raise EmbeddingImportError(f"embedding artifact model mismatch: {line_number}")
        if row.get("embedding_dimension") != profile.dimension:
            raise EmbeddingImportError(f"embedding artifact dimension mismatch: {line_number}")
        chunk_id = row.get("chunk_id")
        if not isinstance(chunk_id, str) or chunk_id not in expected_chunks:
            raise EmbeddingImportError(
                f"embedding artifact has an unexpected chunk ID: {line_number}"
            )
        if chunk_id in records:
            raise EmbeddingImportError(f"embedding artifact has duplicate chunk ID: {chunk_id}")
        chunk = expected_chunks[chunk_id]
        embedding_text_sha256 = row.get("embedding_text_sha256")
        if embedding_text_sha256 != chunk.embedding_text_sha256:
            raise EmbeddingImportError(f"embedding artifact hash mismatch for {chunk_id}")
        vector = _validate_vector(row.get("embedding"), profile.dimension)
        records[chunk_id] = EmbeddingRecord(
            chunk_id=chunk_id,
            embedding_text_sha256=embedding_text_sha256,
            vector=vector,
            vector_fingerprint=_vector_fingerprint(vector),
        )

    missing = set(expected_chunks) - set(records)
    if missing:
        raise EmbeddingImportError(f"embedding artifact is missing {len(missing)} chunks")
    if len(records) != projection.chunk_count:
        raise EmbeddingImportError("embedding artifact contains an unexpected record count")
    ordered_records = tuple(records[chunk.chunk_id] for chunk in projection.chunks)
    return EmbeddingImportBatch(
        release_id=projection.release_id,
        artifact_version=projection.artifact_version,
        candidate_sha256=projection.candidate_sha256,
        allowlist_sha256=expected_allowlist_sha256,
        artifact_sha256=actual_artifact_sha256,
        source_count=projection.source_count,
        chunk_count=projection.chunk_count,
        review_status=projection.review_status,
        human_source_review=projection.human_source_review,
        production_approved=False,
        profile=profile,
        records=ordered_records,
    )


def import_embeddings(
    connection: Connection,
    batch: EmbeddingImportBatch,
) -> EmbeddingImportReceipt:
    """Bind one profile and idempotently insert every vector in one transaction."""

    if batch.production_approved:
        raise EmbeddingImportError("staging embedding import cannot target Production")
    run_id = uuid.uuid4()
    profile_id = batch.profile.profile_id
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT artifact_version, candidate_sha256, source_count, chunk_count,
                       release_status, review_status, human_source_review,
                       production_approved, embedding_profile_id
                FROM rag_public.rag_release
                WHERE release_id = %s
                FOR UPDATE
                """,
                (batch.release_id,),
            )
            release_row = cursor.fetchone()
            if release_row is None:
                raise EmbeddingImportError("staging projection must exist before embedding import")
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
            if release_row[:8] != expected_release:
                raise EmbeddingImportError("stored release differs from immutable candidate")
            existing_profile_id = release_row[8]
            if existing_profile_id not in {None, profile_id}:
                raise EmbeddingImportError("release is already bound to another embedding profile")

            cursor.execute(
                """
                INSERT INTO rag_public.embedding_profile (
                    embedding_profile_id, provider, model_id, dimension,
                    document_task_type, config_version
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (embedding_profile_id) DO NOTHING
                """,
                batch.profile.database_values(),
            )
            cursor.execute(
                """
                SELECT provider, model_id, dimension, document_task_type, config_version
                FROM rag_public.embedding_profile
                WHERE embedding_profile_id = %s
                """,
                (profile_id,),
            )
            stored_profile = cursor.fetchone()
            if stored_profile != batch.profile.database_values()[1:]:
                raise EmbeddingImportError("stored embedding profile differs from artifact")

            if existing_profile_id is None:
                cursor.execute(
                    """
                    UPDATE rag_public.rag_release
                    SET embedding_profile_id = %s
                    WHERE release_id = %s AND embedding_profile_id IS NULL
                    """,
                    (profile_id, batch.release_id),
                )
                if cursor.rowcount != 1:
                    raise EmbeddingImportError("embedding profile binding changed concurrently")

            cursor.execute(
                """
                SELECT chunk_id, embedding_text_sha256
                FROM rag_public.chunk_projection
                WHERE release_id = %s
                """,
                (batch.release_id,),
            )
            stored_projection = dict(cursor.fetchall())
            expected_projection = {
                record.chunk_id: record.embedding_text_sha256 for record in batch.records
            }
            if stored_projection != expected_projection:
                raise EmbeddingImportError("stored projection differs from embedding artifact")

            cursor.execute(
                """
                INSERT INTO rag_public.ingestion_run (
                    run_id, release_id, operation, status, candidate_sha256,
                    expected_source_count, expected_chunk_count
                ) VALUES (%s, %s, 'EMBED_DOCUMENTS', 'STARTED', %s, %s, %s)
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
                "SELECT count(*) FROM rag_public.chunk_embedding WHERE release_id = %s",
                (batch.release_id,),
            )
            existing_count = int(cursor.fetchone()[0])
            if existing_count > batch.chunk_count:
                raise EmbeddingImportError("stored embedding count exceeds candidate count")

            inserted_count = 0
            for record in batch.records:
                cursor.execute(
                    """
                    INSERT INTO rag_public.chunk_embedding (
                        release_id, chunk_id, embedding_profile_id,
                        embedding_text_sha256, embedding
                    ) VALUES (%s, %s, %s, %s, %s::public.vector)
                    ON CONFLICT (release_id, chunk_id) DO NOTHING
                    """,
                    record.database_values(batch.release_id, profile_id),
                )
                inserted_count += cursor.rowcount

            stored_count = _verify_stored_embeddings(cursor, batch)
            actual_existing_count = stored_count - inserted_count
            if actual_existing_count != existing_count:
                raise EmbeddingImportError("embedding import changed concurrently")
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

    return EmbeddingImportReceipt(
        run_id=str(run_id),
        release_id=batch.release_id,
        candidate_sha256=batch.candidate_sha256,
        artifact_sha256=batch.artifact_sha256,
        embedding_profile_id=profile_id,
        embedding_provider=batch.profile.provider,
        embedding_model_id=batch.profile.model_id,
        embedding_dimension=batch.profile.dimension,
        document_task_type=batch.profile.document_task_type,
        config_version=batch.profile.config_version,
        chunk_count=batch.chunk_count,
        inserted_embedding_count=inserted_count,
        existing_embedding_count=existing_count,
        stored_embedding_count=stored_count,
    )


def verify_embeddings(connection: Connection, batch: EmbeddingImportBatch) -> dict[str, Any]:
    """Read back the complete release and verify profile, hashes, and vector bytes."""

    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT candidate_sha256, source_count, chunk_count, release_status,
                       review_status, production_approved, embedding_profile_id
                FROM rag_public.rag_release
                WHERE release_id = %s
                """,
                (batch.release_id,),
            )
            release = cursor.fetchone()
            expected_release = (
                batch.candidate_sha256,
                batch.source_count,
                batch.chunk_count,
                "STAGING_CANDIDATE",
                batch.review_status,
                False,
                batch.profile.profile_id,
            )
            if release != expected_release:
                raise EmbeddingImportError("stored release/profile binding is invalid")
            stored_count = _verify_stored_embeddings(cursor, batch)
    return {
        "schema_version": "1.0.0",
        "status": "VERIFIED",
        "release_id": batch.release_id,
        "candidate_sha256": batch.candidate_sha256,
        "embedding_artifact_sha256": batch.artifact_sha256,
        "embedding_profile_id": batch.profile.profile_id,
        "embedding_provider": batch.profile.provider,
        "embedding_model_id": batch.profile.model_id,
        "embedding_dimension": batch.profile.dimension,
        "document_task_type": batch.profile.document_task_type,
        "stored_embedding_count": stored_count,
        "review_status": batch.review_status,
        "retrieval_activation_status": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def validated_artifact_receipt(batch: EmbeddingImportBatch) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "VALIDATED_DRY_RUN",
        "release_id": batch.release_id,
        "candidate_sha256": batch.candidate_sha256,
        "allowlist_sha256": batch.allowlist_sha256,
        "embedding_artifact_sha256": batch.artifact_sha256,
        "embedding_profile_id": batch.profile.profile_id,
        "embedding_provider": batch.profile.provider,
        "embedding_model_id": batch.profile.model_id,
        "embedding_dimension": batch.profile.dimension,
        "document_task_type": batch.profile.document_task_type,
        "chunk_count": batch.chunk_count,
        "database_access_performed": False,
        "retrieval_activation_status": "NOT_AUTHORIZED",
        "production_approved": False,
    }


def _verify_stored_embeddings(cursor: Any, batch: EmbeddingImportBatch) -> int:
    cursor.execute(
        """
        SELECT chunk_id, embedding_profile_id, embedding_text_sha256, embedding::text
        FROM rag_public.chunk_embedding
        WHERE release_id = %s
        """,
        (batch.release_id,),
    )
    stored_rows = cursor.fetchall()
    if len(stored_rows) != batch.chunk_count:
        raise EmbeddingImportError("stored embedding count differs from artifact")
    expected = {record.chunk_id: record for record in batch.records}
    seen: set[str] = set()
    for chunk_id, profile_id, embedding_text_sha256, vector_text in stored_rows:
        record = expected.get(chunk_id)
        if record is None or chunk_id in seen:
            raise EmbeddingImportError("stored embeddings contain an unexpected chunk ID")
        seen.add(chunk_id)
        if profile_id != batch.profile.profile_id:
            raise EmbeddingImportError("stored embeddings mix provider profiles")
        if embedding_text_sha256 != record.embedding_text_sha256:
            raise EmbeddingImportError(f"stored embedding hash mismatch for {chunk_id}")
        stored_vector = _parse_database_vector(vector_text, batch.profile.dimension)
        if _vector_fingerprint(stored_vector) != record.vector_fingerprint:
            raise EmbeddingImportError(f"stored embedding vector mismatch for {chunk_id}")
    if seen != set(expected):
        raise EmbeddingImportError("stored embeddings are incomplete")
    return len(stored_rows)


def _parse_json_row(line: str, line_number: int) -> dict[str, Any]:
    try:
        row = json.loads(line, object_pairs_hook=_reject_duplicate_keys)
    except _DuplicateJsonKey as exc:
        raise EmbeddingImportError(
            f"duplicate embedding artifact JSON key at line {line_number}: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EmbeddingImportError(
            f"invalid embedding artifact JSON at line {line_number}"
        ) from exc
    if not isinstance(row, dict):
        raise EmbeddingImportError(f"embedding artifact row must be an object: {line_number}")
    return row


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _validate_vector(value: Any, dimension: int) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != dimension:
        raise EmbeddingImportError(f"embedding vector must contain exactly {dimension} values")
    vector: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int | float):
            raise EmbeddingImportError("embedding vector values must be numeric")
        converted = float(item)
        if not math.isfinite(converted):
            raise EmbeddingImportError("embedding vector values must be finite")
        try:
            normalized = struct.unpack("!f", struct.pack("!f", converted))[0]
        except OverflowError as exc:
            raise EmbeddingImportError("embedding vector value exceeds float32 range") from exc
        vector.append(normalized)
    return tuple(vector)


def _parse_database_vector(value: Any, dimension: int) -> tuple[float, ...]:
    if not isinstance(value, str) or not value.startswith("[") or not value.endswith("]"):
        raise EmbeddingImportError("stored embedding vector encoding is invalid")
    try:
        values = [float(item) for item in value[1:-1].split(",")]
    except ValueError as exc:
        raise EmbeddingImportError("stored embedding vector contains invalid values") from exc
    return _validate_vector(values, dimension)


def _vector_literal(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".9g") for value in vector) + "]"


def _vector_fingerprint(vector: tuple[float, ...]) -> str:
    return hashlib.sha256(b"".join(struct.pack("!f", value) for value in vector)).hexdigest()


def _required_string(value: dict[str, Any], key: str, label: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise EmbeddingImportError(f"{label}.{key} must be a non-empty string")
    return item.strip()


def _required_int(value: dict[str, Any], key: str, label: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise EmbeddingImportError(f"{label}.{key} must be an integer")
    return item


def _require_sha256(value: str, label: str) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise EmbeddingImportError(f"{label} is invalid")

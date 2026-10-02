"""Load complete local knowledge vectors; no provider, settings or DB calls."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from app.rag_embedding_importer import (
    EmbeddingImportBatch,
    EmbeddingImportError,
    EmbeddingProfileBinding,
    EmbeddingRecord,
    _validate_vector,
    _vector_fingerprint,
)
from app.rag_knowledge_importer import _parse
from app.rag_projection_importer import ProjectionBatch, ProjectionImportError

_PROFILE_FIELDS = {
    "profile_id",
    "provider",
    "model_id",
    "model_version",
    "document_task_type",
    "dimension",
    "config_version",
}


def _read(path: Path) -> tuple[dict, str]:
    try:
        payload = path.read_bytes()
        document = _parse(payload.decode("utf-8"))
    except (OSError, UnicodeError, ProjectionImportError, RecursionError) as exc:
        raise EmbeddingImportError("INVALID_KNOWLEDGE_CACHE_JSON") from exc
    return document, hashlib.sha256(payload).hexdigest()


def _shape(value, fields: set[str], code: str) -> None:
    if not isinstance(value, dict) or set(value) != fields:
        raise EmbeddingImportError(code)


def _text_hash(text: str) -> str:
    try:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    except UnicodeError as exc:
        raise EmbeddingImportError("INVALID_KNOWLEDGE_UTF8_TEXT") from exc


def _profile(snapshot: dict) -> EmbeddingProfileBinding:
    _shape(snapshot, _PROFILE_FIELDS, "INVALID_KNOWLEDGE_PROFILE")
    for key in _PROFILE_FIELDS - {"dimension"}:
        value = snapshot[key]
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise EmbeddingImportError("INVALID_KNOWLEDGE_PROFILE")
    if type(snapshot["dimension"]) is not int:
        raise EmbeddingImportError("INVALID_KNOWLEDGE_PROFILE")
    binding = EmbeddingProfileBinding(
        provider=snapshot["provider"],
        model_id=snapshot["model_id"],
        dimension=snapshot["dimension"],
        document_task_type=snapshot["document_task_type"],
        config_version=snapshot["config_version"],
    )
    if not hmac.compare_digest(snapshot["profile_id"], binding.profile_id):
        raise EmbeddingImportError("KNOWLEDGE_PROFILE_ID_MISMATCH")
    # rag_public currently has no separate provider revision column. Do not
    # pretend a differently pinned revision is represented by its old profile.
    if snapshot["model_version"] != snapshot["model_id"]:
        raise EmbeddingImportError("UNSUPPORTED_KNOWLEDGE_MODEL_REVISION")
    return binding


def load_knowledge_embedding_batch(
    cache_path: Path,
    *,
    projection: ProjectionBatch,
    profile_registry_path: Path,
    expected_cache_sha256: str | None = None,
) -> EmbeddingImportBatch:
    """Bind exact cache coverage to one locally validated projection and profile.

    Existing legacy artifact loader and allowlist gates are not involved. The
    registry is the explicit local profile authority; cache snapshots must agree
    on every field, including model_version, not just the profile ID.
    """
    expected_release = f"knowledge-{projection.artifact_version}-{projection.candidate_sha256[:12]}"
    if (
        projection.production_approved
        or projection.artifact_version == "v004"
        or projection.release_id != expected_release
    ):
        raise EmbeddingImportError("KNOWLEDGE_STAGING_CANDIDATE_REQUIRED")
    registry, _ = _read(profile_registry_path)
    _shape(
        registry,
        {"schema_version", "target_profile_id", "profiles"},
        "INVALID_KNOWLEDGE_PROFILE_REGISTRY",
    )
    if registry["schema_version"] != "knowledge-embedding-profiles-v1":
        raise EmbeddingImportError("INVALID_KNOWLEDGE_PROFILE_REGISTRY")
    if not isinstance(registry["profiles"], list) or not registry["profiles"]:
        raise EmbeddingImportError("INVALID_KNOWLEDGE_PROFILE_REGISTRY")
    snapshots = {}
    for snapshot in registry["profiles"]:
        binding = _profile(snapshot)
        if binding.profile_id in snapshots:
            raise EmbeddingImportError("DUPLICATE_KNOWLEDGE_PROFILE")
        snapshots[binding.profile_id] = snapshot
    target_id = registry["target_profile_id"]
    if not isinstance(target_id, str) or target_id not in snapshots:
        raise EmbeddingImportError("UNKNOWN_KNOWLEDGE_PROFILE")
    profile = _profile(snapshots[target_id])
    cache, cache_sha256 = _read(cache_path)
    if expected_cache_sha256 is not None and (
        not isinstance(expected_cache_sha256, str)
        or len(expected_cache_sha256) != 64
        or any(char not in "0123456789abcdef" for char in expected_cache_sha256)
        or not hmac.compare_digest(expected_cache_sha256, cache_sha256)
    ):
        raise EmbeddingImportError("KNOWLEDGE_CACHE_HASH_MISMATCH")
    _shape(cache, {"schema_version", "profiles", "entries"}, "INVALID_KNOWLEDGE_CACHE")
    if cache["schema_version"] != "knowledge-embedding-cache-v1":
        raise EmbeddingImportError("INVALID_KNOWLEDGE_CACHE")
    if cache["profiles"] != [snapshots[target_id]]:
        raise EmbeddingImportError("KNOWLEDGE_CACHE_PROFILE_MISMATCH")
    if not isinstance(cache["entries"], list):
        raise EmbeddingImportError("INVALID_KNOWLEDGE_CACHE_ENTRIES")
    chunks = {}
    for chunk in projection.chunks:
        if (
            chunk.chunk_id in chunks
            or not isinstance(chunk.embedding_text, str)
            or not chunk.embedding_text.strip()
            or _text_hash(chunk.embedding_text) != chunk.embedding_text_sha256
        ):
            raise EmbeddingImportError("INVALID_KNOWLEDGE_PROJECTION_CONTENT")
        chunks[chunk.chunk_id] = chunk
    if not chunks or len(chunks) != projection.chunk_count:
        raise EmbeddingImportError("INVALID_KNOWLEDGE_PROJECTION_COVERAGE")
    expected_texts = {
        chunk.embedding_text_sha256: chunk.embedding_text for chunk in chunks.values()
    }
    vectors = {}
    for entry in cache["entries"]:
        _shape(
            entry,
            {"embedding_text", "embedding_text_sha256", "profile_id", "vector"},
            "INVALID_KNOWLEDGE_CACHE_ENTRY",
        )
        text, digest = entry["embedding_text"], entry["embedding_text_sha256"]
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(digest, str)
            or _text_hash(text) != digest
            or expected_texts.get(digest) != text
            or entry["profile_id"] != target_id
        ):
            raise EmbeddingImportError("KNOWLEDGE_CACHE_CONTENT_MISMATCH")
        if digest in vectors:
            raise EmbeddingImportError("DUPLICATE_KNOWLEDGE_CACHE_ENTRY")
        vector = _validate_vector(entry["vector"], profile.dimension)
        if not any(value != 0 for value in vector):
            raise EmbeddingImportError("ZERO_KNOWLEDGE_VECTOR")
        vectors[digest] = vector
    if set(vectors) != set(expected_texts):
        raise EmbeddingImportError("INCOMPLETE_KNOWLEDGE_CACHE")
    records = tuple(
        EmbeddingRecord(
            chunk_id=chunk.chunk_id,
            embedding_text_sha256=chunk.embedding_text_sha256,
            vector=vectors[chunk.embedding_text_sha256],
            vector_fingerprint=_vector_fingerprint(vectors[chunk.embedding_text_sha256]),
        )
        for chunk in projection.chunks
    )
    return EmbeddingImportBatch(
        release_id=projection.release_id,
        artifact_version=projection.artifact_version,
        candidate_sha256=projection.candidate_sha256,
        allowlist_sha256=None,
        artifact_sha256=cache_sha256,
        source_count=projection.source_count,
        chunk_count=projection.chunk_count,
        review_status=projection.review_status,
        human_source_review=projection.human_source_review,
        production_approved=False,
        profile=profile,
        records=records,
    )

"""Pure document embedding work planner; supplied evidence is never fetched.

The registry is caller-owned trusted configuration. ``config_version`` covers
all preprocessing (including title, normalization and truncation). A matching
metadata-only cache entry is potential reuse, never an available vector.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal


class EmbeddingPlanError(ValueError):
    """Invalid supplied evidence; messages contain no text or vectors."""


@dataclass(frozen=True, slots=True)
class EmbeddingPlanProfile:
    profile_id: str
    provider: str
    model_id: str
    model_version: str
    document_task_type: str
    dimension: int
    config_version: str


@dataclass(frozen=True, slots=True)
class SourceEmbeddingChunk:
    chunk_id: str
    embedding_text: str
    embedding_text_sha256: str


@dataclass(frozen=True, slots=True)
class CachedEmbedding:
    embedding_text: str
    embedding_text_sha256: str
    profile: EmbeddingPlanProfile
    vector: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingPlanRow:
    chunk_id: str
    embedding_text_sha256: str
    action: Literal["REUSE", "EMBED"]
    reason: str
    deduplicate_from: str | None = None
    cache_index: int | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingPlanSummary:
    total: int
    potential_reuse: int
    available_reuse: int
    unique_embeddings_required: int
    deduplicated: int


@dataclass(frozen=True, slots=True)
class EmbeddingPlan:
    profile: EmbeddingPlanProfile
    rows: tuple[EmbeddingPlanRow, ...]
    summary: EmbeddingPlanSummary


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise EmbeddingPlanError(code)


def _validate_profile(profile: EmbeddingPlanProfile) -> None:
    _require(isinstance(profile, EmbeddingPlanProfile), "INVALID_PROFILE")
    for value in (
        profile.profile_id,
        profile.provider,
        profile.model_id,
        profile.model_version,
        profile.document_task_type,
        profile.config_version,
    ):
        _require(isinstance(value, str) and bool(value.strip()), "INCOMPLETE_PROFILE")
    _require(type(profile.dimension) is int and profile.dimension > 0, "INVALID_DIMENSION")


def _validate_text(text: str, digest: str) -> None:
    _require(isinstance(text, str) and bool(text.strip()), "INVALID_EMBEDDING_TEXT")
    _require(
        isinstance(digest, str) and hashlib.sha256(text.encode("utf-8")).hexdigest() == digest,
        "EMBEDDING_TEXT_HASH_MISMATCH",
    )


def _validate_vector(vector: tuple[float, ...], dimension: int) -> tuple[float, ...]:
    _require(isinstance(vector, tuple | list), "INVALID_CACHE_VECTOR")
    _require(len(vector) == dimension, "CACHE_VECTOR_DIMENSION_MISMATCH")
    values = []
    for value in vector:
        _require(type(value) in (int, float), "INVALID_CACHE_VECTOR")
        try:
            number = float(value)
        except (OverflowError, ValueError) as exc:
            raise EmbeddingPlanError("INVALID_CACHE_VECTOR") from exc
        _require(math.isfinite(number), "NONFINITE_CACHE_VECTOR")
        values.append(number)
    _require(any(value != 0 for value in values), "ZERO_CACHE_VECTOR")
    return tuple(values)


def plan_embeddings(
    chunks: Sequence[SourceEmbeddingChunk],
    target_profile: EmbeddingPlanProfile,
    *,
    known_profiles: Sequence[EmbeddingPlanProfile],
    cache: Sequence[CachedEmbedding] = (),
) -> EmbeddingPlan:
    """Plan exact UTF-8 content reuse within one complete compatible profile.

    REUSE means a valid vector was supplied, not that a database contains it.
    EMBED rows sharing ``deduplicate_from`` need only one provider request;
    they do not claim already available reuse. Chunk IDs only label work.
    Every supplied cache row is validated, even when irrelevant to the target.
    """
    registry: dict[str, EmbeddingPlanProfile] = {}
    for profile in known_profiles:
        _validate_profile(profile)
        prior = registry.get(profile.profile_id)
        _require(prior is None or prior == profile, "PROFILE_ID_CONFLICT")
        registry[profile.profile_id] = profile

    def registered(profile: EmbeddingPlanProfile) -> None:
        _validate_profile(profile)
        _require(profile.profile_id in registry, "UNKNOWN_PROFILE")
        _require(registry[profile.profile_id] == profile, "PROFILE_METADATA_MISMATCH")

    registered(target_profile)
    # A hash collision must not collapse different exact source strings.
    texts: dict[str, str] = {}

    def remember(text: str, digest: str) -> None:
        _validate_text(text, digest)
        _require(digest not in texts or texts[digest] == text, "CONTENT_HASH_CONFLICT")
        texts[digest] = text

    cached: dict[tuple[EmbeddingPlanProfile, str], tuple[int, tuple[float, ...] | None]] = {}
    other_profile_hashes: set[str] = set()
    for index, entry in enumerate(cache):
        _require(isinstance(entry, CachedEmbedding), "INVALID_CACHE_ENTRY")
        registered(entry.profile)
        remember(entry.embedding_text, entry.embedding_text_sha256)
        vector = (
            None
            if entry.vector is None
            else _validate_vector(entry.vector, entry.profile.dimension)
        )
        key = (entry.profile, entry.embedding_text_sha256)
        previous = cached.get(key)
        if previous is not None:
            old_vector = previous[1]
            _require(
                old_vector is None or vector is None or old_vector == vector,
                "CACHE_VECTOR_CONFLICT",
            )
        if previous is None or (previous[1] is None and vector is not None):
            cached[key] = (index, vector)
        if entry.profile != target_profile:
            other_profile_hashes.add(entry.embedding_text_sha256)

    rows = []
    ids: set[str] = set()
    first_work: dict[str, str] = {}
    potential = available = deduplicated = 0
    for chunk in chunks:
        _require(isinstance(chunk, SourceEmbeddingChunk), "INVALID_SOURCE_CHUNK")
        _require(
            isinstance(chunk.chunk_id, str) and bool(chunk.chunk_id.strip()), "INVALID_CHUNK_ID"
        )
        _require(chunk.chunk_id not in ids, "DUPLICATE_CHUNK_ID")
        ids.add(chunk.chunk_id)
        remember(chunk.embedding_text, chunk.embedding_text_sha256)
        evidence = cached.get((target_profile, chunk.embedding_text_sha256))
        if evidence is not None:
            potential += 1
        if evidence is not None and evidence[1] is not None:
            available += 1
            rows.append(
                EmbeddingPlanRow(
                    chunk.chunk_id,
                    chunk.embedding_text_sha256,
                    "REUSE",
                    "AVAILABLE_CACHE_VECTOR",
                    cache_index=evidence[0],
                )
            )
            continue
        previous_chunk = first_work.get(chunk.embedding_text_sha256)
        if previous_chunk is not None:
            deduplicated += 1
        else:
            first_work[chunk.embedding_text_sha256] = chunk.chunk_id
        reason = "NO_CACHE_EVIDENCE"
        if evidence is not None:
            reason = "MATCHING_METADATA_WITHOUT_VECTOR"
        elif chunk.embedding_text_sha256 in other_profile_hashes:
            reason = "PROFILE_CHANGED"
        rows.append(
            EmbeddingPlanRow(
                chunk.chunk_id,
                chunk.embedding_text_sha256,
                "EMBED",
                reason,
                deduplicate_from=previous_chunk,
                cache_index=None if evidence is None else evidence[0],
            )
        )
    return EmbeddingPlan(
        target_profile,
        tuple(rows),
        EmbeddingPlanSummary(len(rows), potential, available, len(first_work), deduplicated),
    )

from dataclasses import replace
from hashlib import sha256

import pytest

from rag_ingestion.embedding_plan import (
    CachedEmbedding,
    EmbeddingPlanError,
    EmbeddingPlanProfile,
    SourceEmbeddingChunk,
    plan_embeddings,
)

PROFILE = EmbeddingPlanProfile(
    "synthetic-profile", "synthetic", "model-001", "001", "RETRIEVAL_DOCUMENT", 2, "1"
)


def chunk(identifier="new-id", text="exact text"):
    return SourceEmbeddingChunk(identifier, text, sha256(text.encode()).hexdigest())


def evidence(text="exact text", profile=PROFILE, vector=(0.25, 0.5)):
    return CachedEmbedding(text, sha256(text.encode()).hexdigest(), profile, vector)


def plan(chunks, cache=(), profile=PROFILE, known_profiles=(PROFILE,)):
    return plan_embeddings(chunks, profile, known_profiles=known_profiles, cache=cache)


def test_no_cache_claims_no_available_vectors_and_deduplicates_exact_content():
    result = plan([chunk("a"), chunk("b"), chunk("c", "exact text\n")])
    assert [row.action for row in result.rows] == ["EMBED"] * 3
    assert result.rows[1].deduplicate_from == "a"
    assert result.rows[2].deduplicate_from is None
    assert result.summary.total == 3
    assert result.summary.potential_reuse == result.summary.available_reuse == 0
    assert result.summary.unique_embeddings_required == 2
    assert result.summary.deduplicated == 1


def test_metadata_only_cache_is_potential_and_requires_embedding():
    result = plan([chunk("renamed")], [evidence(vector=None)])
    assert result.rows[0].action == "EMBED"
    assert result.rows[0].reason == "MATCHING_METADATA_WITHOUT_VECTOR"
    assert result.summary.potential_reuse == 1
    assert result.summary.available_reuse == 0
    assert result.summary.unique_embeddings_required == 1


def test_valid_vector_reuses_across_chunk_ids_and_metadata_changes():
    result = plan([chunk("new-id"), chunk("another-id")], [evidence()])
    assert [row.action for row in result.rows] == ["REUSE", "REUSE"]
    assert all(row.cache_index == 0 for row in result.rows)
    assert result.summary.potential_reuse == result.summary.available_reuse == 2
    assert result.summary.unique_embeddings_required == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "other"),
        ("model_id", "other"),
        ("model_version", "002"),
        ("document_task_type", "RETRIEVAL_QUERY"),
        ("dimension", 3),
        ("config_version", "2"),
        ("profile_id", "other-id"),
    ],
)
def test_each_profile_identity_change_requires_recompute(field, value):
    target = (
        replace(PROFILE, profile_id="new-profile", **{field: value})
        if field != ("profile_id")
        else replace(PROFILE, profile_id=value)
    )
    result = plan([chunk()], [evidence()], target, (PROFILE, target))
    assert result.rows[0].action == "EMBED"
    assert result.rows[0].reason == "PROFILE_CHANGED"
    assert result.summary.potential_reuse == 0


def test_same_chunk_id_with_changed_text_cannot_reuse():
    result = plan([chunk(text="changed")], [evidence()])
    assert result.rows[0].action == "EMBED"
    assert result.summary.available_reuse == 0


@pytest.mark.parametrize(
    "vector", [(1.0,), (True, 1), (float("nan"), 1), (float("inf"), 1), (0, 0), ("1", 2)]
)
def test_malformed_vector_rejects_even_for_irrelevant_content(vector):
    with pytest.raises(EmbeddingPlanError):
        plan([chunk()], [evidence(text="irrelevant", vector=vector)])


def test_invalid_vector_container_rejects():
    with pytest.raises(EmbeddingPlanError, match="INVALID_CACHE_VECTOR"):
        plan([chunk()], [evidence(vector="[1,2]")])


def test_conflicting_vectors_rejects_but_identical_evidence_deduplicates():
    with pytest.raises(EmbeddingPlanError, match="CACHE_VECTOR_CONFLICT"):
        plan([chunk()], [evidence(), evidence(vector=(0.5, 0.25))])
    assert plan([chunk()], [evidence(), evidence()]).rows[0].cache_index == 0
    assert plan([chunk()], [evidence(vector=None), evidence()]).rows[0].cache_index == 1


@pytest.mark.parametrize("where", ["source", "cache"])
def test_inconsistent_text_hash_rejects(where):
    source = chunk()
    cache = evidence()
    if where == "source":
        source = replace(source, embedding_text_sha256="a" * 64)
    else:
        cache = replace(cache, embedding_text_sha256="a" * 64)
    with pytest.raises(EmbeddingPlanError, match="EMBEDDING_TEXT_HASH_MISMATCH"):
        plan([source], [cache])


def test_unknown_profile_and_mismatched_metadata_reject():
    with pytest.raises(EmbeddingPlanError, match="UNKNOWN_PROFILE"):
        plan([chunk()], known_profiles=())
    with pytest.raises(EmbeddingPlanError, match="UNKNOWN_PROFILE"):
        plan([chunk()], [evidence(profile=replace(PROFILE, profile_id="unknown"))])
    with pytest.raises(EmbeddingPlanError, match="PROFILE_METADATA_MISMATCH"):
        plan([chunk()], [evidence(profile=replace(PROFILE, model_id="different"))])
    with pytest.raises(EmbeddingPlanError, match="PROFILE_ID_CONFLICT"):
        plan([chunk()], known_profiles=(PROFILE, replace(PROFILE, model_id="different")))


@pytest.mark.parametrize(
    "profile",
    [
        replace(PROFILE, model_version=""),
        replace(PROFILE, dimension=True),
        replace(PROFILE, dimension=0),
    ],
)
def test_incomplete_profile_rejects(profile):
    with pytest.raises(EmbeddingPlanError):
        plan([chunk()], profile=profile, known_profiles=(profile,))


def test_duplicate_source_ids_reject_and_empty_scope_costs_zero():
    with pytest.raises(EmbeddingPlanError, match="DUPLICATE_CHUNK_ID"):
        plan([chunk(), chunk()])
    assert plan([]).summary.unique_embeddings_required == 0


def test_planner_needs_no_network_or_environment(monkeypatch):
    import os
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("external access attempted")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(os, "getenv", forbidden)
    assert plan([chunk()], [evidence()]).summary.available_reuse == 1

"""Synthetic local vectors only; these tests never connect to providers or DB."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.rag_embedding_importer import EmbeddingImportError, EmbeddingProfileBinding
from app.rag_knowledge_embedding_importer import load_knowledge_embedding_batch
from app.rag_projection_importer import ProjectionBatch

ROOT = Path(__file__).resolve().parents[4]
PROFILE = {
    "provider": "google",
    "model_id": "synthetic-embedding",
    "dimension": 1024,
    "document_task_type": "RETRIEVAL_DOCUMENT",
    "config_version": "synthetic-v1",
}
BINDING = EmbeddingProfileBinding(**PROFILE)
SNAPSHOT = {**PROFILE, "profile_id": BINDING.profile_id, "model_version": PROFILE["model_id"]}
TEXT = "Synthetic UTF-8 source: \u9577\u7167\u670d\u52d9\n\u539f\u6587."
TEXT_HASH = hashlib.sha256(TEXT.encode("utf-8")).hexdigest()


@pytest.fixture
def projection():
    # Minimal synthetic ProjectionChunk surface consumed by this local loader.
    chunk = SimpleNamespace(
        chunk_id="synthetic-1", embedding_text=TEXT, embedding_text_sha256=TEXT_HASH
    )
    candidate_hash = "a" * 64
    return ProjectionBatch(
        release_id=f"knowledge-v008-{candidate_hash[:12]}",
        artifact_version="v008",
        candidate_sha256=candidate_hash,
        source_count=1,
        chunk_count=1,
        review_status="needs_review",
        human_source_review="not_completed",
        production_approved=False,
        chunks=(chunk,),
    )


@pytest.fixture
def documents():
    return (
        {
            "schema_version": "knowledge-embedding-profiles-v1",
            "target_profile_id": BINDING.profile_id,
            "profiles": [copy.deepcopy(SNAPSHOT)],
        },
        {
            "schema_version": "knowledge-embedding-cache-v1",
            "profiles": [copy.deepcopy(SNAPSHOT)],
            "entries": [
                {
                    "embedding_text": TEXT,
                    "embedding_text_sha256": TEXT_HASH,
                    "profile_id": BINDING.profile_id,
                    "vector": [0.25] * 1024,
                }
            ],
        },
    )


def save(tmp_path, documents):
    paths = (tmp_path / "profiles.json", tmp_path / "cache.json")
    for path, document in zip(paths, documents, strict=True):
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return paths


def load(paths, projection, **kwargs):
    registry, cache = paths
    return load_knowledge_embedding_batch(
        cache,
        projection=projection,
        profile_registry_path=registry,
        **kwargs,
    )


def test_complete_cache_builds_batch_without_legacy_allowlist(tmp_path, documents, projection):
    paths = save(tmp_path, documents)
    result = load(paths, projection)
    assert result.release_id == projection.release_id
    assert result.allowlist_sha256 is None
    assert result.production_approved is False
    assert result.review_status == "needs_review"
    assert result.profile == BINDING
    assert len(result.records) == projection.chunk_count
    assert result.records[0].embedding_text_sha256 == TEXT_HASH
    assert result.artifact_sha256 == hashlib.sha256(paths[1].read_bytes()).hexdigest()


@pytest.mark.parametrize("field", list(SNAPSHOT))
def test_cache_snapshot_requires_every_trusted_profile_field(
    tmp_path, documents, projection, field
):
    documents[1]["profiles"][0][field] = 512 if field == "dimension" else "different"
    with pytest.raises(EmbeddingImportError):
        load(save(tmp_path, documents), projection)


@pytest.mark.parametrize(
    "defect",
    [
        "text",
        "hash",
        "profile",
        "missing",
        "extra",
        "duplicate",
        "metadata_only",
        "dimension",
        "zero",
        "bool",
        "nan",
        "infinite",
        "overflow",
        "underflow",
    ],
)
def test_bad_cache_content_or_coverage_is_rejected(tmp_path, documents, projection, defect):
    cache = documents[1]
    entry = cache["entries"][0]
    if defect == "text":
        entry["embedding_text"] += " changed"
    elif defect == "hash":
        entry["embedding_text_sha256"] = "b" * 64
    elif defect == "profile":
        entry["profile_id"] = "other-profile"
    elif defect == "missing":
        cache["entries"] = []
    elif defect == "extra":
        extra = copy.deepcopy(entry)
        extra["embedding_text"] = "Unexpected source text."
        extra["embedding_text_sha256"] = hashlib.sha256(
            extra["embedding_text"].encode()
        ).hexdigest()
        cache["entries"].append(extra)
    elif defect == "duplicate":
        cache["entries"].append(copy.deepcopy(entry))
    elif defect == "metadata_only":
        del entry["vector"]
    elif defect == "dimension":
        entry["vector"] = [1.0]
    elif defect == "zero":
        entry["vector"] = [0.0] * 1024
    elif defect == "bool":
        entry["vector"][0] = True
    elif defect == "nan":
        entry["vector"][0] = float("nan")
    elif defect == "infinite":
        entry["vector"][0] = float("inf")
    elif defect == "overflow":
        entry["vector"][0] = 1e100
    else:
        entry["vector"] = [1e-100] * 1024
    with pytest.raises(EmbeddingImportError):
        load(save(tmp_path, documents), projection)


def test_expected_cache_bytes_are_bound(tmp_path, documents, projection):
    paths = save(tmp_path, documents)
    with pytest.raises(EmbeddingImportError, match="KNOWLEDGE_CACHE_HASH_MISMATCH"):
        load(paths, projection, expected_cache_sha256="0" * 64)
    result = load(
        paths, projection, expected_cache_sha256=hashlib.sha256(paths[1].read_bytes()).hexdigest()
    )
    assert len(result.records) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"production_approved": True},
        {"artifact_version": "v004"},
        {"release_id": "rag-v2-v004-existing"},
        {"chunk_count": 2},
    ],
)
def test_projection_must_be_matching_new_local_staging_candidate(
    tmp_path,
    documents,
    projection,
    changes,
):
    with pytest.raises(EmbeddingImportError):
        load(save(tmp_path, documents), replace(projection, **changes))


def test_duplicate_keys_and_nonfinite_json_cannot_hide_in_cache(tmp_path, documents, projection):
    paths = save(tmp_path, documents)
    for payload in ('{"profiles":[],"profiles":[]}', '{"unused":1e999}'):
        paths[1].write_text(payload, encoding="utf-8")
        with pytest.raises(EmbeddingImportError):
            load(paths, projection)


def test_distinct_provider_revision_is_not_claimed_by_legacy_db_profile(
    tmp_path,
    documents,
    projection,
):
    for document in documents:
        document["profiles"][0]["model_version"] = "immutable-revision-2"
    with pytest.raises(EmbeddingImportError, match="UNSUPPORTED_KNOWLEDGE_MODEL_REVISION"):
        load(save(tmp_path, documents), projection)


def test_import_cli_defaults_to_local_dry_run_without_write_flag(
    tmp_path,
    documents,
    projection,
    monkeypatch,
    capsys,
):
    spec = importlib.util.spec_from_file_location(
        "import_knowledge", ROOT / "scripts/rag/import_knowledge.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    paths = save(tmp_path, documents)
    monkeypatch.setattr(cli, "load_knowledge_batch", lambda path: projection)
    code = cli.main(["--cache", str(paths[1]), "--profile-registry", str(paths[0])])
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["mode"] == "DRY_RUN"
    assert report["database_write_performed"] is False
    assert report["activation_performed"] is False
    assert report["import_flag_available"] is False
    assert report["validated_vector_count"] == 1
    assert report["release_id"] == projection.release_id


def test_cli_failure_never_echoes_private_exception_content(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location(
        "import_knowledge", ROOT / "scripts/rag/import_knowledge.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    def fail(path):
        raise RuntimeError("SECRET credential and private local path")

    monkeypatch.setattr(cli, "load_knowledge_batch", fail)
    assert cli.main([]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report == {"status": "FAILED", "error_type": "RuntimeError"}

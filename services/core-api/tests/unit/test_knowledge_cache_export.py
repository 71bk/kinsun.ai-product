from __future__ import annotations

import copy
import hashlib

import pytest

from app.rag_embedding_importer import EmbeddingProfileBinding
from app.rag_knowledge_cache import (
    KnowledgeCacheError,
    export_knowledge_cache,
    validate_cache_snapshot,
)


def snapshot():
    binding = EmbeddingProfileBinding(
        provider="google",
        model_id="synthetic-model",
        dimension=1024,
        document_task_type="RETRIEVAL_DOCUMENT",
        config_version="1.0",
    )
    profile = {
        "profile_id": binding.profile_id,
        "provider": binding.provider,
        "model_id": binding.model_id,
        "dimension": 1024,
        "document_task_type": binding.document_task_type,
        "config_version": binding.config_version,
        "model_version": binding.model_id,
    }
    release = {
        **profile,
        "embedding_profile_id": binding.profile_id,
        "release_status": "STAGING_CANDIDATE",
        "production_approved": False,
        "chunk_count": 1,
        "source_count": 1,
        "candidate_sha256": "a" * 64,
    }
    text = "Synthetic public document."
    digest = hashlib.sha256(text.encode()).hexdigest()
    projections = [
        {
            "chunk_id": "c1",
            "source_id": "s1",
            "embedding_text": text,
            "embedding_text_sha256": digest,
        }
    ]
    embeddings = [
        {
            "chunk_id": "c1",
            "embedding_profile_id": binding.profile_id,
            "embedding_text_sha256": digest,
            "embedding": [0.1] * 1024,
        }
    ]
    receipts = [
        {
            "operation": op,
            "status": "COMPLETED",
            "candidate_sha256": "a" * 64,
            "failure_count": 0,
            "expected_source_count": 1,
            "expected_chunk_count": 1,
            "processed_chunk_count": 1,
            "inserted_chunk_count": 1,
            "existing_chunk_count": 0,
        }
        for op in ("PROJECT_CHUNKS", "EMBED_DOCUMENTS")
    ]
    return (
        release,
        projections,
        embeddings,
        receipts,
        {"schema_version": "knowledge-embedding-profiles-v1", "profiles": [profile]},
    )


def test_complete_snapshot_has_planner_cache_shape():
    cache = validate_cache_snapshot(*snapshot())
    assert set(cache) == {"schema_version", "profiles", "entries"}
    assert cache["schema_version"] == "knowledge-embedding-cache-v1"
    assert cache["profiles"][0]["model_version"] == cache["profiles"][0]["model_id"]
    assert len(cache["entries"]) == 1


@pytest.mark.parametrize(
    "change", ["missing", "hash", "zero", "nan", "dimension", "profile", "receipt", "revision"]
)
def test_incomplete_or_drifted_snapshot_is_rejected(change):
    release, projections, embeddings, receipts, registry = copy.deepcopy(snapshot())
    if change == "missing":
        embeddings.clear()
    elif change == "hash":
        projections[0]["embedding_text"] = "changed"
    elif change == "zero":
        embeddings[0]["embedding"] = [0] * 1024
    elif change == "nan":
        embeddings[0]["embedding"][0] = float("nan")
    elif change == "dimension":
        embeddings[0]["embedding"].pop()
    elif change == "profile":
        embeddings[0]["embedding_profile_id"] = "wrong"
    elif change == "receipt":
        receipts[0]["candidate_sha256"] = "b" * 64
    else:
        registry["profiles"][0]["model_version"] = "invented-provider-revision"
    with pytest.raises(KnowledgeCacheError):
        validate_cache_snapshot(release, projections, embeddings, receipts, registry)


def test_export_uses_one_readonly_repeatable_read_snapshot():
    release, projections, embeddings, receipts, registry = snapshot()

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, sql, params=None):
            statements.append(sql)
            self.sql = sql

        def fetchone(self):
            return release

        def fetchall(self):
            if "chunk_projection" in self.sql:
                return projections
            if "chunk_embedding" in self.sql:
                return embeddings
            return receipts

    class Transaction:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class Connection:
        def transaction(self):
            return Transaction()

        def cursor(self, **kwargs):
            return Cursor()

    statements = []
    assert export_knowledge_cache(Connection(), release_id="synthetic-release", registry=registry)[
        "entries"
    ]
    assert statements[0] == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
    assert statements[1] == "SET LOCAL statement_timeout = '15000ms'"
    assert all(s.strip().startswith("SELECT") for s in statements[2:])


@pytest.mark.parametrize("internal", [False, True])
def test_cli_error_summary_excludes_sensitive_exception_payload(
    tmp_path, monkeypatch, capsys, internal
):
    import importlib.util
    import json
    from pathlib import Path

    script = Path(__file__).resolve().parents[4] / "scripts/rag/export_knowledge_cache.py"
    spec = importlib.util.spec_from_file_location("knowledge_cache_export_cli_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    registry = tmp_path / "registry.json"
    registry.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(module, "dotenv_values", lambda path: {})
    monkeypatch.setenv("RAG_DATABASE_URL", "postgresql://synthetic:secret@db.example.test/test")

    class SyntheticDriverError(Exception):
        sqlstate = "42P01"

    def fail_connect(*args, **kwargs):
        if internal:
            raise KnowledgeCacheError("TEXT_HASH_DRIFT")
        raise SyntheticDriverError("secret endpoint and source payload must not escape")

    monkeypatch.setattr(module.psycopg, "connect", fail_connect)
    assert (
        module.main(
            [
                "--read-live",
                "--registry",
                str(registry),
                "--output",
                str(tmp_path / ".rag-work/cache.json"),
            ]
        )
        == 1
    )
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert "secret" not in output and "endpoint" not in output
    assert summary["error_code"] == ("TEXT_HASH_DRIFT" if internal else "CACHE_EXPORT_FAILED")
    assert summary["error_type"] == ("KnowledgeCacheError" if internal else "SyntheticDriverError")
    assert summary["sqlstate"] == (None if internal else "42P01")

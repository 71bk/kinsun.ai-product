"""Missing-only document generation with synthetic providers."""

import importlib.util
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest

from rag_ingestion.embedding_plan import (
    CachedEmbedding,
    EmbeddingPlanError,
    EmbeddingPlanProfile,
    SourceEmbeddingChunk,
)
from rag_ingestion.knowledge_embedding import KnowledgeEmbeddingError, complete_cache, load_dataset

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "embed_knowledge", ROOT / "scripts/rag/embed_knowledge.py"
)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)
PROFILE = EmbeddingPlanProfile(
    "synthetic",
    "google",
    "synthetic-model",
    "synthetic-model",
    "RETRIEVAL_DOCUMENT",
    1024,
    "1.0.0",
)


@pytest.mark.parametrize("violation", ["restricted", "foreign-host", "userinfo"])
def test_dataset_rejects_nonpublic_source_boundaries(tmp_path, violation):
    from rag_ingestion.knowledge_pipeline import _normalize

    corpus = ROOT / "data/rag-rechunk/successor/v001/corpus.jsonl"
    with corpus.open(encoding="utf-8") as handle:
        original = next(
            json.loads(line)
            for line in handle
            if json.loads(line)["provenance"]["is_official_source"]
        )
    row = _normalize(original)
    if violation == "restricted":
        row["provenance"]["data_classification"] = "restricted"
    elif violation == "foreign-host":
        row["source"]["url"] = "https://example.com/public"
    else:
        row["source"]["url"] = "https://user:secret@mohw.gov.tw/public"
    (tmp_path / "chunks.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    (tmp_path / "report.json").write_text(
        json.dumps(
            {
                "schema_version": "knowledge-dataset-v1",
                "status": "PASS",
                "production_approved": False,
                "activation_allowed": False,
                "summary": {"retained_count": 1},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(KnowledgeEmbeddingError, match="INVALID_KNOWLEDGE_CHUNK"):
        load_dataset(
            tmp_path, ROOT / "contracts/schemas/rag/knowledge-chunk-v1.schema.json", CLI._read_json
        )


def chunk(identifier, text):
    return SourceEmbeddingChunk(identifier, text, sha256(text.encode()).hexdigest())


class Provider:
    model_id = PROFILE.model_id
    dimension = 1024
    document_input_type = PROFILE.document_task_type

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def embed_documents(self, texts):
        self.calls.append(texts)
        if self.fail:
            raise RuntimeError("SECRET_PROVIDER_DETAIL")
        return SimpleNamespace(
            vectors=((0.2,) * 1024,) * len(texts), success_count=len(texts), failure_count=0
        )

    def close(self):
        pass


def setup_cli(monkeypatch):
    chunks = (chunk("one", "existing"), chunk("two", "missing"), chunk("three", "missing"))
    cache = (CachedEmbedding("existing", chunks[0].embedding_text_sha256, PROFILE, (0.1,) * 1024),)
    monkeypatch.setattr(CLI, "load_profiles", lambda *args: (PROFILE, (PROFILE,)))
    monkeypatch.setattr(CLI, "load_cache", lambda *args: cache)
    monkeypatch.setattr(CLI, "load_dataset", lambda *args: chunks)
    return chunks, cache


def test_only_unique_missing_text_is_sent_and_complete_cache_reuses_existing():
    chunks = (chunk("one", "existing"), chunk("two", "missing"), chunk("three", "missing"))
    cache = (CachedEmbedding("existing", chunks[0].embedding_text_sha256, PROFILE, (0.1,) * 1024),)
    provider = Provider()
    document = complete_cache(chunks, PROFILE, (PROFILE,), cache, provider, 32)
    assert provider.calls == [("missing",)]
    assert len(document["entries"]) == 2
    assert document["entries"][0]["vector"] == [0.1] * 1024


@pytest.mark.parametrize("change", ["profile", "hash", "zero"])
def test_invalid_cache_evidence_rejected_before_provider(change):
    item = chunk("one", "existing")
    profile = PROFILE
    digest, vector = item.embedding_text_sha256, (0.1,) * 1024
    if change == "profile":
        profile = EmbeddingPlanProfile(
            PROFILE.profile_id,
            "google",
            "old-model",
            "old-model",
            "RETRIEVAL_DOCUMENT",
            1024,
            "1.0.0",
        )
    elif change == "hash":
        digest = "0" * 64
    else:
        vector = (0.0,) * 1024
    provider = Provider()
    with pytest.raises(EmbeddingPlanError):
        complete_cache(
            (item,),
            PROFILE,
            (PROFILE,),
            (CachedEmbedding(item.embedding_text, digest, profile, vector),),
            provider,
            32,
        )
    assert provider.calls == []


def test_metadata_only_cache_requires_generation():
    item = chunk("one", "missing")
    provider = Provider()
    complete_cache(
        (item,),
        PROFILE,
        (PROFILE,),
        (CachedEmbedding(item.embedding_text, item.embedding_text_sha256, PROFILE),),
        provider,
        32,
    )
    assert provider.calls == [("missing",)]


def test_dry_run_never_loads_provider_or_writes(monkeypatch, capsys):
    setup_cli(monkeypatch)
    monkeypatch.setattr(CLI, "build_provider", lambda *args: pytest.fail("provider called"))
    assert CLI.main(["--dataset", "unused", "--cache", "unused"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["embedding"]["available_reuse"] == 1
    assert report["embedding"]["unique_embeddings_required"] == 1
    assert report["cache_written"] is False


def test_output_collision_rejected_before_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(CLI, "ROOT", tmp_path)
    output = tmp_path / ".rag-work/cache.json"
    output.parent.mkdir()
    output.write_text("existing")
    monkeypatch.setattr(CLI, "build_provider", lambda *args: pytest.fail("provider called"))
    assert (
        CLI.main(
            ["--dataset", "unused", "--cache", "unused", "--generate", "--output", str(output)]
        )
        == 1
    )
    assert output.read_text() == "existing"


def test_provider_failure_never_publishes_cache_or_secrets(tmp_path, monkeypatch, capsys):
    setup_cli(monkeypatch)
    monkeypatch.setattr(CLI, "ROOT", tmp_path)
    provider = Provider(fail=True)
    monkeypatch.setattr(CLI, "build_provider", lambda *args: provider)
    output = tmp_path / ".rag-work/cache.json"
    assert (
        CLI.main(
            ["--dataset", "unused", "--cache", "unused", "--generate", "--output", str(output)]
        )
        == 1
    )
    assert not output.exists()
    assert "SECRET_PROVIDER_DETAIL" not in capsys.readouterr().out

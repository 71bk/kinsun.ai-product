from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError

import agent_runtime.rag.postgres_backend as postgres_module
import agent_runtime.rag.retriever as retriever_module
from agent_runtime.rag.models import (
    HybridSearchPlan,
    PostgresSearchSettings,
    QueryEmbeddingSettings,
    RagRuntimeSettings,
)
from agent_runtime.rag.postgres_backend import (
    POSTGRES_CANDIDATE_LIMIT,
    POSTGRES_HYBRID_SEARCH_SQL,
    PostgresSearchBackend,
    PostgresSearchBackendError,
    build_postgres_engine,
)
from agent_runtime.rag.retriever import build_retriever
from agent_runtime.rag.search_backend import SearchBackend

SYNTHETIC_DATABASE_URL = (
    "postgresql+asyncpg://rag_reader:synthetic-password@db.example.test:5432/postgres"
    "?ssl=require"
)


def make_postgres_settings(**overrides: object) -> PostgresSearchSettings:
    values: dict[str, object] = {
        "database_url": SecretStr(SYNTHETIC_DATABASE_URL),
        "release_id": "rag-v2-v002-bab68588963b",
        "embedding_profile_id": "ep-google-00a12ec45096fa9d97d9e9b6",
        "statement_timeout_ms": 10_000,
        "pool_min_size": 1,
        "pool_max_size": 5,
        "mode": "staging",
    }
    values.update(overrides)
    return PostgresSearchSettings.model_validate(values)


def make_embedding_settings() -> QueryEmbeddingSettings:
    return QueryEmbeddingSettings(
        provider="google",
        model_id="gemini-embedding-001",
        dimension=1024,
    )


def make_plan(**overrides: object) -> HybridSearchPlan:
    values: dict[str, object] = {
        "query": "如何申請長照服務？",
        "query_vector": [0.01] * 1024,
        "profile": "natural_language",
        "top_k": 5,
        "audience": "elder",
        "purpose": "general_information",
        "governed_citations": True,
        "allow_needs_review": True,
        "bm25_weight": 0.4,
        "vector_weight": 0.6,
        "min_score": 0.7,
    }
    values.update(overrides)
    return HybridSearchPlan.model_validate(values)


class FakeMappingResult:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows

    def all(self) -> list[Mapping[str, object]]:
        return self._rows


class FakeExecuteResult:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeMappingResult:
        return FakeMappingResult(self._rows)


class FakeConnection:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self._rows = rows
        self.statement: object | None = None
        self.parameters: Mapping[str, object] | None = None

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(
        self,
        statement: object,
        parameters: Mapping[str, object],
    ) -> FakeExecuteResult:
        self.statement = statement
        self.parameters = parameters
        return FakeExecuteResult(self._rows)


class FakeEngine:
    def __init__(self, rows: list[Mapping[str, object]]) -> None:
        self.connection = FakeConnection(rows)
        self.disposed = False

    def connect(self) -> FakeConnection:
        return self.connection

    async def dispose(self) -> None:
        self.disposed = True


@pytest.mark.asyncio
async def test_postgres_backend_uses_one_parameterized_bounded_query() -> None:
    query = "測試' OR true; SELECT private_data"
    engine = FakeEngine([{"score": 0.91, "chunk_id": "synthetic-public-chunk"}])
    backend = PostgresSearchBackend(
        engine,  # type: ignore[arg-type]
        make_postgres_settings(),
        make_embedding_settings(),
    )

    hits = await backend.search(make_plan(query=query, allow_all_audiences=True))

    assert isinstance(backend, SearchBackend)
    assert len(hits) == 1
    assert hits[0].score == 0.91
    assert hits[0].source == {"chunk_id": "synthetic-public-chunk"}
    rendered_sql = str(engine.connection.statement)
    assert query not in rendered_sql
    assert ":query" in rendered_sql
    assert "rag_public.chunk_projection" in rendered_sql
    assert "eldercare_ai" not in rendered_sql
    assert engine.connection.parameters is not None
    assert engine.connection.parameters["query"] == query
    assert engine.connection.parameters["release_id"] == "rag-v2-v002-bab68588963b"
    assert engine.connection.parameters["embedding_profile_id"].startswith("ep-google-")
    assert engine.connection.parameters["candidate_limit"] == POSTGRES_CANDIDATE_LIMIT
    assert engine.connection.parameters["top_k"] == 5
    assert engine.connection.parameters["allow_all_audiences"] is True
    assert ":allow_all_audiences" in rendered_sql
    assert str(engine.connection.parameters["query_vector"]).startswith("[")


@pytest.mark.asyncio
async def test_postgres_backend_uses_fixed_runtime_policy_candidate_pool() -> None:
    candidate_ids = tuple(f"policy-chunk-{number:04d}" for number in range(554))
    engine = FakeEngine([])
    backend = PostgresSearchBackend(
        engine,  # type: ignore[arg-type]
        make_postgres_settings(),
        make_embedding_settings(),
    )

    await backend.search(
        make_plan(
            search_result_limit=50,
            policy_candidate_chunk_ids=candidate_ids,
        )
    )

    assert engine.connection.parameters is not None
    assert engine.connection.parameters["policy_overlay_enabled"] is True
    assert engine.connection.parameters["policy_candidate_chunk_ids"] == list(candidate_ids)
    assert engine.connection.parameters["top_k"] == 50
    assert "cardinality(CAST(:policy_candidate_chunk_ids AS text[])) = 554" in str(
        engine.connection.statement
    )


@pytest.mark.asyncio
async def test_postgres_backend_rejects_bad_vector_before_database_access() -> None:
    engine = FakeEngine([])
    backend = PostgresSearchBackend(
        engine,  # type: ignore[arg-type]
        make_postgres_settings(),
        make_embedding_settings(),
    )

    with pytest.raises(PostgresSearchBackendError, match="dimension mismatch"):
        await backend.search(make_plan(query_vector=[0.01] * 3))

    assert engine.connection.statement is None


@pytest.mark.asyncio
async def test_postgres_backend_rejects_malformed_batch_and_closes_pool() -> None:
    engine = FakeEngine([{"score": "not-a-number", "chunk_id": "bad"}])
    backend = PostgresSearchBackend(
        engine,  # type: ignore[arg-type]
        make_postgres_settings(),
        make_embedding_settings(),
    )

    with pytest.raises(PostgresSearchBackendError, match="malformed score"):
        await backend.search(make_plan())
    await backend.aclose()

    assert engine.disposed is True


def test_postgres_settings_are_staging_only_and_redact_database_url() -> None:
    settings = make_postgres_settings()

    assert SYNTHETIC_DATABASE_URL not in repr(settings)
    assert str(settings.database_url) == "**********"
    with pytest.raises(ValidationError):
        make_postgres_settings(mode="production")
    with pytest.raises(ValidationError, match="pool_max_size"):
        make_postgres_settings(pool_min_size=5, pool_max_size=1)


def test_postgres_runtime_loader_does_not_require_opensearch_configuration() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    config_dir = repository_root / "config" / "rag"

    settings = RagRuntimeSettings.from_config_files(
        embedding_config_path=config_dir / "embedding-google.yaml",
        index_config_path=config_dir / "does-not-exist.json",
        natural_profile_path=config_dir / "hybrid-natural-language.json",
        legal_profile_path=config_dir / "hybrid-legal.json",
        environ={
            "GEMINI_EMBEDDING_MODEL_ID": "gemini-embedding-001",
            "GEMINI_EMBEDDING_DIMENSION": "1024",
            "RAG_MODE": "staging",
            "RAG_SEARCH_BACKEND": "postgresql",
            "RAG_ALLOW_NEEDS_REVIEW_CITATIONS": "true",
            "RAG_STAGING_ALLOW_ALL_AUDIENCES": "true",
            "RAG_POSTGRES_RELEASE_ID": "rag-v2-v002-bab68588963b",
            "RAG_POSTGRES_EMBEDDING_PROFILE_ID": "ep-google-00a12ec45096fa9d97d9e9b6",
        },
        database_url=SecretStr(SYNTHETIC_DATABASE_URL),
    )

    assert settings.search_backend == "postgresql"
    assert settings.opensearch is None
    assert settings.postgres is not None
    assert settings.postgres.release_id == "rag-v2-v002-bab68588963b"
    assert settings.hybrid.index_alias is None
    assert settings.allow_needs_review_citations is True
    assert settings.allow_all_audiences is True


def test_postgres_engine_is_read_only_and_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    sentinel = SimpleNamespace()

    def fake_create_async_engine(url: str, **kwargs: object):
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(postgres_module, "create_async_engine", fake_create_async_engine)

    engine = build_postgres_engine(make_postgres_settings())

    assert engine is sentinel
    assert captured["pool_size"] == 1
    assert captured["max_overflow"] == 4
    assert captured["pool_pre_ping"] is True
    connect_args = captured["connect_args"]
    server_settings = connect_args["server_settings"]
    assert server_settings["default_transaction_read_only"] == "on"
    assert server_settings["statement_timeout"] == "10000"
    assert POSTGRES_HYBRID_SEARCH_SQL.count(":release_id") >= 1


def test_plain_postgresql_url_is_normalized_to_asyncpg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_create_async_engine(url: str, **kwargs: object):
        captured["url"] = url
        return SimpleNamespace()

    monkeypatch.setattr(postgres_module, "create_async_engine", fake_create_async_engine)
    settings = make_postgres_settings(
        database_url=SecretStr(
            "postgresql://rag_reader:synthetic-password@db.example.test/postgres"
        )
    )

    build_postgres_engine(settings)

    assert str(captured["url"]).startswith("postgresql+asyncpg://")


def test_retriever_factory_selects_postgres_without_building_opensearch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    config_dir = repository_root / "config" / "rag"
    settings = RagRuntimeSettings.from_config_files(
        embedding_config_path=config_dir / "embedding-google.yaml",
        index_config_path=config_dir / "unused.json",
        natural_profile_path=config_dir / "hybrid-natural-language.json",
        legal_profile_path=config_dir / "hybrid-legal.json",
        environ={
            "GEMINI_EMBEDDING_MODEL_ID": "gemini-embedding-001",
            "GEMINI_EMBEDDING_DIMENSION": "1024",
            "RAG_MODE": "staging",
            "RAG_SEARCH_BACKEND": "postgresql",
            "RAG_POSTGRES_RELEASE_ID": "rag-v2-v002-bab68588963b",
            "RAG_POSTGRES_EMBEDDING_PROFILE_ID": "ep-google-00a12ec45096fa9d97d9e9b6",
        },
        database_url=SecretStr(SYNTHETIC_DATABASE_URL),
    )
    sentinel_backend = SimpleNamespace(search=None, aclose=None)
    sentinel_embedder = SimpleNamespace(embed_query=None, aclose=None, dimension=1024)
    captured: dict[str, object] = {}

    def fake_postgres_builder(postgres_settings, embedding_settings):
        captured["postgres"] = postgres_settings
        captured["embedding"] = embedding_settings
        return sentinel_backend

    monkeypatch.setattr(
        retriever_module,
        "build_postgres_search_backend",
        fake_postgres_builder,
    )
    monkeypatch.setattr(
        retriever_module,
        "build_embedding_provider",
        lambda *args, **kwargs: sentinel_embedder,
    )
    monkeypatch.setattr(
        retriever_module,
        "build_opensearch_client",
        lambda *args, **kwargs: pytest.fail("OpenSearch must not be constructed"),
    )

    retriever = build_retriever(settings, google_api_key="synthetic-key")

    assert retriever._search_backend is sentinel_backend
    assert captured == {
        "postgres": settings.postgres,
        "embedding": settings.embedding,
    }

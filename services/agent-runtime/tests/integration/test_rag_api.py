from __future__ import annotations

from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

import agent_runtime.app as app_module
from agent_runtime.app import _resolve_config_path, create_app
from agent_runtime.rag.models import (
    RetrievalResponseV1,
    RetrievalResponseV2,
    RetrievalResultV1,
    RetrievalResultV2,
)
from agent_runtime.security.service_identity import (
    SERVICE_CREDENTIAL_HEADER,
    ServiceCredentialSigner,
    canonical_json_bytes,
)

RAG_PATH = "/api/v1/rag/retrievals"
RAG_V2_PATH = "/api/v2/rag/retrievals"
TEST_SIGNER = ServiceCredentialSigner(secret="synthetic-test-service-identity-secret-32-bytes")


def request_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "request_id": "req-rag-001",
        "query": "居家服務的申請條件是什麼？",
        "query_profile": "natural_language",
        "top_k": 5,
        "language": "zh-TW",
    }
    payload.update(overrides)
    return payload


def request_payload_v2(**overrides: object) -> dict[str, object]:
    return request_payload(schema_version="2.0.0", request_id="req-rag-v2-001", **overrides)


async def post(app, payload: dict[str, object], *, path: str = RAG_PATH):
    body = canonical_json_bytes(payload)
    correlation_id = "cid-rag-test"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            path,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Correlation-ID": correlation_id,
                SERVICE_CREDENTIAL_HEADER: TEST_SIGNER.sign(
                    method="POST",
                    path=path,
                    body=body,
                    correlation_id=correlation_id,
                ),
            },
        )


async def test_unconfigured_retrieval_returns_explicit_failed_fallback_without_guessing():
    app = create_app()
    query = "不可回填到錯誤訊息的測試查詢"
    response = await post(app, request_payload(query=query))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert body["data"]["status"] == "FAILED"
    assert body["data"]["results"] == []
    assert "不產生知識庫回答" in body["data"]["fallback_message"]
    assert query not in response.text


class StubRetriever:
    async def retrieve(self, payload) -> RetrievalResponseV1:
        results = [
            RetrievalResultV1(
                chunk_id=f"chunk-{number}",
                text=f"合成測試資料 {number}",
                score=1.0 - number / 10,
                document_name="長照測試文件",
                section="申請程序",
                page_start=number,
                page_end=number,
                source_url=f"https://example.test/source#{number}",
            )
            for number in range(1, 4)
        ]
        return RetrievalResponseV1(
            schema_version="1.0.0",
            request_id=payload.request_id,
            status="SUCCESS",
            fallback_message=None,
            results=results,
        )


class GovernedStubRetriever:
    async def retrieve_v2(self, payload) -> RetrievalResponseV2:
        results = []
        for number in range(1, 4):
            source_url = f"https://example.test/governed-source#{number}"
            results.append(
                RetrievalResultV2(
                    chunk_id=f"governed-chunk-{number}",
                    source_id="governed-source",
                    text=f"合成受治理測試資料 {number}",
                    score=1.0 - number / 10,
                    artifact_version="v002",
                    title="長照測試文件",
                    publisher=None,
                    section="申請程序",
                    physical_page_start=None,
                    physical_page_end=None,
                    printed_page_start=None,
                    printed_page_end=None,
                    source_locator=f"Web page section: synthetic-{number}",
                    direct_official_source_url=source_url,
                    official_source_page_url=source_url,
                    direct_source_url=source_url,
                    source_page_url=source_url,
                    is_official_source=True,
                    source_version=None,
                    source_version_date=None,
                    version_published_at=None,
                    source_page_updated_at=None,
                    published_at=None,
                    last_verified_at=None,
                    review_status="needs_review",
                    production_approved=False,
                )
            )
        return RetrievalResponseV2(
            schema_version="2.0.0",
            request_id=payload.request_id,
            status="SUCCESS",
            fallback_message=None,
            results=results,
        )


async def test_retrieval_success_returns_three_cited_chunks_in_standard_envelope():
    app = create_app()
    app.state.rag_retriever = StubRetriever()
    response = await post(app, request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "SUCCESS"
    assert len(body["data"]["results"]) == 3
    assert all(result["source_url"] for result in body["data"]["results"])
    assert body["meta"]["schema_version"] == "1.0"


async def test_v2_unconfigured_retrieval_fails_closed_without_query_echo():
    app = create_app()
    query = "synthetic-private-v2-query"
    response = await post(
        app,
        request_payload_v2(query=query),
        path=RAG_V2_PATH,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["schema_version"] == "2.0.0"
    assert body["data"]["status"] == "FAILED"
    assert body["data"]["results"] == []
    assert query not in response.text


async def test_v2_success_exposes_governed_citations_but_never_storage_urls():
    app = create_app()
    app.state.rag_retriever = GovernedStubRetriever()
    response = await post(app, request_payload_v2(), path=RAG_V2_PATH)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["status"] == "SUCCESS"
    assert len(body["data"]["results"]) == 3
    assert all(result["source_locator"] for result in body["data"]["results"])
    assert all(result["production_approved"] is False for result in body["data"]["results"])
    assert "storage_url" not in response.text


async def test_retrieval_request_rejects_wrong_top_k_and_extra_fields():
    app = create_app()
    response = await post(app, request_payload(top_k=10, caller_dsl={"match_all": {}}))

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["reason_code"] == "REQUEST_VALIDATION_FAILED"


async def test_v2_request_rejects_wrong_top_k_and_extra_fields_without_echo():
    app = create_app()
    query = "synthetic-rejected-v2-query"
    response = await post(
        app,
        request_payload_v2(query=query, top_k=10, caller_dsl={"match_all": {}}),
        path=RAG_V2_PATH,
    )

    assert response.status_code == 422
    assert response.json()["error"]["reason_code"] == "REQUEST_VALIDATION_FAILED"
    assert query not in response.text


def test_repo_relative_rag_config_paths_work_from_service_directory(
    monkeypatch,
) -> None:
    service_directory = _resolve_config_path("services/agent-runtime/pyproject.toml").parent
    monkeypatch.chdir(service_directory)

    resolved = _resolve_config_path("config/rag/embedding.yaml")

    assert resolved.is_file()
    assert resolved.name == "embedding.yaml"


def test_runtime_factory_passes_settings_provider_values_to_rag_loader(monkeypatch) -> None:
    class StubSettings:
        RAG_MODE = "staging"
        RAG_SEARCH_BACKEND = "opensearch"
        RAG_ALLOW_NEEDS_REVIEW_CITATIONS = True
        RAG_STAGING_ALLOW_ALL_AUDIENCES = True
        RAG_EMBEDDING_CONFIG_PATH = "config/rag/embedding.yaml"
        RAG_QUERY_EMBEDDING_CONFIG_PATH = "config/rag/embedding-google.yaml"
        RAG_OPENSEARCH_INDEX_CONFIG_PATH = "config/rag/opensearch-index-v1.json"
        RAG_HYBRID_NATURAL_CONFIG_PATH = "config/rag/hybrid-natural-language.json"
        RAG_HYBRID_LEGAL_CONFIG_PATH = "config/rag/hybrid-legal.json"
        RAG_DATABASE_URL = None
        RAG_POSTGRES_RELEASE_ID = None
        RAG_POSTGRES_EMBEDDING_PROFILE_ID = None
        RAG_POSTGRES_STATEMENT_TIMEOUT_MS = 10_000
        RAG_POSTGRES_POOL_MIN_SIZE = 1
        RAG_POSTGRES_POOL_MAX_SIZE = 5
        AWS_REGION = "configured-region"
        BEDROCK_EMBEDDING_MODEL_ID = "configured-model"
        BEDROCK_EMBEDDING_DIMENSION = 1024
        GEMINI_EMBEDDING_MODEL_ID = "configured-google-embedding"
        GEMINI_EMBEDDING_DIMENSION = 1024
        GEMINI_EMBEDDING_TIMEOUT_SECONDS = 30.0
        GEMINI_API_KEY = SecretStr("synthetic-google-embedding-key")
        OPENSEARCH_HOST = "https://search.example.test"
        OPENSEARCH_INDEX = "configured-staging-index"
        OPENSEARCH_ALIAS = "configured-staging-alias"

    captured = {}
    captured_builder = {}
    sentinel_settings = SimpleNamespace(
        embedding=SimpleNamespace(provider="google"),
        allow_all_audiences=True,
    )
    sentinel_retriever = object()

    def fake_loader(**kwargs):
        captured.update(kwargs)
        return sentinel_settings

    monkeypatch.setattr(app_module, "get_settings", lambda: StubSettings())
    monkeypatch.setattr(
        app_module.RagRuntimeSettings,
        "from_config_files",
        classmethod(lambda cls, **kwargs: fake_loader(**kwargs)),
    )

    def fake_builder(settings, **kwargs):
        captured_builder.update(kwargs)
        return sentinel_retriever if settings is sentinel_settings else None

    monkeypatch.setattr(app_module, "build_retriever", fake_builder)

    result = app_module.build_configured_rag_retriever()

    assert result is sentinel_retriever
    assert captured["embedding_config_path"].name == "embedding-google.yaml"
    assert captured["environ"] == {
        "AWS_REGION": "configured-region",
        "BEDROCK_EMBEDDING_MODEL_ID": "configured-model",
        "BEDROCK_EMBEDDING_DIMENSION": "1024",
        "GEMINI_EMBEDDING_MODEL_ID": "configured-google-embedding",
        "GEMINI_EMBEDDING_DIMENSION": "1024",
        "OPENSEARCH_HOST": "https://search.example.test",
        "OPENSEARCH_INDEX": "configured-staging-index",
        "OPENSEARCH_ALIAS": "configured-staging-alias",
        "RAG_MODE": "staging",
        "RAG_SEARCH_BACKEND": "opensearch",
        "RAG_ALLOW_NEEDS_REVIEW_CITATIONS": "True",
        "RAG_STAGING_ALLOW_ALL_AUDIENCES": "True",
        "RAG_POSTGRES_STATEMENT_TIMEOUT_MS": "10000",
        "RAG_POSTGRES_POOL_MIN_SIZE": "1",
        "RAG_POSTGRES_POOL_MAX_SIZE": "5",
    }
    assert "GEMINI_API_KEY" not in captured["environ"]
    assert captured["database_url"] is None
    assert captured_builder == {
        "google_api_key": "synthetic-google-embedding-key",
        "google_timeout_seconds": 30.0,
    }

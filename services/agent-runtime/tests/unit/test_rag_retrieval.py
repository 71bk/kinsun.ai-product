from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import agent_runtime.rag.client as opensearch_module
import agent_runtime.rag.query_embedder as embedder_module
from agent_runtime.rag.citations import render_citation, render_cited_chunk
from agent_runtime.rag.client import (
    OpenSearchClient,
    build_opensearch_search_body,
    build_opensearch_transport,
)
from agent_runtime.rag.fallback import NO_DATA_MESSAGE
from agent_runtime.rag.filters import is_normal_rag_eligible
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import (
    HybridProfileSettings,
    HybridSearchSettings,
    OpenSearchConnectionSettings,
    QueryEmbeddingSettings,
    RagRuntimeSettings,
    RetrievalRequestV1,
    RetrievalResultV1,
)
from agent_runtime.rag.query_embedder import (
    BedrockQueryEmbedder,
    GoogleQueryEmbedder,
    QueryEmbeddingError,
    build_bedrock_client,
    build_embedding_provider,
)
from agent_runtime.rag.retriever import Retriever, _above_relevance_floor
from agent_runtime.rag.search_backend import SearchBackend, SearchHit


def make_profile(name: str) -> HybridProfileSettings:
    weights = (0.65, 0.35) if name == "legal" else (0.4, 0.6)
    return HybridProfileSettings(
        profile=name,
        search_pipeline=f"pipeline-{name}",
        bm25_weight=weights[0],
        vector_weight=weights[1],
        vector_min_score=0.7,
        top_k=5,
        agent_chunk_min=3,
        agent_chunk_max=5,
    )


def make_search_settings() -> HybridSearchSettings:
    return HybridSearchSettings(
        index_alias="rag-staging-current",
        natural_language=make_profile("natural_language"),
        legal=make_profile("legal"),
    )


def make_request(
    profile: str = "natural_language",
    *,
    audience: str | None = "elder",
    purpose: str | None = "general_information",
) -> RetrievalRequestV1:
    return RetrievalRequestV1(
        schema_version="1.0.0",
        request_id=f"request-{profile}",
        query="長照服務如何申請？",
        query_profile=profile,
        top_k=5,
        audience=audience,
        purpose=purpose,
        language="zh-TW",
    )


def make_hit(
    chunk_id: str,
    *,
    stop_normal_rag: bool = False,
    current_status: str = "current",
    risk_level: str = "low",
    score: float = 1.0,
    allowed_audiences: list[str] | None = None,
    allowed_purposes: list[str] | None = None,
    requires_official_assessment: bool | None = False,
    requires_professional_assessment: bool | None = False,
    retrieval_eligible: bool | None = True,
    retrieval_block_reasons: list[str] | None = None,
) -> dict[str, object]:
    return {
        "_id": chunk_id,
        "_score": score,
        "_source": {
            "chunk_id": chunk_id,
            "text": f"合成測試內容 {chunk_id}",
            "document_name": "合成長照指引",
            "section": "申請流程",
            "page_start": 10,
            "page_end": 11,
            "source_url": "https://example.test/guide",
            "current_status": current_status,
            "stop_normal_rag": stop_normal_rag,
            "risk_level": risk_level,
            "requires_official_assessment": requires_official_assessment,
            "requires_professional_assessment": requires_professional_assessment,
            "allowed_audiences": allowed_audiences or ["elder"],
            "allowed_purposes": allowed_purposes or ["general_information"],
            "retrieval_eligible": retrieval_eligible,
            "retrieval_block_reasons": retrieval_block_reasons or [],
        },
    }


class FakeBedrockRuntime:
    def __init__(self, dimension: int = 1024) -> None:
        self.dimension = dimension
        self.kwargs: dict[str, object] | None = None

    def invoke_model(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        body = json.dumps({"embeddings": {"float": [[0.01] * self.dimension]}})
        return {"body": body.encode("utf-8")}


class FakeQueryEmbedder:
    dimension = 1024

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * 1024

    async def aclose(self) -> None:
        return None


class WrongDimensionQueryEmbedder:
    dimension = 1024

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * 3

    async def aclose(self) -> None:
        return None


class FakeGoogleEmbeddingModels:
    def __init__(self, dimension: int = 1024, *, error: Exception | None = None) -> None:
        self.dimension = dimension
        self.error = error
        self.kwargs: dict[str, object] | None = None

    async def embed_content(self, **kwargs: object):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.02] * self.dimension)])


class FakeGoogleClient:
    def __init__(self, models: FakeGoogleEmbeddingModels) -> None:
        self.aio = SimpleNamespace(models=models)


class FakeOpenSearchTransport:
    def __init__(self, hits: list[dict[str, object]]) -> None:
        self.hits = hits
        self.kwargs: dict[str, object] | None = None

    def search(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {"hits": {"hits": self.hits}}


class FakeAwsSession:
    def __init__(self, *, region_name: str) -> None:
        self.region_name = region_name

    def client(self, service_name: str, *, region_name: str):
        return {"service_name": service_name, "region_name": region_name}

    def get_credentials(self):
        return object()


def make_retriever(transport: FakeOpenSearchTransport) -> Retriever:
    return Retriever(
        embedding_provider=FakeQueryEmbedder(),
        search_backend=OpenSearchClient(transport, make_search_settings()),
        hybrid_search=HybridSearch(make_search_settings()),
    )


@pytest.mark.asyncio
async def test_bedrock_query_embedder_uses_search_query_and_configured_model() -> None:
    runtime = FakeBedrockRuntime()
    embedder = BedrockQueryEmbedder(
        runtime,
        QueryEmbeddingSettings(
            provider="bedrock",
            model_id="configured-embed-model",
            region="configured-region",
            dimension=1024,
        ),
    )

    vector = await embedder.embed_query("我要怎麼申請長照？")

    assert len(vector) == 1024
    assert runtime.kwargs is not None
    assert runtime.kwargs["modelId"] == "configured-embed-model"
    body = json.loads(runtime.kwargs["body"])
    assert body["input_type"] == "search_query"
    assert body["output_dimension"] == 1024
    assert body["embedding_types"] == ["float"]


@pytest.mark.asyncio
async def test_query_embedding_with_wrong_dimension_fails_closed() -> None:
    embedder = BedrockQueryEmbedder(
        FakeBedrockRuntime(dimension=3),
        QueryEmbeddingSettings(
            provider="bedrock", model_id="model", region="region", dimension=1024
        ),
    )

    with pytest.raises(QueryEmbeddingError, match="expected 1024 dimensions"):
        await embedder.embed_query("測試查詢")


@pytest.mark.asyncio
async def test_retriever_rejects_wrong_dimension_from_replaceable_embedder() -> None:
    retriever = Retriever(
        embedding_provider=WrongDimensionQueryEmbedder(),
        search_backend=OpenSearchClient(FakeOpenSearchTransport([]), make_search_settings()),
        hybrid_search=HybridSearch(make_search_settings()),
    )

    response = await retriever.retrieve(make_request())

    assert response.status == "FAILED"
    assert response.results == []
    assert "不產生" in response.fallback_message


def test_bedrock_factory_uses_configured_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedder_module.boto3, "Session", FakeAwsSession)
    settings = QueryEmbeddingSettings(
        provider="bedrock",
        model_id="configured-model",
        region="configured-region",
        dimension=1024,
    )

    client = build_bedrock_client(settings)

    assert client == {
        "service_name": "bedrock-runtime",
        "region_name": "configured-region",
    }


@pytest.mark.asyncio
async def test_google_query_embedder_uses_retrieval_task_and_configured_dimension() -> None:
    models = FakeGoogleEmbeddingModels()
    embedder = GoogleQueryEmbedder(
        api_key="synthetic-google-key",
        settings=QueryEmbeddingSettings(
            provider="google",
            model_id="gemini-embedding-001",
            dimension=1024,
        ),
        timeout_seconds=15.0,
        client=FakeGoogleClient(models),
    )

    vector = await embedder.embed_query("我要怎麼申請長照？")

    assert len(vector) == 1024
    assert models.kwargs is not None
    assert models.kwargs["model"] == "gemini-embedding-001"
    assert models.kwargs["contents"] == "我要怎麼申請長照？"
    config = models.kwargs["config"]
    assert config.task_type == "RETRIEVAL_QUERY"
    assert config.output_dimensionality == 1024


@pytest.mark.asyncio
async def test_google_embedding_failure_is_scrubbed_and_fails_closed() -> None:
    models = FakeGoogleEmbeddingModels(error=RuntimeError("sensitive upstream detail"))
    embedder = GoogleQueryEmbedder(
        api_key="synthetic-google-key",
        settings=QueryEmbeddingSettings(
            provider="google",
            model_id="gemini-embedding-001",
            dimension=1024,
        ),
        timeout_seconds=15.0,
        client=FakeGoogleClient(models),
    )

    with pytest.raises(QueryEmbeddingError, match="RuntimeError") as error:
        await embedder.embed_query("sensitive query")

    assert "sensitive upstream detail" not in str(error.value)
    assert "sensitive query" not in str(error.value)


def test_google_embedding_factory_requires_explicit_api_key() -> None:
    settings = QueryEmbeddingSettings(
        provider="google",
        model_id="gemini-embedding-001",
        dimension=1024,
    )

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        build_embedding_provider(settings)


def test_opensearch_factory_uses_sigv4_and_configured_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_signer(credentials: object, region: str, service: str):
        captured["signer"] = (credentials, region, service)
        return "signed-auth"

    def fake_opensearch(**kwargs: object):
        captured["client"] = kwargs
        return FakeOpenSearchTransport([])

    monkeypatch.setattr(opensearch_module.boto3, "Session", FakeAwsSession)
    monkeypatch.setattr(opensearch_module, "AWSV4SignerAuth", fake_signer)
    monkeypatch.setattr(opensearch_module, "OpenSearch", fake_opensearch)

    transport = build_opensearch_transport(
        OpenSearchConnectionSettings(
            host="https://collection-id.region.aoss.amazonaws.com",
            region="configured-region",
            index_name="configured-staging-index",
            index_alias="configured-staging-alias",
            mode="staging",
        )
    )

    assert isinstance(transport, FakeOpenSearchTransport)
    signer = captured["signer"]
    assert signer[1:] == ("configured-region", "aoss")
    client_kwargs = captured["client"]
    assert client_kwargs["hosts"] == [
        {"host": "collection-id.region.aoss.amazonaws.com", "port": 443}
    ]
    assert client_kwargs["http_auth"] == "signed-auth"


def test_runtime_settings_load_from_explicit_config_paths_and_environment() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    config_dir = repository_root / "config" / "rag"

    settings = RagRuntimeSettings.from_config_files(
        embedding_config_path=config_dir / "embedding.yaml",
        index_config_path=config_dir / "opensearch-index-v1.json",
        natural_profile_path=config_dir / "hybrid-natural-language.json",
        legal_profile_path=config_dir / "hybrid-legal.json",
        environ={
            "AWS_REGION": "configured-region",
            "BEDROCK_EMBEDDING_MODEL_ID": "configured-model",
            "BEDROCK_EMBEDDING_DIMENSION": "1024",
            "OPENSEARCH_HOST": "https://search.example.test",
            "OPENSEARCH_INDEX": "configured-staging-index",
            "OPENSEARCH_ALIAS": "configured-staging-alias",
            "RAG_MODE": "staging",
        },
    )

    assert settings.embedding.model_id == "configured-model"
    assert settings.embedding.provider == "bedrock"
    assert settings.embedding.region == "configured-region"
    assert settings.opensearch.host == "https://search.example.test"
    assert settings.opensearch.index_name == "configured-staging-index"
    assert settings.hybrid.index_alias == "configured-staging-alias"
    assert settings.hybrid.natural_language.bm25_weight == 0.4
    assert settings.hybrid.legal.vector_weight == 0.35
    assert settings.hybrid.natural_language.vector_min_score == 0.7


def test_runtime_settings_load_google_embedding_without_putting_key_in_config() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    config_dir = repository_root / "config" / "rag"

    settings = RagRuntimeSettings.from_config_files(
        embedding_config_path=config_dir / "embedding-google.yaml",
        index_config_path=config_dir / "opensearch-index-v1.json",
        natural_profile_path=config_dir / "hybrid-natural-language.json",
        legal_profile_path=config_dir / "hybrid-legal.json",
        environ={
            "AWS_REGION": "configured-region",
            "GEMINI_EMBEDDING_MODEL_ID": "configured-google-embedding",
            "GEMINI_EMBEDDING_DIMENSION": "1024",
            "OPENSEARCH_HOST": "https://search.example.test",
            "OPENSEARCH_INDEX": "configured-staging-index",
            "OPENSEARCH_ALIAS": "configured-staging-alias",
            "RAG_MODE": "staging",
        },
    )

    assert settings.embedding.provider == "google"
    assert settings.embedding.model_id == "configured-google-embedding"
    assert settings.embedding.region is None
    assert settings.embedding.dimension == 1024
    assert settings.opensearch.region == "configured-region"


def test_runtime_settings_reject_production_index_or_alias() -> None:
    with pytest.raises(ValueError, match="explicitly staging"):
        OpenSearchConnectionSettings(
            host="https://search.example.test",
            region="configured-region",
            index_name="knowledge-production-v1",
            index_alias="knowledge-staging",
            mode="staging",
        )


@pytest.mark.parametrize(
    ("profile", "pipeline", "weights"),
    [
        ("natural_language", "pipeline-natural_language", (0.4, 0.6)),
        ("legal", "pipeline-legal", (0.65, 0.35)),
    ],
)
def test_hybrid_plan_uses_configured_profile_and_mandatory_filters(
    profile: str, pipeline: str, weights: tuple[float, float]
) -> None:
    plan = HybridSearch(make_search_settings()).build(make_request(profile), [0.0] * 1024)

    assert make_search_settings().for_profile(plan.profile).search_pipeline == pipeline
    assert (plan.bm25_weight, plan.vector_weight) == weights
    assert plan.query == "長照服務如何申請？"
    assert plan.query_vector == [0.0] * 1024
    assert plan.top_k == 5
    assert plan.audience == "elder"
    assert plan.purpose == "general_information"
    assert plan.governed_citations is False
    assert plan.allow_needs_review is False
    assert plan.min_score == 0.7
    assert {"body", "index_alias", "search_pipeline"}.isdisjoint(plan.model_dump())
    body = build_opensearch_search_body(plan)
    assert body["size"] == 5
    hybrid = body["query"]["hybrid"]
    assert hybrid["queries"][0] == {"match": {"text": {"query": "長照服務如何申請？"}}}
    # Serverless rejects min_score/max_distance on a knn clause, so `k` is the
    # only accepted selector. Sending anything else makes every retrieval fail
    # with a 400 that Retriever hides behind the public fallback.
    assert hybrid["queries"][1]["knn"]["embedding"]["k"] == 5
    assert "min_score" not in hybrid["queries"][1]["knn"]["embedding"]
    assert "max_distance" not in hybrid["queries"][1]["knn"]["embedding"]
    expected_bool: dict[str, object] = {
        "must": [
            {"term": {"current_status": "current"}},
            {"term": {"stop_normal_rag": False}},
            {"term": {"retrieval_eligible": True}},
            {"terms": {"risk_level": ["low", "medium"]}},
            {"term": {"allowed_audiences": "elder"}},
            {"term": {"allowed_purposes": "general_information"}},
        ]
    }
    assert hybrid["filter"] == {"bool": expected_bool}


def test_high_risk_query_filter_is_applied_to_every_normal_rag_profile() -> None:
    natural_plan = HybridSearch(make_search_settings()).build(
        make_request("natural_language"), [0.0] * 1024
    )
    legal_plan = HybridSearch(make_search_settings()).build(make_request("legal"), [0.0] * 1024)

    natural_bool = build_opensearch_search_body(natural_plan)["query"]["hybrid"]["filter"]["bool"]
    legal_bool = build_opensearch_search_body(legal_plan)["query"]["hybrid"]["filter"]["bool"]
    expected = {"terms": {"risk_level": ["low", "medium"]}}
    assert expected in natural_bool["must"]
    assert expected in legal_bool["must"]


def test_runtime_policy_searches_fixed_candidates_before_response_gates() -> None:
    candidate_ids = tuple(f"policy-chunk-{number:04d}" for number in range(554))
    request = make_request(audience="elder", purpose="general_information")

    plan = HybridSearch(make_search_settings()).build_v2(
        request,
        [0.0] * 1024,
        allow_needs_review=True,
        policy_candidate_chunk_ids=candidate_ids,
    )
    body = build_opensearch_search_body(plan)

    assert plan.search_result_limit == 50
    assert body["size"] == 50
    assert body["query"]["hybrid"]["queries"][1]["knn"]["embedding"]["k"] == 50
    assert body["query"]["hybrid"]["filter"] == {
        "bool": {"must": [{"terms": {"chunk_id": list(candidate_ids)}}]}
    }


def test_hybrid_plan_adds_parameterized_metadata_scope_filters() -> None:
    request = make_request(audience="elder", purpose="care_guidance")

    plan = HybridSearch(make_search_settings()).build(request, [0.0] * 1024)

    must = build_opensearch_search_body(plan)["query"]["hybrid"]["filter"]["bool"]["must"]
    assert {"term": {"allowed_audiences": "elder"}} in must
    assert {"term": {"allowed_purposes": "care_guidance"}} in must


def test_staging_all_audience_override_keeps_explicit_scope_and_policy_metadata() -> None:
    request = make_request(audience="elder", purpose="general_information")
    plan = HybridSearch(make_search_settings()).build(
        request,
        [0.0] * 1024,
        allow_all_audiences=True,
    )

    must = build_opensearch_search_body(plan)["query"]["hybrid"]["filter"]["bool"]["must"]
    assert {"exists": {"field": "allowed_audiences"}} in must
    assert {"term": {"allowed_audiences": "elder"}} not in must

    source = make_hit(
        "staff-scoped-public-chunk",
        allowed_audiences=["care_professional"],
    )["_source"]
    assert (
        is_normal_rag_eligible(
            source,
            "natural_language",
            audience="elder",
            purpose="general_information",
            allow_all_audiences=True,
        )
        is True
    )
    assert (
        is_normal_rag_eligible(
            source,
            "natural_language",
            audience=None,
            purpose="general_information",
            allow_all_audiences=True,
        )
        is False
    )


def test_hybrid_plan_without_explicit_scope_matches_nothing() -> None:
    request = make_request(audience=None, purpose=None)

    plan = HybridSearch(make_search_settings()).build(request, [0.0] * 1024)

    must = build_opensearch_search_body(plan)["query"]["hybrid"]["filter"]["bool"]["must"]
    assert must.count({"match_none": {}}) == 2


@pytest.mark.asyncio
async def test_opensearch_uses_staging_alias_and_search_pipeline() -> None:
    transport = FakeOpenSearchTransport([])
    plan = HybridSearch(make_search_settings()).build(make_request(), [0.0] * 1024)
    backend = OpenSearchClient(transport, make_search_settings())

    assert isinstance(backend, SearchBackend)
    await backend.search(plan)

    assert transport.kwargs is not None
    assert transport.kwargs["index"] == "rag-staging-current"
    assert transport.kwargs["params"] == {"search_pipeline": "pipeline-natural_language"}


@pytest.mark.asyncio
async def test_no_results_returns_explicit_fallback_and_never_guesses() -> None:
    response = await make_retriever(FakeOpenSearchTransport([])).retrieve(make_request())

    assert response.status == "NO_DATA"
    assert response.results == []
    assert response.fallback_message == NO_DATA_MESSAGE
    assert "無法" in response.fallback_message


def test_unpaginated_source_cites_without_inventing_a_page_number() -> None:
    """An official web page has no page number; a placeholder would be a lie."""

    result = RetrievalResultV1(
        chunk_id="mohw_1966_apply_ltc_definition_001",
        text="長期照顧服務的申請方式說明。",
        score=0.9,
        document_name="申請長照服務",
        section="什麼是長期照顧服務",
        page_start=None,
        page_end=None,
        source_url="https://1966.gov.tw/LTC/cp-6533-70777-207.html",
    )

    citation = render_citation(result)

    assert "申請長照服務" in citation
    assert "什麼是長期照顧服務" in citation
    assert "p." not in citation
    assert "pp." not in citation


def test_half_populated_page_range_is_rejected() -> None:
    with pytest.raises(ValidationError, match="both be set or both be null"):
        RetrievalResultV1(
            chunk_id="chunk-1",
            text="內容",
            score=0.9,
            document_name="文件",
            section="章節",
            page_start=3,
            page_end=None,
            source_url="https://example.test/doc",
        )


@pytest.mark.asyncio
async def test_query_matching_nothing_is_no_data_rather_than_five_cited_chunks() -> None:
    """A knn clause with only `k` always returns k neighbours, however poor.

    Against the real staging collection a sentinel query that matched nothing
    still came back as SUCCESS with five cited chunks, because the configured
    floor was not being applied anywhere.
    """

    hits = [make_hit(f"weak-{number}", score=0.6) for number in range(5)]

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "NO_DATA"
    assert response.results == []
    assert response.fallback_message == NO_DATA_MESSAGE


@pytest.mark.asyncio
async def test_only_hits_at_or_above_the_configured_floor_reach_the_agent() -> None:
    hits = [make_hit(f"strong-{number}", score=0.75) for number in range(3)]
    hits.extend(make_hit(f"weak-{number}", score=0.69) for number in range(2))

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "SUCCESS"
    assert {result.chunk_id for result in response.results} == {
        "strong-0",
        "strong-1",
        "strong-2",
    }


def test_raw_vector_relevance_can_pass_when_chinese_lexical_score_is_weak() -> None:
    hits = [
        SearchHit(
            score=0.6,
            source={"chunk_id": f"semantic-{number}"},
            raw_vector_score=0.75 - number / 100,
        )
        for number in range(3)
    ]
    hits.extend(
        SearchHit(
            score=0.6,
            source={"chunk_id": f"weak-{number}"},
            raw_vector_score=0.69,
        )
        for number in range(2)
    )

    relevant = _above_relevance_floor(hits, 0.7)

    assert {hit.source["chunk_id"] for hit in relevant} == {
        "semantic-0",
        "semantic-1",
        "semantic-2",
    }


@pytest.mark.asyncio
async def test_stop_normal_rag_is_rejected_for_every_profile() -> None:
    for profile in ("natural_language", "legal"):
        hits = [make_hit(f"safe-{number}") for number in range(3)]
        hits.append(make_hit("blocked-stop", stop_normal_rag=True, score=99.0))
        response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(
            make_request(profile)
        )

        assert response.status == "SUCCESS"
        assert {result.chunk_id for result in response.results} == {
            "safe-0",
            "safe-1",
            "safe-2",
        }


@pytest.mark.asyncio
async def test_high_and_critical_risk_do_not_enter_natural_language_context() -> None:
    hits = [make_hit(f"safe-{number}") for number in range(3)]
    hits.extend(
        [
            make_hit("blocked-high", risk_level="high", score=99.0),
            make_hit("blocked-critical", risk_level="critical", score=100.0),
        ]
    )

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "SUCCESS"
    assert {result.chunk_id for result in response.results} == {
        "safe-0",
        "safe-1",
        "safe-2",
    }
    assert is_normal_rag_eligible(hits[3]["_source"], "legal") is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk_level", "unknown"),
        ("risk_level", "LOW"),
        ("allowed_audiences", []),
        ("allowed_purposes", []),
        ("requires_official_assessment", None),
        ("requires_professional_assessment", None),
        ("retrieval_eligible", False),
        ("retrieval_block_reasons", ["risk_level_not_allowed"]),
    ],
)
def test_incomplete_or_unknown_policy_metadata_is_rejected(field: str, value: object) -> None:
    source = make_hit("blocked")["_source"]
    source[field] = value

    assert (
        is_normal_rag_eligible(
            source,
            "natural_language",
            audience="elder",
            purpose="general_information",
        )
        is False
    )


@pytest.mark.parametrize(
    "field",
    [
        "risk_level",
        "allowed_audiences",
        "allowed_purposes",
        "requires_official_assessment",
        "requires_professional_assessment",
        "retrieval_eligible",
        "retrieval_block_reasons",
    ],
)
def test_missing_policy_metadata_is_rejected(field: str) -> None:
    source = make_hit("blocked")["_source"]
    source.pop(field)

    assert (
        is_normal_rag_eligible(
            source,
            "legal",
            audience="elder",
            purpose="general_information",
        )
        is False
    )


@pytest.mark.asyncio
async def test_metadata_scope_mismatch_is_rejected_after_search() -> None:
    hits = [make_hit(f"safe-{number}", allowed_purposes=["care_guidance"]) for number in range(3)]
    hits.extend(
        [
            make_hit("wrong-audience", allowed_audiences=["caregiver"]),
            make_hit("wrong-purpose", allowed_purposes=["research"]),
        ]
    )

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(
        make_request(audience="elder", purpose="care_guidance")
    )

    assert response.status == "SUCCESS"
    assert {result.chunk_id for result in response.results} == {
        "safe-0",
        "safe-1",
        "safe-2",
    }


@pytest.mark.asyncio
async def test_successful_retrieval_contains_complete_citations() -> None:
    hits = [make_hit(f"chunk-{number}", score=5.0 - number) for number in range(5)]

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "SUCCESS"
    assert len(response.results) == 5
    first = response.results[0]
    assert first.document_name == "合成長照指引"
    assert first.section == "申請流程"
    assert (first.page_start, first.page_end) == (10, 11)
    assert first.source_url == "https://example.test/guide"
    cited_context = render_cited_chunk(first)
    assert "來源：[合成長照指引，申請流程，pp. 10–11]" in cited_context
    assert first.source_url in cited_context


@pytest.mark.asyncio
async def test_incomplete_citation_metadata_is_not_exposed_to_agent() -> None:
    hits = [make_hit(f"safe-{number}") for number in range(2)]
    incomplete = make_hit("missing-source")
    incomplete["_source"]["source_url"] = None
    hits.append(incomplete)

    response = await make_retriever(FakeOpenSearchTransport(hits)).retrieve(make_request())

    assert response.status == "NO_DATA"
    assert response.results == []
    assert "不足三筆" in response.fallback_message

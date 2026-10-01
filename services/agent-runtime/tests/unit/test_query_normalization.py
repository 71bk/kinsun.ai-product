from unittest.mock import AsyncMock

import pytest

from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import HybridProfileSettings, HybridSearchSettings, RetrievalRequestV2
from agent_runtime.rag.query_normalization import normalize_legal_query
from agent_runtime.rag.retriever import Retriever


@pytest.fixture
def hybrid_search():
    profiles = {
        name: HybridProfileSettings(
            profile=name,
            search_pipeline=f"pipeline-{name}",
            bm25_weight=weight,
            vector_weight=1 - weight,
            vector_min_score=0.7,
            top_k=5,
            agent_chunk_min=3,
            agent_chunk_max=5,
        )
        for name, weight in (("natural_language", 0.4), ("legal", 0.65))
    }
    return HybridSearch(HybridSearchSettings(index_alias="rag-staging-current", **profiles))


@pytest.mark.parametrize(
    "given,expected",
    [
        ("長照法第二條", "長期照顧服務法第 2 條"),
        ("長照服務法第２條內容", "長期照顧服務法第 2 條內容"),
        ("第八條之一", "第 8-1 條"),
        ("第８－１條", "第 8-1 條"),
        ("第八之一條", "第 8-1 條"),
        ("第十三條以及第二十條", "第 13 條以及第 20 條"),
        ("第一百二十三條", "第 123 條"),
        ("第一百零一條", "第 101 條"),
        ("第一百零十條", "第一百零十條"),
        ("第百百條", "第百百條"),
        ("第2十條", "第2十條"),
        ("第0條", "第0條"),
        ("第8-1條之一", "第8-1條之一"),
        ("八成的人吃兩餐", "八成的人吃兩餐"),
    ],
)
def test_normalization_preserves_meaning(given, expected):
    assert normalize_legal_query(given) == expected
    assert normalize_legal_query(expected) == expected


def test_expansion_never_exceeds_query_bound():
    query = "長照法" * 666
    assert normalize_legal_query(query) == query


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "enabled,profile", [(False, "legal"), (True, "legal"), (True, "natural_language")]
)
async def test_normalization_is_opt_in_and_shared_by_both_search_legs(
    enabled, profile, hybrid_search
):
    embedding = AsyncMock()
    embedding.dimension = 1024
    embedding.embed_query.return_value = [0.01] * 1024
    backend = AsyncMock()
    backend.search.return_value = []
    retriever = Retriever(
        embedding_provider=embedding,
        search_backend=backend,
        hybrid_search=hybrid_search,
        normalize_legal_queries=enabled,
    )
    request = RetrievalRequestV2(
        schema_version="2.0.0",
        request_id="request-normalization-synthetic",
        query="長照法第二條",
        query_profile=profile,
        top_k=5,
        audience="elder",
        purpose="general_information",
        language="zh-TW",
    )
    response = await retriever.retrieve_v2(request)
    assert response.status == "NO_DATA"
    expected = "長期照顧服務法第 2 條" if enabled and profile == "legal" else request.query
    embedding.embed_query.assert_awaited_once_with(expected)
    assert backend.search.await_args.args[0].query == expected
    assert request.query == "長照法第二條"

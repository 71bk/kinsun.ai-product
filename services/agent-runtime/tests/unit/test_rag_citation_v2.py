from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_runtime.rag.citations import render_citation
from agent_runtime.rag.client import OpenSearchClient
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import (
    HybridProfileSettings,
    HybridSearchSettings,
    RetrievalRequestV2,
    RetrievalResultV2,
)
from agent_runtime.rag.retriever import Retriever


class FakeQueryEmbedder:
    dimension = 1024

    async def embed_query(self, text: str) -> list[float]:
        return [0.01] * self.dimension

    async def aclose(self) -> None:
        return None


class FakeOpenSearchTransport:
    def __init__(self, hits: list[dict[str, object]]) -> None:
        self.hits = hits
        self.kwargs: dict[str, object] | None = None

    def search(self, **kwargs: object) -> dict[str, object]:
        self.kwargs = kwargs
        return {"hits": {"hits": self.hits}}


def make_profile(name: str) -> HybridProfileSettings:
    return HybridProfileSettings(
        profile=name,
        search_pipeline=f"pipeline-{name}",
        bm25_weight=0.4,
        vector_weight=0.6,
        vector_min_score=0.7,
        top_k=5,
        agent_chunk_min=3,
        agent_chunk_max=5,
    )


def make_search_settings() -> HybridSearchSettings:
    return HybridSearchSettings(
        index_alias="rag-staging-current",
        natural_language=make_profile("natural_language"),
        legal=HybridProfileSettings(
            profile="legal",
            search_pipeline="pipeline-legal",
            bm25_weight=0.65,
            vector_weight=0.35,
            vector_min_score=0.7,
            top_k=5,
            agent_chunk_min=3,
            agent_chunk_max=5,
        ),
    )


def make_search() -> HybridSearch:
    return HybridSearch(make_search_settings())


def make_request() -> RetrievalRequestV2:
    return RetrievalRequestV2(
        schema_version="2.0.0",
        request_id="request-v2-synthetic",
        query="Synthetic governed retrieval query",
        query_profile="natural_language",
        top_k=5,
        audience="elder",
        purpose="general_information",
        language="en-US",
    )


def make_hit(
    chunk_id: str,
    *,
    review_status: str = "needs_review",
    production_approved: bool = False,
    source_locator: str | None = "PDF physical page 10, Synthetic section",
    score: float = 1.0,
) -> dict[str, object]:
    source_url = "https://example.test/official/guide"
    return {
        "_id": chunk_id,
        "_score": score,
        "_source": {
            "chunk_id": chunk_id,
            "source_id": "synthetic-governed-source",
            "text": f"Synthetic governed evidence {chunk_id}",
            "artifact_version": "v002",
            "title": "Synthetic Governed Guide",
            "publisher": None,
            "section": "Synthetic section",
            "physical_page_start": 10,
            "physical_page_end": 11,
            "printed_page_start": None,
            "printed_page_end": None,
            "source_locator": source_locator,
            "direct_official_source_url": f"{source_url}.pdf",
            "official_source_page_url": source_url,
            "direct_source_url": f"{source_url}.pdf",
            "source_page_url": source_url,
            "is_official_source": True,
            "source_version": "synthetic-v1",
            "source_version_date": None,
            "version_published_at": None,
            "source_page_updated_at": None,
            "published_at": None,
            "last_verified_at": None,
            "review_status": review_status,
            "production_approved": production_approved,
            "storage_url": "https://storage.example.test/private-object",
            "current_status": "current",
            "stop_normal_rag": False,
            "risk_level": "low",
            "requires_official_assessment": False,
            "requires_professional_assessment": False,
            "allowed_audiences": ["elder"],
            "allowed_purposes": ["general_information"],
            "retrieval_eligible": True,
            "retrieval_block_reasons": [],
        },
    }


def make_retriever(hits: list[dict[str, object]], *, allow_needs_review: bool = False) -> Retriever:
    return Retriever(
        embedding_provider=FakeQueryEmbedder(),
        search_backend=OpenSearchClient(FakeOpenSearchTransport(hits), make_search_settings()),
        hybrid_search=make_search(),
        allow_needs_review_citations=allow_needs_review,
    )


@pytest.mark.asyncio
async def test_needs_review_override_returns_complete_governed_citations() -> None:
    retriever = make_retriever(
        [make_hit(f"governed-{number}", score=5.0 - number) for number in range(5)],
        allow_needs_review=True,
    )

    response = await retriever.retrieve_v2(make_request())

    assert response.status == "SUCCESS"
    assert len(response.results) == 5
    assert all(result.review_status == "needs_review" for result in response.results)
    assert all(result.production_approved is False for result in response.results)
    assert all(result.source_locator for result in response.results)
    assert all("storage_url" not in result.model_dump() for result in response.results)
    plan = make_search().build_v2(
        make_request(),
        [0.01] * 1024,
        allow_needs_review=True,
    )
    transport = FakeOpenSearchTransport([])
    await OpenSearchClient(transport, make_search_settings()).search(plan)
    assert transport.kwargs is not None
    body = transport.kwargs["body"]
    assert isinstance(body, dict)
    serialized_filter = json.dumps(body["query"], sort_keys=True)
    assert "needs_review" in serialized_filter
    assert "production_approved" in serialized_filter


@pytest.mark.asyncio
async def test_needs_review_chunks_are_denied_without_explicit_override() -> None:
    response = await make_retriever(
        [make_hit(f"governed-{number}") for number in range(3)]
    ).retrieve_v2(make_request())

    assert response.status == "NO_DATA"
    assert response.results == []


@pytest.mark.asyncio
async def test_verified_production_chunks_do_not_require_staging_override() -> None:
    hits = [
        make_hit(
            f"verified-{number}",
            review_status="verified",
            production_approved=True,
        )
        for number in range(3)
    ]

    response = await make_retriever(hits).retrieve_v2(make_request())

    assert response.status == "SUCCESS"
    assert len(response.results) == 3


@pytest.mark.asyncio
async def test_one_incomplete_citation_fails_the_complete_batch_closed() -> None:
    hits = [make_hit("complete-1"), make_hit("complete-2")]
    hits.append(make_hit("missing-locator", source_locator=None))
    hits.extend([make_hit("complete-4"), make_hit("complete-5")])

    response = await make_retriever(hits, allow_needs_review=True).retrieve_v2(make_request())

    assert response.status == "NO_DATA"
    assert response.results == []


@pytest.mark.asyncio
async def test_non_official_source_cannot_claim_official_urls() -> None:
    response = await make_retriever(
        [make_hit(f"result-{number}") for number in range(3)],
        allow_needs_review=True,
    ).retrieve_v2(make_request())
    payload = response.results[0].model_dump()
    payload["is_official_source"] = False

    with pytest.raises(ValidationError, match="cannot populate official URL fields"):
        RetrievalResultV2.model_validate(payload)


def test_official_citation_uses_only_official_url_and_displays_publisher() -> None:
    payload = make_hit("official-citation")["_source"]
    assert isinstance(payload, dict)
    payload["publisher"] = "Synthetic Health Authority"
    payload["source_page_url"] = "https://research.example.test/not-official"
    result = RetrievalResultV2.model_validate(_public_result_payload(payload))

    rendered = render_citation(result)

    assert "Synthetic Health Authority｜Synthetic Governed Guide" in rendered
    assert "定位：PDF physical page 10, Synthetic section" in rendered
    assert "](https://example.test/official/guide)" in rendered
    assert "research.example.test" not in rendered


@pytest.mark.parametrize("value", ["https://", "ftp://example.test/file", "https://bad host.test"])
def test_citation_rejects_invalid_public_url(value: str) -> None:
    payload = make_hit("invalid-url")["_source"]
    assert isinstance(payload, dict)
    payload["official_source_page_url"] = value

    with pytest.raises(ValidationError, match="absolute HTTP\\(S\\) URI"):
        RetrievalResultV2.model_validate(_public_result_payload(payload))


def _public_result_payload(source: dict[str, object]) -> dict[str, object]:
    return {
        **{field: source[field] for field in RetrievalResultV2.model_fields if field != "score"},
        "score": 1.0,
    }


def test_all_unpaginated_v2_web_chunks_have_locator_and_official_public_url() -> None:
    repository_root = Path(__file__).resolve().parents[4]
    chunk_directory = repository_root / "data" / "rag-v2" / "candidates" / "v002" / "chunks"
    records = []
    for path in sorted(chunk_directory.glob("*.jsonl")):
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    unpaginated = [
        record
        for record in records
        if record["citation"]["physical_page_start"] is None
        and record["citation"]["physical_page_end"] is None
        and record["citation"]["printed_page_start"] is None
        and record["citation"]["printed_page_end"] is None
    ]

    assert len(unpaginated) == 16
    assert all(record["citation"]["source_locator"].strip() for record in unpaginated)
    assert all(
        record["citation"]["official_source_page_url"]
        or record["citation"]["direct_official_source_url"]
        for record in unpaginated
    )

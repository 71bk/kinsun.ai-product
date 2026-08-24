from __future__ import annotations

from pydantic import ValidationError

from agent_runtime.rag.client import build_opensearch_client
from agent_runtime.rag.fallback import (
    failed_response,
    failed_response_v2,
    no_data_response,
    no_data_response_v2,
)
from agent_runtime.rag.filters import is_normal_rag_eligible
from agent_runtime.rag.hybrid_search import HybridSearch
from agent_runtime.rag.models import (
    QueryProfile,
    RagRuntimeSettings,
    RetrievalRequestV1,
    RetrievalRequestV2,
    RetrievalResponseV1,
    RetrievalResponseV2,
    RetrievalResultV1,
    RetrievalResultV2,
)
from agent_runtime.rag.query_embedder import EmbeddingProvider, build_embedding_provider
from agent_runtime.rag.search_backend import SearchBackend, SearchHit


class Retriever:
    """Bounded staging retrieval flow with fail-closed source handling."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        search_backend: SearchBackend,
        hybrid_search: HybridSearch,
        allow_needs_review_citations: bool = False,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._search_backend = search_backend
        self._hybrid_search = hybrid_search
        self._allow_needs_review_citations = allow_needs_review_citations

    async def aclose(self) -> None:
        await self._embedding_provider.aclose()

    async def retrieve(self, request: RetrievalRequestV1) -> RetrievalResponseV1:
        try:
            vector = await self._embedding_provider.embed_query(request.query)
            if len(vector) != self._embedding_provider.dimension:
                raise ValueError("query embedding has an unexpected dimension")
            plan = self._hybrid_search.build(request, vector)
            hits = await self._search_backend.search(plan)
        except Exception:
            # The public fallback deliberately excludes provider details and query text.
            return failed_response(request.request_id)

        results = _eligible_unique_results(
            _above_relevance_floor(hits, plan.min_score),
            request.top_k,
            request.query_profile,
            audience=request.audience,
            purpose=request.purpose,
        )
        if not results:
            return no_data_response(request.request_id)
        if len(results) < 3:
            return no_data_response(request.request_id, insufficient=True)
        return RetrievalResponseV1(
            schema_version="1.0.0",
            request_id=request.request_id,
            status="SUCCESS",
            fallback_message=None,
            results=results,
        )

    async def retrieve_v2(self, request: RetrievalRequestV2) -> RetrievalResponseV2:
        """Retrieve only complete governed citations and never expose a partial batch."""

        try:
            vector = await self._embedding_provider.embed_query(request.query)
            if len(vector) != self._embedding_provider.dimension:
                raise ValueError("query embedding has an unexpected dimension")
            plan = self._hybrid_search.build_v2(
                request,
                vector,
                allow_needs_review=self._allow_needs_review_citations,
            )
            hits = await self._search_backend.search(plan)
        except Exception:
            return failed_response_v2(request.request_id)

        results = _eligible_unique_results_v2(
            _above_relevance_floor(hits, plan.min_score),
            request.top_k,
            request.query_profile,
            audience=request.audience,
            purpose=request.purpose,
            allow_needs_review=self._allow_needs_review_citations,
        )
        if results is None or not results:
            return no_data_response_v2(request.request_id)
        if len(results) < 3:
            return no_data_response_v2(request.request_id, insufficient=True)
        return RetrievalResponseV2(
            schema_version="2.0.0",
            request_id=request.request_id,
            status="SUCCESS",
            fallback_message=None,
            results=results,
        )


def build_retriever(
    settings: RagRuntimeSettings,
    *,
    google_api_key: str | None = None,
    google_timeout_seconds: float = 30.0,
) -> Retriever:
    """Compose explicitly configured embedding and search adapters."""

    return Retriever(
        embedding_provider=build_embedding_provider(
            settings.embedding,
            google_api_key=google_api_key,
            google_timeout_seconds=google_timeout_seconds,
        ),
        search_backend=build_opensearch_client(settings.opensearch, settings.hybrid),
        hybrid_search=HybridSearch(settings.hybrid),
        allow_needs_review_citations=settings.allow_needs_review_citations,
    )


async def close_retriever(retriever: Retriever | None) -> None:
    if retriever is not None:
        await retriever.aclose()


def _above_relevance_floor(hits: list[SearchHit], min_score: float) -> list[SearchHit]:
    """Drop hits the configured floor rejects, so a bad query yields NO_DATA.

    The floor applies to the pipeline-normalized hybrid score, not to raw
    cosine similarity: the collection's knn clause accepts only ``k``, so it
    always returns that many neighbours no matter how poor the match. Without
    this, a query matching nothing still produced five cited chunks reported as
    SUCCESS. A hit that satisfies only one retrieval leg cannot exceed that
    leg's configured weight, which is what keeps unmatched queries below the
    floor.
    """

    scored: list[SearchHit] = []
    for hit in hits:
        if hit.score >= min_score:
            scored.append(hit)
    return scored


def _eligible_unique_results(
    hits: list[SearchHit],
    top_k: int,
    profile: QueryProfile,
    *,
    audience: str | None,
    purpose: str | None,
) -> list[RetrievalResultV1]:
    results: list[RetrievalResultV1] = []
    seen: set[str] = set()
    for hit in hits:
        source = hit.source
        if not is_normal_rag_eligible(
            source,
            profile,
            audience=audience,
            purpose=purpose,
        ):
            continue
        chunk_id = source.get("chunk_id")
        if not isinstance(chunk_id, str) or chunk_id in seen:
            continue
        try:
            result = RetrievalResultV1(
                chunk_id=chunk_id,
                text=source.get("text"),
                score=hit.score,
                document_name=source.get("document_name"),
                section=source.get("section"),
                page_start=source.get("page_start"),
                page_end=source.get("page_end"),
                source_url=source.get("source_url"),
            )
        except (TypeError, ValueError, ValidationError):
            # Missing citation/policy metadata cannot enter agent context.
            continue
        seen.add(chunk_id)
        results.append(result)
        if len(results) == top_k:
            break
    return results


def _eligible_unique_results_v2(
    hits: list[SearchHit],
    top_k: int,
    profile: QueryProfile,
    *,
    audience: str | None,
    purpose: str | None,
    allow_needs_review: bool,
) -> list[RetrievalResultV2] | None:
    """Return governed results, or ``None`` when any selected citation is defective."""

    results: list[RetrievalResultV2] = []
    seen: set[str] = set()
    for hit in hits:
        source = hit.source
        if not is_normal_rag_eligible(
            source,
            profile,
            audience=audience,
            purpose=purpose,
            governed_citations=True,
            allow_needs_review=allow_needs_review,
        ):
            continue
        chunk_id = source.get("chunk_id")
        if not isinstance(chunk_id, str):
            return None
        if chunk_id in seen:
            continue
        try:
            result = RetrievalResultV2(
                chunk_id=chunk_id,
                source_id=source.get("source_id"),
                text=source.get("text"),
                score=hit.score,
                artifact_version=source.get("artifact_version"),
                title=source.get("title"),
                publisher=source.get("publisher"),
                section=source.get("section"),
                physical_page_start=source.get("physical_page_start"),
                physical_page_end=source.get("physical_page_end"),
                printed_page_start=source.get("printed_page_start"),
                printed_page_end=source.get("printed_page_end"),
                source_locator=source.get("source_locator"),
                direct_official_source_url=source.get("direct_official_source_url"),
                official_source_page_url=source.get("official_source_page_url"),
                direct_source_url=source.get("direct_source_url"),
                source_page_url=source.get("source_page_url"),
                is_official_source=source.get("is_official_source"),
                source_version=source.get("source_version"),
                source_version_date=source.get("source_version_date"),
                version_published_at=source.get("version_published_at"),
                source_page_updated_at=source.get("source_page_updated_at"),
                published_at=source.get("published_at"),
                last_verified_at=source.get("last_verified_at"),
                review_status=source.get("review_status"),
                production_approved=source.get("production_approved"),
            )
        except (TypeError, ValueError, ValidationError):
            return None
        seen.add(chunk_id)
        results.append(result)
        if len(results) == top_k:
            break
    return results

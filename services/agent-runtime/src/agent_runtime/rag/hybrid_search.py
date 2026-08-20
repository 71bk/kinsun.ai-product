from __future__ import annotations

from agent_runtime.rag.filters import build_normal_rag_filter
from agent_runtime.rag.models import (
    HybridSearchPlan,
    HybridSearchSettings,
    RetrievalRequestV1,
    RetrievalRequestV2,
)

_V1_SOURCE_FIELDS = [
    "chunk_id",
    "text",
    "document_name",
    "section",
    "page_start",
    "page_end",
    "source_url",
    "current_status",
    "stop_normal_rag",
    "risk_level",
    "requires_official_assessment",
    "requires_professional_assessment",
    "allowed_audiences",
    "allowed_purposes",
    "retrieval_eligible",
    "retrieval_block_reasons",
]

_V2_SOURCE_FIELDS = [
    "source_id",
    "artifact_version",
    "title",
    "publisher",
    "physical_page_start",
    "physical_page_end",
    "printed_page_start",
    "printed_page_end",
    "source_locator",
    "direct_official_source_url",
    "official_source_page_url",
    "direct_source_url",
    "source_page_url",
    "is_official_source",
    "source_version",
    "source_version_date",
    "version_published_at",
    "source_page_updated_at",
    "published_at",
    "last_verified_at",
    "review_status",
    "production_approved",
]


class HybridSearch:
    """Build a bounded query from approved parameters and profile configuration."""

    def __init__(self, settings: HybridSearchSettings) -> None:
        self._settings = settings

    def build(self, request: RetrievalRequestV1, query_vector: list[float]) -> HybridSearchPlan:
        return self._build(request, query_vector, governed_citations=False)

    def build_v2(
        self,
        request: RetrievalRequestV2,
        query_vector: list[float],
        *,
        allow_needs_review: bool,
    ) -> HybridSearchPlan:
        return self._build(
            request,
            query_vector,
            governed_citations=True,
            allow_needs_review=allow_needs_review,
        )

    def _build(
        self,
        request: RetrievalRequestV1 | RetrievalRequestV2,
        query_vector: list[float],
        *,
        governed_citations: bool,
        allow_needs_review: bool = False,
    ) -> HybridSearchPlan:
        profile = self._settings.for_profile(request.query_profile)
        body: dict[str, object] = {
            "size": request.top_k,
            "_source": _V1_SOURCE_FIELDS + (_V2_SOURCE_FIELDS if governed_citations else []),
            "query": {
                "hybrid": {
                    "queries": [
                        {"match": {"text": {"query": request.query}}},
                        {
                            "knn": {
                                "embedding": {
                                    "vector": query_vector,
                                    # Serverless accepts only `k` here. It rejects
                                    # min_score and max_distance alike with "[knn]
                                    # requires exactly one of k, distance or score
                                    # to be set", so profile.vector_min_score cannot
                                    # be enforced on the vector leg. Sufficiency is
                                    # decided by Retriever's minimum eligible count.
                                    "k": request.top_k,
                                }
                            }
                        },
                    ],
                    "filter": build_normal_rag_filter(
                        profile=request.query_profile,
                        audience=request.audience,
                        purpose=request.purpose,
                        governed_citations=governed_citations,
                        allow_needs_review=allow_needs_review,
                    ),
                }
            },
        }
        return HybridSearchPlan(
            index_alias=self._settings.index_alias,
            search_pipeline=profile.search_pipeline,
            profile=profile.profile,
            bm25_weight=profile.bm25_weight,
            vector_weight=profile.vector_weight,
            min_score=profile.vector_min_score,
            body=body,
        )

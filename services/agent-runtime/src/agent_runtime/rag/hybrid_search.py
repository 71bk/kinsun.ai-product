from __future__ import annotations

from agent_runtime.rag.models import (
    HybridSearchPlan,
    HybridSearchSettings,
    RetrievalRequestV1,
    RetrievalRequestV2,
)


class HybridSearch:
    """Build a bounded query from approved parameters and profile configuration."""

    def __init__(self, settings: HybridSearchSettings) -> None:
        self._settings = settings

    def build(
        self,
        request: RetrievalRequestV1,
        query_vector: list[float],
        *,
        allow_all_audiences: bool = False,
    ) -> HybridSearchPlan:
        return self._build(
            request,
            query_vector,
            governed_citations=False,
            allow_all_audiences=allow_all_audiences,
        )

    def build_v2(
        self,
        request: RetrievalRequestV2,
        query_vector: list[float],
        *,
        allow_needs_review: bool,
        allow_all_audiences: bool = False,
        policy_candidate_chunk_ids: tuple[str, ...] | None = None,
    ) -> HybridSearchPlan:
        return self._build(
            request,
            query_vector,
            governed_citations=True,
            allow_needs_review=allow_needs_review,
            allow_all_audiences=allow_all_audiences,
            policy_candidate_chunk_ids=policy_candidate_chunk_ids,
        )

    def _build(
        self,
        request: RetrievalRequestV1 | RetrievalRequestV2,
        query_vector: list[float],
        *,
        governed_citations: bool,
        allow_needs_review: bool = False,
        allow_all_audiences: bool = False,
        policy_candidate_chunk_ids: tuple[str, ...] | None = None,
    ) -> HybridSearchPlan:
        profile = self._settings.for_profile(request.query_profile)
        return HybridSearchPlan(
            query=request.query,
            query_vector=query_vector,
            profile=profile.profile,
            top_k=request.top_k,
            audience=request.audience,
            purpose=request.purpose,
            governed_citations=governed_citations,
            allow_needs_review=allow_needs_review,
            allow_all_audiences=allow_all_audiences,
            search_result_limit=50 if policy_candidate_chunk_ids is not None else 5,
            policy_candidate_chunk_ids=policy_candidate_chunk_ids,
            bm25_weight=profile.bm25_weight,
            vector_weight=profile.vector_weight,
            min_score=profile.vector_min_score,
        )

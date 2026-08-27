from __future__ import annotations

from typing import Protocol

from agent_runtime.common.enums import ActorRole, RiskLevel, SafetyDecision
from agent_runtime.contracts.models import AgentRunRequest, SafetyEvaluation
from agent_runtime.rag.fallback import failed_response_v2
from agent_runtime.rag.models import (
    QueryProfile,
    RetrievalRequestV2,
    RetrievalResponseV2,
)

RAG_PURPOSES: dict[str, QueryProfile] = {
    "general_information": "natural_language",
    "legal_reference": "legal",
}

LEGAL_QUERY_MARKERS = (
    "長照法",
    "長期照顧服務法",
    "長照服務法",
    "法規",
    "法律",
    "條文",
    "施行細則",
)

AUDIENCE_BY_ROLE = {
    ActorRole.ELDER: "elder",
    ActorRole.FAMILY: "family_caregiver",
    ActorRole.STAFF: "care_professional",
    ActorRole.SYSTEM: "system_admin",
}


class RagRetriever(Protocol):
    async def retrieve_v2(self, request: RetrievalRequestV2) -> RetrievalResponseV2: ...


def is_rag_request(request: AgentRunRequest) -> bool:
    """Conservatively route only requests carrying an explicit knowledge purpose."""

    return _normalized_purpose(request.purpose) in RAG_PURPOSES


def build_retrieval_request(request: AgentRunRequest) -> RetrievalRequestV2:
    purpose = _normalized_purpose(request.purpose)
    profile = _query_profile(purpose, request.input_text)
    return RetrievalRequestV2(
        schema_version="2.0.0",
        request_id=request.request_id,
        query=_retrieval_query(profile, request.input_text),
        query_profile=profile,
        top_k=5,
        audience=AUDIENCE_BY_ROLE[request.actor_role],
        purpose=purpose,
        language=request.language,
    )


async def retrieve_for_agent(
    request: AgentRunRequest,
    retriever: RagRetriever | None,
) -> RetrievalResponseV2:
    """Return a sanitized FAILED outcome for missing or faulty retrieval adapters."""

    if retriever is None:
        return failed_response_v2(request.request_id)
    try:
        retrieval_request = build_retrieval_request(request)
        response = await retriever.retrieve_v2(retrieval_request)
        if response.request_id != request.request_id:
            return failed_response_v2(request.request_id)
        return response
    except Exception:
        # Do not expose provider errors or the elder's query in the Agent reply.
        return failed_response_v2(request.request_id)


def retrieval_fallback_safety(response: RetrievalResponseV2) -> SafetyEvaluation:
    """Represent a no-guess retrieval outcome using the existing Agent wire contract."""

    if response.status == "SUCCESS" or response.fallback_message is None:
        raise ValueError("retrieval fallback safety requires a non-success response")
    return SafetyEvaluation(
        decision=SafetyDecision.SAFE_FALLBACK,
        risk_level=RiskLevel.LOW,
        reason_codes=[f"RAG_{response.status}"],
        matched_terms=[],
        safe_reply=response.fallback_message,
    )


def _normalized_purpose(value: str) -> str:
    return value.strip().casefold().replace("-", "_")


def _query_profile(purpose: str, query: str) -> QueryProfile:
    configured = RAG_PURPOSES[purpose]
    if configured == "legal" or any(marker in query for marker in LEGAL_QUERY_MARKERS):
        return "legal"
    return configured


def _retrieval_query(profile: QueryProfile, query: str) -> str:
    """Expand common statute aliases for retrieval without changing the user's question."""

    if profile != "legal":
        return query
    return query.replace("長照服務法", "長期照顧服務法").replace("長照法", "長期照顧服務法")

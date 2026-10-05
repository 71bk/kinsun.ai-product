"""Natural public-knowledge retrieval and one bounded grounded model answer."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from agent_runtime.agents.safety_evaluator.evaluator import SafetyEvaluator
from agent_runtime.common.enums import ActorRole, SafetyDecision
from agent_runtime.contracts.models import AgentRunRequest
from agent_runtime.rag.citations import append_citations
from agent_runtime.rag.diagnostics import failure_diagnostics, mark_stage, record_exception
from agent_runtime.rag.evidence_models import (
    RetrievalRequestV3,
    RetrievalResponseV3,
    evidence_failure,
)
from agent_runtime.rag.grounded_answer import generate_grounded_answer
from agent_runtime.rag.public_knowledge_policy import POLICY_VERSION

CURRENT_MARKERS = (
    "最新",
    "目前",
    "現在",
    "今年",
    "資格",
    "補助",
    "給付",
    "額度",
    "費用",
    "自付",
    "申請條件",
    "法規",
    "條文",
    "長照法",
    "長期照顧服務法",
)
FALLBACK = "目前找到的資料不足以回答這個問題，請補充您想了解的內容。"
CLARIFICATION = "請再說明您想了解哪一項服務、規定或申請步驟。"


def requires_current_source(query: str, purpose: str) -> bool:
    return purpose == "legal_reference" or any(marker in query for marker in CURRENT_MARKERS)


def _public_generation_request(request: RetrievalRequestV3) -> AgentRunRequest:
    # Public retrieval has no elder/tenant records. These internal labels identify
    # a public-only prompt, never an authenticated actor or access to domain data.
    roles = {
        "elder": ActorRole.ELDER,
        "family_caregiver": ActorRole.FAMILY,
        "care_professional": ActorRole.STAFF,
        "system_admin": ActorRole.SYSTEM,
    }
    return AgentRunRequest(
        request_id=request.request_id,
        session_id="public-knowledge",
        actor_id="public-knowledge",
        actor_role=roles[request.audience],
        elder_id="public-knowledge",
        tenant_id="public-knowledge",
        purpose=request.purpose,
        consent_version="public-only",
        policy_version=POLICY_VERSION,
        language=request.language,
        input_text=request.query,
        latency_budget_ms=30000,
    )


class EvidenceService:
    def __init__(self, *, retriever, provider, release_id: str, embedding_profile_id: str):
        self.retriever = retriever
        self.provider = provider
        self.release_id = release_id
        self.embedding_profile_id = embedding_profile_id
        self.safety = SafetyEvaluator()

    def _no_data(
        self,
        request,
        *,
        decision="INSUFFICIENT",
        reason="EVIDENCE_INSUFFICIENT",
        message=None,
        missing=(),
    ):
        return RetrievalResponseV3(
            request_id=request.request_id,
            status="NO_DATA",
            decision=decision,
            fallback_message=message or (CLARIFICATION if decision == "CLARIFY" else FALLBACK),
            reason_codes=[reason],
            missing_facets=list(missing),
            release_id=self.release_id,
            embedding_profile_id=self.embedding_profile_id,
            policy_version=POLICY_VERSION,
        )

    async def retrieve_v3(self, request: RetrievalRequestV3) -> RetrievalResponseV3:
        with failure_diagnostics(request.request_id) as diagnostic:
            deadline = asyncio.timeout(30)
            try:
                async with deadline:
                    response = await self._retrieve(request)
                if response.status == "FAILED" and diagnostic.code is None:
                    diagnostic.code = "PIPELINE_FAILED"
                return response
            except asyncio.CancelledError:
                diagnostic.code = "REQUEST_CANCELLED"
                raise
            except Exception as exc:
                if deadline.expired():
                    diagnostic.code = "DEADLINE_EXCEEDED"
                else:
                    record_exception(exc)
                return evidence_failure(request.request_id)

    async def _retrieve(self, request: RetrievalRequestV3) -> RetrievalResponseV3:
        generation_request = _public_generation_request(request)
        safety = self.safety.evaluate(generation_request, "")
        if safety.decision != SafetyDecision.ALLOW:
            return self._no_data(request, reason="SAFETY_GATE", message=safety.safe_reply)
        require_current = requires_current_source(request.query, request.purpose)
        mark_stage("retrieval")
        results = await self.retriever.load_public_candidates(
            request, require_current=require_current
        )
        if len(results) > 5 or len({r.chunk_id for r in results}) != len(results):
            raise ValueError("invalid candidate batch")
        if require_current:
            results = [r for r in results if r.current_status == "current"]
        if not results:
            return self._no_data(request, reason="NO_ELIGIBLE_EVIDENCE")
        versions = defaultdict(set)
        for result in results:
            if result.current_status == "current" and result.source_version not in (
                None,
                "unknown",
            ):
                versions[result.source_id].add(result.source_version)
        if any(len(values) > 1 for values in versions.values()):
            return self._no_data(request, reason="SOURCE_VERSION_CONFLICT")
        generated = await generate_grounded_answer(
            self.provider, generation_request, results, request.language
        )
        if generated.status == "FAILED":
            return evidence_failure(request.request_id)
        mark_stage("response")
        if generated.status in {"INSUFFICIENT", "CLARIFY"}:
            gap_safety = self.safety.evaluate(
                generation_request, "、".join(generated.missing_facets)
            )
            if gap_safety.decision != SafetyDecision.ALLOW:
                return self._no_data(request, reason="SAFETY_GATE", message=gap_safety.safe_reply)
            return self._no_data(
                request,
                decision=generated.status,
                reason=generated.reason_code,
                missing=generated.missing_facets,
            )
        chosen = [r for r in results if r.chunk_id in generated.citation_ids]
        body = generated.answer_text or ""
        if generated.status == "PARTIAL":
            body += "\n\n資料尚未涵蓋：" + "、".join(generated.missing_facets) + "。"
        if any(r.current_status == "unknown" for r in chosen):
            body += "\n\n提醒：部分來源尚未確認是否仍為現行版本，以上僅供一般資訊參考。"
        safety = self.safety.evaluate(generation_request, body)
        if safety.decision != SafetyDecision.ALLOW:
            return self._no_data(request, reason="SAFETY_GATE", message=safety.safe_reply)
        answer = append_citations(body, chosen, max_length=4000)
        if not answer.startswith(body.strip() + "\n\n"):
            raise ValueError("answer and complete citations exceed the response budget")
        return RetrievalResponseV3(
            request_id=request.request_id,
            status="SUCCESS",
            decision="PARTIAL" if generated.status == "PARTIAL" else "SUFFICIENT",
            results=chosen,
            answer_text=answer,
            missing_facets=list(generated.missing_facets),
            reason_codes=[generated.reason_code],
            release_id=self.release_id,
            embedding_profile_id=self.embedding_profile_id,
            policy_version=POLICY_VERSION,
        )

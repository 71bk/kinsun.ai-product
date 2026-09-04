from __future__ import annotations

import asyncio
import logging

from agent_runtime.agents.care_action_candidate.agent import CareActionCandidateAgent
from agent_runtime.agents.companion.agent import CompanionAgent
from agent_runtime.agents.event_extractor.agent import EventExtractorAgent
from agent_runtime.agents.event_extractor.models import EventExtractionContext
from agent_runtime.agents.memory_extractor.agent import MemoryExtractorAgent
from agent_runtime.agents.safety_evaluator.evaluator import SafetyEvaluator
from agent_runtime.common.enums import RiskLevel, SafetyDecision
from agent_runtime.common.errors import StepLimitError
from agent_runtime.context.builder import (
    build_minimal_context_manifest,
    build_rag_context_manifest,
)
from agent_runtime.contracts.models import (
    AgentRunRequest,
    AgentRunResponse,
    CareActionCandidateProposal,
    ContextManifest,
    EventCandidateProposal,
    MemoryCandidateProposal,
    SafetyEvaluation,
)
from agent_runtime.models.provider import ModelProvider
from agent_runtime.orchestration.execution_budget import ExecutionBudget
from agent_runtime.orchestration.fallback import fallback_reply
from agent_runtime.orchestration.rag_integration import (
    RagRetriever,
    is_rag_request,
    retrieval_fallback_safety,
    retrieve_for_agent,
)
from agent_runtime.orchestration.stop_conditions import map_to_status
from agent_runtime.rag.citations import append_citations
from agent_runtime.rag.fallback import failed_response_v2
from agent_runtime.rag.models import RetrievalResponseV2
from agent_runtime.tracing.trace import new_agent_run_id, new_trace_id

logger = logging.getLogger(__name__)

LATENCY_BUDGET_FALLBACK = "這次處理時間超過安全限制，請稍後再試。"


class AgentOrchestrator:
    """Bounded orchestrator that returns replies and untrusted typed proposals."""

    def __init__(
        self,
        provider: ModelProvider,
        *,
        max_steps: int,
        agent_version: str = "0.0.1",
        max_tool_rounds: int = 2,
        max_total_tools: int = 5,
    ) -> None:
        if not agent_version.strip() or len(agent_version) > 64:
            raise ValueError("agent_version must be between 1 and 64 characters")
        if max_tool_rounds < 0 or max_total_tools < 0:
            raise ValueError("Tool limits must not be negative")

        self.provider = provider
        self.max_steps = max_steps
        self.agent_version = agent_version
        self.max_tool_rounds = max_tool_rounds
        self.max_total_tools = max_total_tools
        self.companion = CompanionAgent(provider)
        self.care_action_candidate = CareActionCandidateAgent()
        self.event_extractor = EventExtractorAgent()
        self.memory_extractor = MemoryExtractorAgent()
        self.safety_evaluator = SafetyEvaluator()

    def select_agent(self, _request: AgentRunRequest) -> str:
        return "companion-agent"

    async def run(
        self,
        request: AgentRunRequest,
        *,
        rag_retriever: RagRetriever | None = None,
    ) -> AgentRunResponse:
        if request.max_steps > self.max_steps:
            raise StepLimitError("max_steps exceeds system limit")

        budget = ExecutionBudget(
            latency_budget_ms=request.latency_budget_ms,
            max_decisions=request.max_steps,
            max_tool_rounds=self.max_tool_rounds,
            max_total_tools=self.max_total_tools,
        )
        try:
            async with asyncio.timeout(budget.remaining_seconds()):
                return await self._run_bounded(
                    request,
                    budget=budget,
                    rag_retriever=rag_retriever,
                )
        except TimeoutError:
            logger.warning(
                "agent_latency_budget_exhausted",
                extra={
                    "latency_budget_ms": request.latency_budget_ms,
                    "decision_count": budget.decision_count,
                    "tool_round_count": budget.tool_round_count,
                    "total_tool_count": budget.total_tool_count,
                },
            )
            selected_agent = self.select_agent(request)
            safety_result = SafetyEvaluation(
                decision=SafetyDecision.SAFE_FALLBACK,
                risk_level=RiskLevel.LOW,
                reason_codes=["LATENCY_BUDGET_EXCEEDED"],
                matched_terms=[],
                safe_reply=LATENCY_BUDGET_FALLBACK,
            )
            return self._response(
                request=request,
                trace_id=request.trace_id or new_trace_id(),
                selected_agent=selected_agent,
                context_manifest=build_minimal_context_manifest(request, selected_agent),
                step_count=max(1, budget.decision_count),
                safety_result=safety_result,
                reply_text=LATENCY_BUDGET_FALLBACK,
            )

    async def _run_bounded(
        self,
        request: AgentRunRequest,
        *,
        budget: ExecutionBudget,
        rag_retriever: RagRetriever | None,
    ) -> AgentRunResponse:
        trace_id = request.trace_id or new_trace_id()
        selected_agent = self.select_agent(request)
        context_manifest = build_minimal_context_manifest(request, selected_agent)

        # The companion decision remains one bounded model step. Proposal
        # extraction is deterministic and cannot write Core domain state.
        step_count = budget.consume_decision()

        retrieval: RetrievalResponseV2 | None = None
        if is_rag_request(request):
            input_safety = self.safety_evaluator.evaluate(request, "")
            if input_safety.decision == SafetyDecision.ALLOW:
                retrieval = await budget.wait_for(
                    lambda: retrieve_for_agent(request, rag_retriever)
                )
                if retrieval.status != "SUCCESS":
                    safety_result = retrieval_fallback_safety(retrieval)
                    return self._response(
                        request=request,
                        trace_id=trace_id,
                        selected_agent=selected_agent,
                        context_manifest=context_manifest,
                        step_count=step_count,
                        safety_result=safety_result,
                        reply_text=fallback_reply(safety_result, ""),
                    )
                try:
                    context_manifest = build_rag_context_manifest(
                        request,
                        selected_agent,
                        retrieval.results,
                    )
                except ValueError:
                    retrieval = failed_response_v2(request.request_id)
                    safety_result = retrieval_fallback_safety(retrieval)
                    return self._response(
                        request=request,
                        trace_id=trace_id,
                        selected_agent=selected_agent,
                        context_manifest=context_manifest,
                        step_count=step_count,
                        safety_result=safety_result,
                        reply_text=fallback_reply(safety_result, ""),
                    )

        companion_output = (
            await budget.wait_for(
                lambda: self.companion.run(request, context_manifest, request.language)
            )
        ).reply_text
        safety_result = self.safety_evaluator.evaluate(request, companion_output)

        reply_text = fallback_reply(safety_result, companion_output)
        if retrieval is not None and safety_result.decision == SafetyDecision.ALLOW:
            try:
                reply_text = append_citations(reply_text, retrieval.results)
            except ValueError:
                retrieval = failed_response_v2(request.request_id)
                safety_result = retrieval_fallback_safety(retrieval)
                reply_text = fallback_reply(safety_result, "")

        event_candidate_proposal: EventCandidateProposal | None = None
        if (
            safety_result.decision == SafetyDecision.ALLOW
            and "event_candidate" in request.requested_outputs
        ):
            try:
                extraction = await budget.wait_for(
                    lambda: self.event_extractor.run(
                        request,
                        EventExtractionContext(),
                    )
                )
            except ValueError:
                extraction = None
            if isinstance(extraction, EventCandidateProposal):
                event_candidate_proposal = extraction

        memory_candidate_proposal: MemoryCandidateProposal | None = None
        if (
            safety_result.decision == SafetyDecision.ALLOW
            and "memory_candidate" in request.requested_outputs
            and event_candidate_proposal is not None
        ):
            try:
                memory_extraction = await budget.wait_for(
                    lambda: self.memory_extractor.run(
                        request,
                        source_event=event_candidate_proposal,
                    )
                )
            except ValueError:
                memory_extraction = None
            if isinstance(memory_extraction, MemoryCandidateProposal):
                memory_candidate_proposal = memory_extraction

        care_action_candidate_proposal: CareActionCandidateProposal | None = None
        if (
            safety_result.decision == SafetyDecision.ALLOW
            and "care_action_candidate" in request.requested_outputs
            and event_candidate_proposal is not None
        ):
            try:
                action_extraction = await budget.wait_for(
                    lambda: self.care_action_candidate.run(
                        request,
                        source_event=event_candidate_proposal,
                    )
                )
            except ValueError:
                action_extraction = None
            if isinstance(action_extraction, CareActionCandidateProposal):
                care_action_candidate_proposal = action_extraction

        return self._response(
            request=request,
            trace_id=trace_id,
            selected_agent=selected_agent,
            context_manifest=context_manifest,
            step_count=step_count,
            safety_result=safety_result,
            reply_text=reply_text,
            event_candidate_proposal=event_candidate_proposal,
            memory_candidate_proposal=memory_candidate_proposal,
            care_action_candidate_proposal=care_action_candidate_proposal,
        )

    @staticmethod
    def _response(
        *,
        request: AgentRunRequest,
        trace_id: str,
        selected_agent: str,
        context_manifest: ContextManifest,
        step_count: int,
        safety_result: SafetyEvaluation,
        reply_text: str,
        event_candidate_proposal: EventCandidateProposal | None = None,
        memory_candidate_proposal: MemoryCandidateProposal | None = None,
        care_action_candidate_proposal: CareActionCandidateProposal | None = None,
    ) -> AgentRunResponse:
        return AgentRunResponse(
            request_id=request.request_id,
            trace_id=trace_id,
            agent_run_id=request.agent_run_id or new_agent_run_id(),
            selected_agent=selected_agent,
            reply_text=reply_text,
            reply_language=request.language,
            safety_result=safety_result,
            context_manifest_id=context_manifest.context_manifest_id,
            step_count=step_count,
            result_status=map_to_status(safety_result),
            reason_codes=list(dict.fromkeys(safety_result.reason_codes)),
            event_candidate_proposal=event_candidate_proposal,
            memory_candidate_proposal=memory_candidate_proposal,
            care_action_candidate_proposal=care_action_candidate_proposal,
        )

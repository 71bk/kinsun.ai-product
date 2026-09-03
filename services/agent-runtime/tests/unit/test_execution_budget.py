from __future__ import annotations

import asyncio
import time

import pytest

from agent_runtime.common.enums import ResultStatus
from agent_runtime.common.errors import StepLimitError
from agent_runtime.contracts.models import AgentRunRequest, ContextManifest
from agent_runtime.models.provider import ModelProvider
from agent_runtime.orchestration.execution_budget import ExecutionBudget
from agent_runtime.orchestration.orchestrator import (
    LATENCY_BUDGET_FALLBACK,
    AgentOrchestrator,
)
from agent_runtime.rag.models import RetrievalRequestV2, RetrievalResponseV2


class SlowProvider(ModelProvider):
    def __init__(self) -> None:
        self.cancelled = False
        self.call_count = 0

    async def generate_reply(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> str:
        self.call_count += 1
        try:
            await asyncio.sleep(60)
        finally:
            self.cancelled = True
        return "unreachable"


class UnexpectedProvider(ModelProvider):
    async def generate_reply(
        self,
        request: AgentRunRequest,
        context_manifest: ContextManifest,
        language: str,
    ) -> str:
        raise AssertionError("provider must not run after the retrieval deadline")


class SlowRetriever:
    def __init__(self) -> None:
        self.cancelled = False

    async def retrieve_v2(self, request: RetrievalRequestV2) -> RetrievalResponseV2:
        try:
            await asyncio.sleep(60)
        finally:
            self.cancelled = True
        raise AssertionError("unreachable")


def make_request(**overrides: object) -> AgentRunRequest:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "request_id": "req-budget-001",
        "trace_id": "trace-budget-001",
        "session_id": "sess-budget-001",
        "actor_id": "actor-elder-001",
        "actor_role": "elder",
        "elder_id": "elder-001",
        "tenant_id": "tenant-001",
        "purpose": "conversation",
        "consent_version": "cv-synthetic-001",
        "policy_version": "pv-synthetic-001",
        "language": "zh-TW",
        "input_text": "請說一個故事。",
        "allowed_tools": [],
        "requested_outputs": [],
        "max_steps": 1,
        "latency_budget_ms": 100,
    }
    values.update(overrides)
    return AgentRunRequest.model_validate(values)


def test_execution_budget_enforces_decision_and_tool_boundaries_atomically() -> None:
    budget = ExecutionBudget(
        latency_budget_ms=3_000,
        max_decisions=1,
        max_tool_rounds=1,
        max_total_tools=2,
    )

    assert budget.consume_decision() == 1
    with pytest.raises(StepLimitError, match="decision budget"):
        budget.consume_decision()

    budget.consume_tool_round(2)
    assert budget.tool_round_count == 1
    assert budget.total_tool_count == 2
    with pytest.raises(StepLimitError, match="Tool round budget"):
        budget.consume_tool_round(1)
    assert budget.tool_round_count == 1
    assert budget.total_tool_count == 2

    total_limited = ExecutionBudget(
        latency_budget_ms=3_000,
        max_decisions=1,
        max_tool_rounds=2,
        max_total_tools=2,
    )
    total_limited.consume_tool_round(2)
    with pytest.raises(StepLimitError, match="total Tool budget"):
        total_limited.consume_tool_round(1)
    assert total_limited.tool_round_count == 1
    assert total_limited.total_tool_count == 2


@pytest.mark.asyncio
async def test_provider_is_cancelled_at_the_shared_latency_deadline(caplog) -> None:
    provider = SlowProvider()
    orchestrator = AgentOrchestrator(provider, max_steps=3)
    started = time.perf_counter()

    with caplog.at_level("WARNING", logger="agent_runtime.orchestration.orchestrator"):
        response = await orchestrator.run(make_request())

    assert time.perf_counter() - started < 1.0
    assert provider.call_count == 1
    assert provider.cancelled is True
    assert response.result_status == ResultStatus.SAFE_FALLBACK
    assert response.reason_codes == ["LATENCY_BUDGET_EXCEEDED"]
    assert response.reply_text == LATENCY_BUDGET_FALLBACK
    record = next(
        record for record in caplog.records if record.message == "agent_latency_budget_exhausted"
    )
    assert record.latency_budget_ms == 100
    assert record.decision_count == 1
    assert record.tool_round_count == 0
    assert record.total_tool_count == 0


@pytest.mark.asyncio
async def test_retrieval_is_cancelled_at_the_same_end_to_end_deadline() -> None:
    retriever = SlowRetriever()
    response = await AgentOrchestrator(UnexpectedProvider(), max_steps=3).run(
        make_request(purpose="general_information"),
        rag_retriever=retriever,
    )

    assert retriever.cancelled is True
    assert response.result_status == ResultStatus.SAFE_FALLBACK
    assert response.reason_codes == ["LATENCY_BUDGET_EXCEEDED"]

from __future__ import annotations

import pytest

from agent_runtime.agents.memory_extractor.agent import MemoryExtractorAgent
from agent_runtime.contracts.models import AgentRunRequest, EventCandidateProposal


def _request(text: str, *, language: str = "zh-TW") -> AgentRunRequest:
    return AgentRunRequest(
        request_id="req-memory-1",
        trace_id="trace-memory-1",
        session_id="session-memory-1",
        actor_id="actor-memory-1",
        actor_role="elder",
        elder_id="elder-memory-1",
        tenant_id="tenant-memory-1",
        purpose="BASIC_VOICE",
        consent_version="2",
        policy_version="policy-v2",
        language=language,
        input_text=text,
        requested_outputs=["event_candidate", "memory_candidate"],
        max_steps=3,
        latency_budget_ms=3000,
    )


def _event(event_type: str = "MEAL") -> EventCandidateProposal:
    return EventCandidateProposal(
        event_type=event_type,
        event_time=None,
        structured_payload={"observation_basis": "ELDER_STATEMENT"},
        evidence_refs=[],
        confidence_band="MEDIUM",
        review_requirement="REQUIRED",
        extractor_version="event-extractor-v1",
    )


@pytest.mark.asyncio
async def test_explicit_stable_breakfast_routine_returns_minimized_proposal() -> None:
    proposal = await MemoryExtractorAgent().run(
        _request("我每天早餐都吃粥"),
        source_event=_event(),
    )

    assert proposal is not None
    assert proposal.memory_type == "ROUTINE"
    assert proposal.normalized_content == "每天早餐習慣吃粥。"
    assert proposal.confidence_band == "HIGH"
    assert "每天早餐" in proposal.confirmation_question
    assert {"elder_id", "tenant_id", "source_event_ids"}.isdisjoint(proposal.model_dump())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "我今天早餐吃了粥",
        "我最近胃不舒服所以吃粥",
        "我很孤單，希望每天有人陪",
    ],
)
async def test_non_stable_or_sensitive_statement_returns_no_memory(text: str) -> None:
    assert await MemoryExtractorAgent().run(_request(text), source_event=_event()) is None


@pytest.mark.asyncio
async def test_memory_requires_matching_source_event_type() -> None:
    assert (
        await MemoryExtractorAgent().run(
            _request("我每天早餐都吃粥"),
            source_event=_event("ACTIVITY"),
        )
        is None
    )

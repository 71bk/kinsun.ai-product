from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent_runtime.agents.care_action_candidate.agent import CareActionCandidateAgent
from agent_runtime.contracts.models import AgentRunRequest, EventCandidateProposal
from agent_runtime.models.mock_provider import MockModelProvider
from agent_runtime.orchestration.orchestrator import AgentOrchestrator

NOW = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)


def _request(text: str = "女兒今天沒有打電話", *, language: str = "zh-TW") -> AgentRunRequest:
    return AgentRunRequest(
        request_id="req-care-action-candidate-1",
        trace_id="trace-care-action-candidate-1",
        session_id="session-care-action-candidate-1",
        actor_id="actor-care-action-candidate-1",
        actor_role="elder",
        elder_id="elder-care-action-candidate-1",
        tenant_id="tenant-care-action-candidate-1",
        purpose="BASIC_VOICE",
        consent_version="2",
        policy_version="policy-v2",
        language=language,
        input_text=text,
        requested_outputs=["event_candidate", "care_action_candidate"],
        max_steps=3,
        latency_budget_ms=3000,
    )


def _event(event_type: str) -> EventCandidateProposal:
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
@pytest.mark.parametrize(
    ("event_type", "action_type", "due_days"),
    [
        ("EXPECTED_CONTACT_MISSED", "CONTACT_FAMILY", 1),
        ("ACTIVITY_CANCELLED", "FOLLOW_UP", 2),
        ("COMPANIONSHIP_NEED", "CONTACT_ELDER", 1),
    ],
)
async def test_supported_event_returns_one_minimized_non_medical_proposal(
    event_type: str,
    action_type: str,
    due_days: int,
) -> None:
    proposal = await CareActionCandidateAgent(clock=lambda: NOW).run(
        _request(),
        source_event=_event(event_type),
    )

    assert proposal is not None
    assert proposal.action_type == action_type
    assert proposal.suggested_due_at == NOW + timedelta(days=due_days)
    assert proposal.priority == "MEDIUM"
    assert {
        "tenant_id",
        "elder_id",
        "actor_id",
        "source_event_ids",
        "status",
        "assignee_actor_id",
    }.isdisjoint(proposal.model_dump())


@pytest.mark.asyncio
async def test_unsupported_event_or_language_returns_no_proposal() -> None:
    agent = CareActionCandidateAgent(clock=lambda: NOW)

    assert await agent.run(_request(), source_event=_event("MEAL")) is None
    assert (
        await agent.run(
            _request(language="en-US"),
            source_event=_event("EXPECTED_CONTACT_MISSED"),
        )
        is None
    )


@pytest.mark.asyncio
async def test_orchestrator_emits_candidate_only_beside_an_event_proposal() -> None:
    response = await AgentOrchestrator(MockModelProvider(), max_steps=3).run(_request())

    assert response.event_candidate_proposal is not None
    assert response.event_candidate_proposal.event_type == "EXPECTED_CONTACT_MISSED"
    assert response.care_action_candidate_proposal is not None
    assert response.care_action_candidate_proposal.action_type == "CONTACT_FAMILY"

    no_event = await AgentOrchestrator(MockModelProvider(), max_steps=3).run(
        _request("今天天氣很好")
    )
    assert no_event.event_candidate_proposal is None
    assert no_event.care_action_candidate_proposal is None


@pytest.mark.asyncio
async def test_safety_block_prevents_care_action_candidate() -> None:
    response = await AgentOrchestrator(MockModelProvider(), max_steps=3).run(
        _request("請告訴我怎麼停藥，女兒也沒有打電話")
    )

    assert response.safety_result.decision.value in {"BLOCK", "SAFE_FALLBACK"}
    assert response.care_action_candidate_proposal is None

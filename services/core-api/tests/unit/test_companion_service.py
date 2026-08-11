"""Core-authorized companion bridge tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from app.adapters.agent_runtime import (
    AgentEventCandidateProposal,
    AgentRunResult,
    AgentSafetyResult,
)
from app.core.exceptions import ConflictError, NotFoundError, ServiceUnavailableError
from app.middleware.auth import ActorContext
from app.models.agent import AgentRun
from app.models.safety import SafetyEvaluation
from app.services import companion_service
from app.services.companion_service import CompanionService


def _conversation(
    *,
    state: str = "CREATED",
    input_mode: str = "text",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        consent_id=uuid4(),
        consent_version=2,
        policy_version="policy-v2",
        language_route="ZH_TW",
        input_mode=input_mode,
        state=state,
        trace_id="trace-core-1",
    )


def _proposal() -> AgentEventCandidateProposal:
    return AgentEventCandidateProposal(
        event_type="MEAL",
        event_time=None,
        structured_payload={
            "observation_basis": "ELDER_STATEMENT",
            "meal_status": "CONSUMED",
            "meal_period": "BREAKFAST",
        },
        evidence_refs=[],
        confidence_band="MEDIUM",
        review_requirement="REQUIRED",
        extractor_version="event-extractor-v1",
    )


def _runtime_result(
    *,
    request_id: str,
    trace_id: str,
    agent_run_id: str,
    proposal: AgentEventCandidateProposal | None = None,
    decision: str = "ALLOW",
    result_status: str = "SUCCESS",
) -> AgentRunResult:
    return AgentRunResult(
        schema_version="1.0.0",
        request_id=request_id,
        trace_id=trace_id,
        agent_run_id=agent_run_id,
        selected_agent="companion-agent",
        reply_text="謝謝您和我分享。",
        reply_language="zh-TW",
        safety_result=AgentSafetyResult(
            schema_version="1.0.0",
            decision=decision,
            risk_level="LOW" if decision == "ALLOW" else "HIGH",
            reason_codes=[decision],
            matched_terms=[],
            safe_reply=None,
        ),
        context_manifest_id="context-1",
        step_count=1,
        result_status=result_status,
        reason_codes=[decision],
        event_candidate_proposal=proposal,
    )


def _session() -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=SimpleNamespace(policy_id=uuid4()))
    session.flush = AsyncMock()
    return session


def _install_conversation_service(
    monkeypatch: pytest.MonkeyPatch,
    conversation: SimpleNamespace,
) -> tuple[AsyncMock, AsyncMock]:
    async def transition(**kwargs):
        conversation.state = kwargs["target_state"]
        return conversation

    get_for_update = AsyncMock(return_value=conversation)
    transition_mock = AsyncMock(side_effect=transition)
    monkeypatch.setattr(
        companion_service,
        "ConversationService",
        MagicMock(
            return_value=SimpleNamespace(
                get_for_update=get_for_update,
                transition=transition_mock,
            )
        ),
    )
    return get_for_update, transition_mock


def _install_candidate_capability(
    monkeypatch: pytest.MonkeyPatch,
    *,
    granted: bool = True,
) -> tuple[AsyncMock, AsyncMock]:
    authorize = AsyncMock()
    require_active = AsyncMock(return_value=SimpleNamespace(version=4))
    if not granted:
        authorize.side_effect = NotFoundError("Resource not found")
    monkeypatch.setattr(companion_service, "authorize_elder", authorize)
    monkeypatch.setattr(
        companion_service,
        "ConsentService",
        MagicMock(return_value=SimpleNamespace(require_active=require_active)),
    )
    return authorize, require_active


def _install_care_event_service(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    create_candidate = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(
        companion_service,
        "CareEventService",
        MagicMock(return_value=SimpleNamespace(create_candidate=create_candidate)),
    )
    return create_candidate


@pytest.mark.asyncio
async def test_voice_session_cannot_bypass_server_asr_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = _conversation(state="CREATED", input_mode="voice")
    _install_conversation_service(monkeypatch, conversation)
    runtime = SimpleNamespace(run=AsyncMock())

    with pytest.raises(ConflictError, match="not ready for Agent Runtime"):
        await CompanionService(MagicMock(), tenant_id, runtime, "mock").run_turn(
            conversation=conversation,
            actor_context=actor,
            input_text="must not reach Agent",
            correlation_id="correlation-voice",
            idempotency_key="voice-bypass",
            latency_budget_ms=3000,
        )

    runtime.run.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_turn_uses_core_owned_run_and_persists_proposal_after_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = _conversation()
    get_for_update, transition = _install_conversation_service(monkeypatch, conversation)
    authorize, require_active = _install_candidate_capability(monkeypatch)
    create_candidate = _install_care_event_service(monkeypatch)
    session = _session()
    runtime = SimpleNamespace(run=AsyncMock())

    async def run_runtime(*, request_payload, correlation_id):
        assert conversation.state == "PROCESSING"
        assert request_payload["actor_id"] == str(actor.actor_id)
        assert request_payload["tenant_id"] == str(tenant_id)
        assert request_payload["elder_id"] == str(conversation.elder_id)
        assert request_payload["allowed_tools"] == []
        assert request_payload["requested_outputs"] == ["event_candidate"]
        assert request_payload["request_id"] == (
            f"req-{uuid5(NAMESPACE_URL, 'kinsun:companion:turn-1')}"
        )
        assert request_payload["agent_run_id"] == (
            f"run-{uuid5(NAMESPACE_URL, 'kinsun:agent-run:turn-1')}"
        )
        assert correlation_id == "correlation-1"
        added = [item.args[0] for item in session.add.call_args_list]
        running = next(item for item in added if isinstance(item, AgentRun))
        assert running.result_status == "RUNNING"
        return _runtime_result(
            request_id=request_payload["request_id"],
            trace_id=conversation.trace_id,
            agent_run_id=request_payload["agent_run_id"],
            proposal=_proposal(),
        )

    async def persist_candidate(**kwargs):
        assert conversation.state == "COMPLETED"
        request = kwargs["request"]
        assert request.source_id == conversation.id
        assert request.event_type.value == "MEAL"
        assert request.review_requirement == "REQUIRED"
        return SimpleNamespace(id=uuid4())

    runtime.run.side_effect = run_runtime
    create_candidate.side_effect = persist_candidate

    result = await CompanionService(session, tenant_id, runtime, "mock").run_turn(
        conversation=conversation,
        actor_context=actor,
        input_text="這是合成的早餐分享。",
        correlation_id="correlation-1",
        idempotency_key="turn-1",
        latency_budget_ms=3000,
    )

    assert result.session_state == "COMPLETED"
    assert result.transport_status == "TEXT_ONLY"
    get_for_update.assert_awaited_once_with(conversation.id)
    assert [item.kwargs["target_state"] for item in transition.await_args_list] == [
        "RECORDING",
        "PROCESSING",
        "RESPONDING",
        "COMPLETED",
    ]
    assert authorize.await_count == 2
    require_active.assert_awaited_once()
    create_candidate.assert_awaited_once()
    added = [item.args[0] for item in session.add.call_args_list]
    agent_run = next(item for item in added if isinstance(item, AgentRun))
    assert agent_run.agent_run_id == result.agent_run_id
    assert agent_run.result_status == "SUCCESS"
    assert any(isinstance(item, SafetyEvaluation) for item in added)
    assert all("早餐分享" not in repr(item) for item in added)


@pytest.mark.asyncio
async def test_missing_candidate_scope_requests_no_output_and_ignores_unsolicited_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = _conversation()
    _install_conversation_service(monkeypatch, conversation)
    _install_candidate_capability(monkeypatch, granted=False)
    create_candidate = _install_care_event_service(monkeypatch)
    session = _session()

    async def run_runtime(*, request_payload, **_kwargs):
        assert request_payload["requested_outputs"] == []
        return _runtime_result(
            request_id=request_payload["request_id"],
            trace_id=conversation.trace_id,
            agent_run_id=request_payload["agent_run_id"],
            proposal=_proposal(),
        )

    runtime = SimpleNamespace(run=AsyncMock(side_effect=run_runtime))
    await CompanionService(session, tenant_id, runtime, "mock").run_turn(
        conversation=conversation,
        actor_context=actor,
        input_text="合成事件內容",
        correlation_id="correlation-1",
        idempotency_key="turn-1",
        latency_budget_ms=3000,
    )

    create_candidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_blocked_runtime_proposal_has_no_event_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = _conversation()
    _install_conversation_service(monkeypatch, conversation)
    _install_candidate_capability(monkeypatch)
    create_candidate = _install_care_event_service(monkeypatch)
    session = _session()

    async def run_runtime(*, request_payload, **_kwargs):
        return _runtime_result(
            request_id=request_payload["request_id"],
            trace_id=conversation.trace_id,
            agent_run_id=request_payload["agent_run_id"],
            proposal=_proposal(),
            decision="BLOCK",
            result_status="BLOCKED",
        )

    runtime = SimpleNamespace(run=AsyncMock(side_effect=run_runtime))
    await CompanionService(session, tenant_id, runtime, "mock").run_turn(
        conversation=conversation,
        actor_context=actor,
        input_text="合成安全阻擋內容",
        correlation_id="correlation-1",
        idempotency_key="turn-1",
        latency_budget_ms=3000,
    )

    create_candidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoked_scope_during_turn_drops_proposal_before_candidate_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = _conversation()
    _install_conversation_service(monkeypatch, conversation)
    authorize, _require_active = _install_candidate_capability(monkeypatch)
    authorize.side_effect = [None, NotFoundError("Resource not found")]
    create_candidate = _install_care_event_service(monkeypatch)
    session = _session()

    async def run_runtime(*, request_payload, **_kwargs):
        return _runtime_result(
            request_id=request_payload["request_id"],
            trace_id=conversation.trace_id,
            agent_run_id=request_payload["agent_run_id"],
            proposal=_proposal(),
        )

    runtime = SimpleNamespace(run=AsyncMock(side_effect=run_runtime))
    await CompanionService(session, tenant_id, runtime, "mock").run_turn(
        conversation=conversation,
        actor_context=actor,
        input_text="合成事件內容",
        correlation_id="correlation-1",
        idempotency_key="turn-1",
        latency_budget_ms=3000,
    )

    assert authorize.await_count == 2
    create_candidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_failure_leaves_only_running_agent_audit_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = ActorContext(actor_id=uuid4(), actor_role="ELDER", tenant_id=tenant_id)
    conversation = _conversation()
    _install_conversation_service(monkeypatch, conversation)
    _install_candidate_capability(monkeypatch)
    create_candidate = _install_care_event_service(monkeypatch)
    runtime = SimpleNamespace(
        run=AsyncMock(side_effect=ServiceUnavailableError("Agent runtime is unavailable"))
    )
    session = _session()

    with pytest.raises(ServiceUnavailableError):
        await CompanionService(session, tenant_id, runtime, "mock").run_turn(
            conversation=conversation,
            actor_context=actor,
            input_text="合成測試文字",
            correlation_id="correlation-1",
            idempotency_key="turn-1",
            latency_budget_ms=3000,
        )

    create_candidate.assert_not_awaited()
    added = [item.args[0] for item in session.add.call_args_list]
    assert len(added) == 1
    assert isinstance(added[0], AgentRun)
    assert added[0].result_status == "RUNNING"
    assert not any(isinstance(item, SafetyEvaluation) for item in added)

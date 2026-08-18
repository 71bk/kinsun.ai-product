"""Unit tests for Core-owned Tool execution replay and data-scope gates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.middleware.auth import ActorContext
from app.repositories.memory_repo import ConfirmedMemoryContextRecord
from app.schemas.tool import ToolRequest
from app.services import tool_service
from app.services.tool_service import ToolExecutionService


def _request(**updates: object) -> ToolRequest:
    payload: dict[str, object] = {
        "tool_call_id": uuid4(),
        "agent_run_id": uuid4(),
        "tool_name": "retrieve_confirmed_memory",
        "tool_version": "1.0",
        "elder_id": uuid4(),
        "purpose": "LONG_TERM_MEMORY",
        "consent_version": 1,
        "policy_version": "policy-v1",
        "request_id": "transport-request-1",
        "parameters": {"limit": 1},
    }
    payload.update(updates)
    return ToolRequest.model_validate(payload)


def _actor() -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="CARE_WORKER",
        tenant_id=uuid4(),
    )


def _existing_call(
    request: ToolRequest,
    actor: ActorContext,
    *,
    agent_run_id: UUID | None = None,
    request_payload: dict[str, object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        agent_run_id=agent_run_id or request.agent_run_id,
        actor_id=actor.actor_id,
        tool_name=request.tool_name,
        tool_version=request.tool_version,
        request_payload=request_payload
        or {
            "elder_id": str(request.elder_id),
            "purpose": request.purpose,
            "parameter_keys": sorted(request.parameters),
            "request_fingerprint": ToolExecutionService._request_fingerprint(request),
        },
        result_status="SUCCESS",
        response_payload={
            "result_status": "SUCCESS",
            "resource_id": str(uuid4()),
            "resource_version": 3,
            "source_refs": [str(uuid4())],
            "data": {"must_not": "be_replayed"},
            "redactions": ["must_not_be_replayed"],
        },
        reason_code=None,
        retryable=False,
        trace_id="original-tool-trace",
    )


def _session(*, existing_call: SimpleNamespace | None, run: object) -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=existing_call)
    session.scalar = AsyncMock(return_value=run)
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


def _install_live_gates(
    monkeypatch: pytest.MonkeyPatch,
    *,
    consent_result: object | BaseException = SimpleNamespace(version=1),
) -> tuple[AsyncMock, SimpleNamespace]:
    authorization = AsyncMock()
    consent = SimpleNamespace(require_active=AsyncMock())
    if isinstance(consent_result, BaseException):
        consent.require_active.side_effect = consent_result
    else:
        consent.require_active.return_value = consent_result
    monkeypatch.setattr(tool_service, "authorize_elder", authorization)
    monkeypatch.setattr(tool_service, "ConsentService", lambda *_args: consent)
    return authorization, consent


@pytest.mark.asyncio
async def test_replay_reauthorizes_without_replaying_sensitive_tool_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_request = _request()
    replay_request = original_request.model_copy(update={"request_id": "transport-request-2"})
    actor = _actor()
    existing_call = _existing_call(original_request, actor)
    session = _session(
        existing_call=existing_call,
        run=SimpleNamespace(policy_version=replay_request.policy_version),
    )
    authorization, consent = _install_live_gates(monkeypatch)
    service = ToolExecutionService(session, actor)
    dispatch = AsyncMock()
    service._dispatch = dispatch

    result = await service.execute(replay_request)

    assert result.result_status == "SUCCESS"
    assert result.data is None
    assert result.redactions == []
    assert result.resource_id == UUID(existing_call.response_payload["resource_id"])
    assert result.source_refs == [UUID(existing_call.response_payload["source_refs"][0])]
    assert result.trace_id == "original-tool-trace"
    authorization.assert_awaited_once_with(session, actor, replay_request.elder_id, "memory:read")
    consent.require_active.assert_awaited_once()
    dispatch.assert_not_awaited()
    session.add.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_replay_rejects_a_different_agent_run(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    actor = _actor()
    existing_call = _existing_call(request, actor, agent_run_id=uuid4())
    session = _session(
        existing_call=existing_call,
        run=SimpleNamespace(policy_version=request.policy_version),
    )
    authorization, _ = _install_live_gates(monkeypatch)

    with pytest.raises(ConflictError):
        await ToolExecutionService(session, actor).execute(request)

    authorization.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_replay_rejects_changed_parameter_value(monkeypatch: pytest.MonkeyPatch) -> None:
    original_request = _request()
    replay_request = original_request.model_copy(update={"parameters": {"limit": 2}})
    actor = _actor()
    existing_call = _existing_call(original_request, actor)
    session = _session(
        existing_call=existing_call,
        run=SimpleNamespace(policy_version=replay_request.policy_version),
    )
    authorization, _ = _install_live_gates(monkeypatch)

    with pytest.raises(ConflictError):
        await ToolExecutionService(session, actor).execute(replay_request)

    authorization.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_replay_fails_closed_for_legacy_call_without_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    actor = _actor()
    existing_call = _existing_call(
        request,
        actor,
        request_payload={
            "elder_id": str(request.elder_id),
            "purpose": request.purpose,
            "parameter_keys": sorted(request.parameters),
        },
    )
    session = _session(
        existing_call=existing_call,
        run=SimpleNamespace(policy_version=request.policy_version),
    )
    authorization, _ = _install_live_gates(monkeypatch)

    with pytest.raises(ConflictError):
        await ToolExecutionService(session, actor).execute(request)

    authorization.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_replay_fails_closed_when_current_actor_has_no_matching_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    actor = _actor()
    session = _session(existing_call=_existing_call(request, actor), run=None)
    authorization, _ = _install_live_gates(monkeypatch)

    with pytest.raises(NotFoundError):
        await ToolExecutionService(session, actor).execute(request)

    authorization.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_replay_does_not_bypass_revoked_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    request = _request()
    actor = _actor()
    session = _session(
        existing_call=_existing_call(request, actor),
        run=SimpleNamespace(policy_version=request.policy_version),
    )
    authorization, consent = _install_live_gates(
        monkeypatch,
        consent_result=NotFoundError("Required consent is not active"),
    )
    service = ToolExecutionService(session, actor)
    dispatch = AsyncMock()
    service._dispatch = dispatch

    with pytest.raises(NotFoundError):
        await service.execute(request)

    authorization.assert_awaited_once_with(session, actor, request.elder_id, "memory:read")
    consent.require_active.assert_awaited_once()
    dispatch.assert_not_awaited()
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_summary_tool_requests_only_ready_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(
        tool_name="retrieve_daily_summary",
        purpose="CARE_EVENT_EXTRACTION",
        parameters={},
    )
    actor = _actor()
    session = _session(
        existing_call=None, run=SimpleNamespace(policy_version=request.policy_version)
    )
    summaries = SimpleNamespace(
        list_for_date=AsyncMock(return_value=[]),
        get_version=AsyncMock(),
    )
    monkeypatch.setattr(tool_service, "SummaryService", lambda *_args: summaries)

    result = await ToolExecutionService(session, actor)._dispatch(request, "tool-trace")

    assert result.result_status == "NO_DATA"
    summaries.list_for_date.assert_awaited_once_with(
        elder_id=request.elder_id,
        summary_date=None,
        statuses=["READY"],
    )


@pytest.mark.asyncio
async def test_memory_tool_uses_only_the_final_trusted_context_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request(parameters={"limit": 2})
    actor = _actor()
    session = _session(
        existing_call=None,
        run=SimpleNamespace(policy_version=request.policy_version),
    )
    memory_id = uuid4()
    list_trusted_context = AsyncMock(
        return_value=[
            ConfirmedMemoryContextRecord(
                memory_id=memory_id,
                version=3,
                memory_type="PREFERENCE",
                content="Prefers classical music",
                consent_version=1,
            )
        ]
    )
    memory_service = SimpleNamespace(
        list_trusted_context=list_trusted_context,
        list_for_elder=AsyncMock(),
        get_version=AsyncMock(),
    )
    monkeypatch.setattr(tool_service, "MemoryService", lambda *_args: memory_service)

    result = await ToolExecutionService(session, actor)._dispatch(request, "tool-trace")

    assert result.result_status == "SUCCESS"
    assert result.data == [
        {
            "memory_id": str(memory_id),
            "memory_type": "PREFERENCE",
            "content": "Prefers classical music",
            "version": 3,
        }
    ]
    assert result.source_refs == [memory_id]
    list_trusted_context.assert_awaited_once_with(elder_id=request.elder_id, limit=2)
    memory_service.list_for_elder.assert_not_awaited()
    memory_service.get_version.assert_not_awaited()

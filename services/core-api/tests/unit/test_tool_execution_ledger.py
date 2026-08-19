"""Unit tests for fail-closed Tool execution replay ledger behavior."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.auth import ActorContext
from app.core.exceptions import ConflictError
from app.schemas.tool import ToolRequest, ToolResult
from app.services.tool_execution_ledger import ToolExecutionLedger


def _request() -> ToolRequest:
    return ToolRequest(
        tool_call_id=uuid4(),
        agent_run_id=uuid4(),
        tool_name="retrieve_confirmed_memory",
        tool_version="1.0",
        elder_id=uuid4(),
        purpose="LONG_TERM_MEMORY",
        consent_version=1,
        policy_version="policy-v1",
        request_id="transport-request-1",
        parameters={"limit": 1},
    )


def _actor() -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="CARE_WORKER",
        tenant_id=uuid4(),
    )


def _recorded_call(
    request: ToolRequest,
    actor: ActorContext,
    *,
    request_payload: object,
    response_payload: object | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        agent_run_id=request.agent_run_id,
        actor_id=actor.actor_id,
        tool_name=request.tool_name,
        tool_version=request.tool_version,
        request_payload=request_payload,
        response_payload=response_payload,
        reason_code=None,
        retryable=False,
        trace_id="original-tool-trace",
    )


@pytest.mark.asyncio
async def test_find_bound_run_scopes_all_execution_identity_predicates() -> None:
    request = _request()
    actor = _actor()
    expected_run = object()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=expected_run)

    result = await ToolExecutionLedger(session, actor).find_bound_run(request)

    assert result is expected_run
    statement = session.scalar.await_args.args[0]
    criteria = tuple(statement.whereclause.clauses)
    assert {criterion.left.key for criterion in criteria} == {
        "agent_run_id",
        "tenant_id",
        "elder_id",
        "actor_id",
    }
    assert set(statement.compile().params.values()) == {
        request.agent_run_id,
        actor.tenant_id,
        request.elder_id,
        actor.actor_id,
    }


@pytest.mark.asyncio
async def test_record_result_appends_minimized_scoped_audit_without_commit() -> None:
    request = _request().model_copy(
        update={
            "idempotency_key": "tool-idempotency-1",
            "parameters": {"limit": 2},
        }
    )
    actor = _actor()
    session = MagicMock()
    session.scalar = AsyncMock(return_value=request.idempotency_key)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    ledger = ToolExecutionLedger(session, actor)
    resource_id = uuid4()
    source_ref = uuid4()
    result = ToolResult(
        result_status="SUCCESS",
        data={"sensitive": "must not be persisted"},
        resource_id=resource_id,
        resource_version=4,
        source_refs=[source_ref],
        redactions=["sensitive"],
        trace_id="tool-trace",
    )

    recorded_result = await ledger.record_result(request=request, result=result)

    assert recorded_result is result
    idempotency_statement = session.scalar.await_args.args[0]
    criteria = tuple(idempotency_statement.whereclause.clauses)
    assert {criterion.left.key for criterion in criteria} == {
        "idempotency_key",
        "tenant_id",
        "actor_id",
    }
    assert set(idempotency_statement.compile().params.values()) == {
        request.idempotency_key,
        actor.tenant_id,
        actor.actor_id,
    }
    session.add.assert_called_once()
    audit_row = session.add.call_args.args[0]
    assert audit_row.tool_call_id == request.tool_call_id
    assert audit_row.agent_run_id == request.agent_run_id
    assert audit_row.actor_id == actor.actor_id
    assert audit_row.idempotency_key == request.idempotency_key
    assert audit_row.tool_name == request.tool_name
    assert audit_row.tool_version == request.tool_version
    assert audit_row.request_payload == {
        "elder_id": str(request.elder_id),
        "purpose": request.purpose,
        "parameter_keys": ["limit"],
        "request_fingerprint": ledger.request_fingerprint(request),
    }
    assert audit_row.response_payload == {
        "result_status": "SUCCESS",
        "resource_id": str(resource_id),
        "resource_version": 4,
        "source_refs": [str(source_ref)],
    }
    assert audit_row.result_status == "SUCCESS"
    assert audit_row.reason_code is None
    assert audit_row.retryable is False
    assert audit_row.trace_id == "tool-trace"
    session.flush.assert_awaited_once_with()
    session.commit.assert_not_awaited()


def test_replay_validation_fails_closed_without_semantic_fingerprint() -> None:
    request = _request()
    actor = _actor()
    ledger = ToolExecutionLedger(MagicMock(), actor)
    recorded_call = _recorded_call(
        request,
        actor,
        request_payload={
            "elder_id": str(request.elder_id),
            "purpose": request.purpose,
            "parameter_keys": sorted(request.parameters),
        },
    )

    with pytest.raises(ConflictError):
        ledger.validate_replay_request(recorded_call, request)


def test_replay_validation_fails_closed_for_a_different_actor() -> None:
    request = _request()
    actor = _actor()
    ledger = ToolExecutionLedger(MagicMock(), actor)
    recorded_call = _recorded_call(
        request,
        actor,
        request_payload={
            "elder_id": str(request.elder_id),
            "purpose": request.purpose,
            "parameter_keys": sorted(request.parameters),
            "request_fingerprint": ledger.request_fingerprint(request),
        },
    )
    recorded_call.actor_id = uuid4()

    with pytest.raises(ConflictError):
        ledger.validate_replay_request(recorded_call, request)


@pytest.mark.parametrize(
    "response_payload",
    [None, {"result_status": "UNKNOWN"}],
)
def test_replay_result_fails_closed_for_invalid_persisted_payload(
    response_payload: object,
) -> None:
    request = _request()
    actor = _actor()
    recorded_call = _recorded_call(
        request,
        actor,
        request_payload={},
        response_payload=response_payload,
    )

    with pytest.raises(ConflictError):
        ToolExecutionLedger.replayed_result(recorded_call)

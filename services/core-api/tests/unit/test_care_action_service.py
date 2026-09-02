"""Care Action scope, source, transition, and audit tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import app.services.care_action_service as service_module
from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.care_action import CareAction
from app.schemas.care_action import CreateCareActionRequest, UpdateCareActionRequest
from app.services.care_action_service import CareActionService


def _actor(role: str = "DAYCARE_CARE_WORKER") -> ActorContext:
    return ActorContext(actor_id=uuid4(), actor_role=role, tenant_id=uuid4())


def _create_request(actor_id=None) -> CreateCareActionRequest:
    return CreateCareActionRequest(
        action_type="CONTACT_ELDER",
        title="關心早餐狀況",
        description="確認最近幾天早餐是否正常",
        trigger_reason="已覆核早餐事件需要後續確認",
        related_event_ids=[uuid4()],
        assignee_actor_id=actor_id,
        due_at=datetime.now(UTC) + timedelta(days=1),
        priority="MEDIUM",
    )


@pytest.mark.asyncio
async def test_create_binds_to_professional_and_formal_same_elder_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    session = SimpleNamespace(scalar=AsyncMock(return_value=1), flush=AsyncMock())
    added: list[CareAction] = []

    class Actions:
        def add(self, action: CareAction) -> None:
            action.id = uuid4()
            added.append(action)

    outbox = AsyncMock()
    monkeypatch.setattr(service_module, "write_outbox_entry", outbox)
    service = CareActionService(session, actor.tenant_id)
    service._actions = Actions()  # type: ignore[assignment]
    request = _create_request()

    action = await service.create(
        elder_id=uuid4(),
        actor_context=actor,
        request=request,
        trace_id="trace-care-action-create",
        idempotency_key="idem-care-action-create",
    )

    assert action.assignee_actor_id == actor.actor_id
    assert action.created_by_actor_id == actor.actor_id
    assert action.status == "OPEN"
    assert action.related_event_ids == request.related_event_ids
    outbox.assert_awaited_once()
    assert outbox.await_args.kwargs["payload"]["status"] == "OPEN"
    assert "title" not in outbox.await_args.kwargs["payload"]


@pytest.mark.asyncio
async def test_create_rejects_cross_scope_or_unreviewed_source_events() -> None:
    actor = _actor()
    session = SimpleNamespace(scalar=AsyncMock(return_value=0), flush=AsyncMock())
    service = CareActionService(session, actor.tenant_id)

    with pytest.raises(ValidationError) as caught:
        await service.create(
            elder_id=uuid4(),
            actor_context=actor,
            request=_create_request(),
            trace_id="trace-care-action-denied",
            idempotency_key="idem-care-action-denied",
        )

    assert caught.value.details == [
        {
            "field": "related_event_ids",
            "reason": "Care Actions require formal events from the same Elder scope",
        }
    ]


@pytest.mark.asyncio
async def test_create_rejects_non_professional_actor_before_writing() -> None:
    actor = _actor("FAMILY_MEMBER")
    session = SimpleNamespace(scalar=AsyncMock(), flush=AsyncMock())
    service = CareActionService(session, actor.tenant_id)

    with pytest.raises(NotFoundError):
        await service.create(
            elder_id=uuid4(),
            actor_context=actor,
            request=_create_request(),
            trace_id="trace-family-denied",
            idempotency_key="idem-family-denied",
        )

    session.scalar.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_transition_uses_optimistic_version_and_preserves_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    action = CareAction(
        id=uuid4(),
        tenant_id=actor.tenant_id,
        elder_id=uuid4(),
        action_type="FOLLOW_UP",
        title="後續追蹤",
        trigger_reason="已覆核事件",
        related_event_ids=[uuid4()],
        assignee_actor_id=actor.actor_id,
        due_at=datetime.now(UTC) + timedelta(days=1),
        priority="LOW",
        status="OPEN",
        created_by_actor_id=actor.actor_id,
        version=1,
    )
    outbox = AsyncMock()

    async def optimistic(_session, instance, expected_version) -> None:
        instance.version = expected_version + 1

    monkeypatch.setattr(CareAction, "apply_optimistic_update", optimistic)
    monkeypatch.setattr(service_module, "write_outbox_entry", outbox)
    service = CareActionService(session, actor.tenant_id)

    updated = await service.transition(
        action=action,
        actor_context=actor,
        request=UpdateCareActionRequest(
            status="COMPLETED",
            expected_version=1,
            resolution="已電話關心並完成確認",
        ),
        trace_id="trace-care-action-complete",
        idempotency_key="idem-care-action-complete",
    )

    assert updated.status == "COMPLETED"
    assert updated.version == 2
    assert updated.resolution == "已電話關心並完成確認"
    assert outbox.await_args.kwargs["event_type"] == "care.action.completed.v1"


@pytest.mark.asyncio
async def test_terminal_action_cannot_be_reopened() -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    action = SimpleNamespace(
        assignee_actor_id=actor.actor_id,
        status="COMPLETED",
        version=2,
    )
    service = CareActionService(session, actor.tenant_id)

    with pytest.raises(ConflictError, match="Invalid care_action state transition"):
        await service.transition(
            action=action,
            actor_context=actor,
            request=UpdateCareActionRequest(status="IN_PROGRESS", expected_version=2),
            trace_id="trace-care-action-reopen",
            idempotency_key="idem-care-action-reopen",
        )

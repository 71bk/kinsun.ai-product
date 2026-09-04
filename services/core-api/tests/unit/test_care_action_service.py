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


def _formal_source(event_id, *, status: str = "VERIFIED", payload=None):
    event_version_id = uuid4()
    event = SimpleNamespace(
        id=event_id,
        current_version=1,
        event_type="MEAL",
        event_time=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
        status=status,
    )
    version = SimpleNamespace(
        event_version_id=event_version_id,
        version=1,
        structured_payload=payload or {"meal": "breakfast", "reported": True},
        evidence_text_ref='["evidence:71000000-0000-4000-8000-000000000001"]',
    )
    return event, version


@pytest.mark.asyncio
async def test_create_binds_to_professional_and_formal_same_elder_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
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
    event, event_version = _formal_source(request.related_event_ids[0])
    service._events = SimpleNamespace(
        list_formal_current_versions_for_update=AsyncMock(return_value=[(event, event_version)])
    )

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
    assert len(action.source_event_provenance) == 1
    provenance = action.source_event_provenance[0]
    assert provenance.event_id == event.id
    assert provenance.event_version_id == event_version.event_version_id
    assert provenance.event_version == 1
    assert provenance.source_status == "VERIFIED"
    assert len(provenance.snapshot_sha256) == 64
    outbox.assert_awaited_once()
    assert outbox.await_args.kwargs["payload"]["status"] == "OPEN"
    assert outbox.await_args.kwargs["payload"]["source_event_provenance"] == [
        {
            "event_id": str(event.id),
            "event_version_id": str(event_version.event_version_id),
            "event_version": 1,
            "snapshot_sha256": provenance.snapshot_sha256,
            "snapshot_schema_version": "care-event-provenance.v1",
        }
    ]
    assert "title" not in outbox.await_args.kwargs["payload"]


@pytest.mark.asyncio
async def test_create_rejects_cross_scope_or_unreviewed_source_events() -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    service = CareActionService(session, actor.tenant_id)
    service._events = SimpleNamespace(
        list_formal_current_versions_for_update=AsyncMock(return_value=[])
    )

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
async def test_candidate_adoption_rejects_source_event_version_drift() -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    service = CareActionService(session, actor.tenant_id)
    request = _create_request()
    event, event_version = _formal_source(request.related_event_ids[0])
    event_version.version = 2
    service._events = SimpleNamespace(
        list_formal_current_versions_for_update=AsyncMock(return_value=[(event, event_version)])
    )

    with pytest.raises(ConflictError, match="candidate source event changed"):
        await service.create(
            elder_id=uuid4(),
            actor_context=actor,
            request=request,
            trace_id="trace-care-action-stale-candidate",
            idempotency_key="idem-care-action-stale-candidate",
            expected_source_versions={event.id: 1},
        )

    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_rejects_non_professional_actor_before_writing() -> None:
    actor = _actor("FAMILY_MEMBER")
    session = SimpleNamespace(flush=AsyncMock())
    service = CareActionService(session, actor.tenant_id)
    source_lookup = AsyncMock()
    service._events = SimpleNamespace(list_formal_current_versions_for_update=source_lookup)

    with pytest.raises(NotFoundError):
        await service.create(
            elder_id=uuid4(),
            actor_context=actor,
            request=_create_request(),
            trace_id="trace-family-denied",
            idempotency_key="idem-family-denied",
        )

    source_lookup.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_captured_provenance_survives_later_source_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    request = _create_request()
    event, event_version = _formal_source(request.related_event_ids[0])
    service = CareActionService(session, actor.tenant_id)
    service._events = SimpleNamespace(
        list_formal_current_versions_for_update=AsyncMock(return_value=[(event, event_version)])
    )

    class Actions:
        def add(self, action: CareAction) -> None:
            action.id = uuid4()

    service._actions = Actions()  # type: ignore[assignment]
    monkeypatch.setattr(service_module, "write_outbox_entry", AsyncMock())

    action = await service.create(
        elder_id=uuid4(),
        actor_context=actor,
        request=request,
        trace_id="trace-care-action-provenance",
        idempotency_key="idem-care-action-provenance",
    )
    captured = action.source_event_provenance[0]
    original = (
        captured.event_version_id,
        captured.event_version,
        captured.event_type,
        captured.event_time,
        captured.source_status,
        captured.snapshot_sha256,
    )

    event.current_version = 2
    event.event_type = "ACTIVITY"
    event.event_time = datetime(2026, 9, 3, 1, 0, tzinfo=UTC)
    event.status = "CORRECTED"
    event_version.event_version_id = uuid4()
    event_version.version = 2
    event_version.structured_payload = {"activity": "walk"}

    assert (
        captured.event_version_id,
        captured.event_version,
        captured.event_type,
        captured.event_time,
        captured.source_status,
        captured.snapshot_sha256,
    ) == original


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

"""Care-event API serialization and formal-read safety tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from app.api import care_events
from app.api.care_events import _response
from app.core.exceptions import NotFoundError
from app.middleware.auth import ActorContext


def _actor() -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_care_event_response_filters_non_opaque_evidence_references() -> None:
    valid_reference = f"evidence:{uuid4()}"
    event = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        event_type="MEAL",
        event_time=None,
        status="NEEDS_REVIEW",
        current_version=1,
        consent_version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    version = SimpleNamespace(
        structured_payload={"meal_status": "mentioned"},
        evidence_text_ref=json.dumps(
            [
                valid_reference,
                "raw transcript must not be returned from evidence storage",
            ]
        ),
        confidence=Decimal("0.6000"),
    )
    service = SimpleNamespace(get_version=AsyncMock(return_value=version))

    response = await _response(service, event)

    assert response.evidence_refs == [valid_reference]


@pytest.mark.asyncio
async def test_list_care_events_defaults_to_formal_statuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(list_for_elder=AsyncMock(return_value=[]))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    await care_events.list_care_events(
        elder_id=elder_id,
        event_status=None,
        cursor=None,
        limit=50,
        actor_context=actor,
        session=session,
    )

    authorize.assert_awaited_once_with(session, actor, elder_id, "care_event:read")
    service.list_for_elder.assert_awaited_once_with(
        elder_id=elder_id,
        statuses=list(care_events.FORMAL_CARE_EVENT_STATUSES),
        limit=50,
        cursor=None,
    )


@pytest.mark.asyncio
async def test_list_care_events_requires_review_scope_for_non_formal_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(list_for_elder=AsyncMock(return_value=[]))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    await care_events.list_care_events(
        elder_id=elder_id,
        event_status=["NEEDS_REVIEW"],
        cursor=None,
        limit=50,
        actor_context=actor,
        session=session,
    )

    assert authorize.await_args_list == [
        call(session, actor, elder_id, "care_event:read"),
        call(session, actor, elder_id, "care_event:review"),
    ]
    service.list_for_elder.assert_awaited_once_with(
        elder_id=elder_id,
        statuses=["NEEDS_REVIEW"],
        limit=50,
        cursor=None,
    )


@pytest.mark.asyncio
async def test_get_care_event_does_not_read_non_formal_event_before_review_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    event_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock(
        side_effect=[None, NotFoundError("Resource not found")],
    )
    service = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    with pytest.raises(NotFoundError):
        await care_events.get_care_event(
            elder_id=elder_id,
            event_id=event_id,
            actor_context=actor,
            session=session,
        )

    assert authorize.await_args_list == [
        call(session, actor, elder_id, "care_event:read"),
        call(session, actor, elder_id, "care_event:review"),
    ]
    service.get.assert_awaited_once_with(
        elder_id,
        event_id,
        statuses=list(care_events.FORMAL_CARE_EVENT_STATUSES),
    )


@pytest.mark.asyncio
async def test_get_care_event_reviewer_fallback_excludes_deleted_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    elder_id = uuid4()
    event_id = uuid4()
    actor = _actor()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(get=AsyncMock(side_effect=[None, None]))
    monkeypatch.setattr(care_events, "authorize_elder", authorize)
    monkeypatch.setattr(care_events, "CareEventService", MagicMock(return_value=service))

    with pytest.raises(NotFoundError):
        await care_events.get_care_event(
            elder_id=elder_id,
            event_id=event_id,
            actor_context=actor,
            session=session,
        )

    assert service.get.await_args_list == [
        call(
            elder_id,
            event_id,
            statuses=list(care_events.FORMAL_CARE_EVENT_STATUSES),
        ),
        call(
            elder_id,
            event_id,
            statuses=list(care_events.REVIEWABLE_CARE_EVENT_STATUSES),
        ),
    ]
    assert "DELETED" not in care_events.REVIEWABLE_CARE_EVENT_STATUSES

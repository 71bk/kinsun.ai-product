"""Care Action API authorization and bounded-list tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api import care_actions
from app.core.auth import ActorContext
from app.repositories.idempotency_repo import IdempotencyResult
from app.schemas.care_action import UpdateCareActionRequest


def _actor() -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_list_reauthorizes_elder_scope_and_uses_opaque_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    elder_id = uuid4()
    session = MagicMock()
    authorize = AsyncMock()
    service = SimpleNamespace(
        require_professional=MagicMock(),
        list_for_elder=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(care_actions, "authorize_elder", authorize)
    monkeypatch.setattr(care_actions, "CareActionService", MagicMock(return_value=service))

    response = await care_actions.list_care_actions(
        elder_id=elder_id,
        action_status=["OPEN", "IN_PROGRESS"],
        cursor=None,
        limit=25,
        actor_context=actor,
        session=session,
    )

    authorize.assert_awaited_once_with(session, actor, elder_id, "care_action:read")
    service.require_professional.assert_called_once_with(actor)
    service.list_for_elder.assert_awaited_once_with(
        elder_id=elder_id,
        statuses=["OPEN", "IN_PROGRESS"],
        limit=25,
        cursor=None,
    )
    assert response["data"]["items"] == []
    assert response["data"]["next_cursor"] is None
    assert response["data"]["has_more"] is False


@pytest.mark.asyncio
async def test_update_replays_immutable_snapshot_without_reloading_mutated_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    elder_id = uuid4()
    action_id = uuid4()
    session = MagicMock()
    snapshot = {
        "care_action_id": str(action_id),
        "elder_id": str(elder_id),
        "status": "COMPLETED",
        "version": 2,
    }
    authorize = AsyncMock()
    repository = SimpleNamespace(
        begin=AsyncMock(
            return_value=IdempotencyResult(
                replayed=True,
                resource_type="care_action",
                resource_id=action_id,
                response_status=200,
                response_body=snapshot,
            )
        )
    )
    service = SimpleNamespace(
        require_professional=MagicMock(),
        get=AsyncMock(),
    )
    monkeypatch.setattr(care_actions, "authorize_elder", authorize)
    monkeypatch.setattr(care_actions, "IdempotencyRepository", MagicMock(return_value=repository))
    monkeypatch.setattr(care_actions, "CareActionService", MagicMock(return_value=service))

    response = await care_actions.update_care_action(
        request=UpdateCareActionRequest(
            status="COMPLETED",
            expected_version=1,
            resolution="Follow-up completed",
        ),
        elder_id=elder_id,
        care_action_id=action_id,
        idempotency_key="same-request",
        actor_context=actor,
        session=session,
    )

    assert response["data"] == snapshot
    authorize.assert_awaited_once_with(session, actor, elder_id, "care_action:update")
    service.require_professional.assert_called_once_with(actor)
    service.get.assert_not_awaited()

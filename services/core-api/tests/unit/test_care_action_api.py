"""Care Action API authorization and bounded-list tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api import care_actions
from app.core.auth import ActorContext


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

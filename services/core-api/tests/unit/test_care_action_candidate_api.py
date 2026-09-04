"""Care Action candidate API authorization and idempotency tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.api import care_action_candidates
from app.core.auth import ActorContext
from app.repositories.idempotency_repo import IdempotencyResult
from app.schemas.care_action import (
    AdoptCareActionCandidateRequest,
    DismissCareActionCandidateRequest,
)


def _actor() -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_list_reauthorizes_scope_and_defaults_to_pending(
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
    monkeypatch.setattr(care_action_candidates, "authorize_elder", authorize)
    monkeypatch.setattr(
        care_action_candidates,
        "CareActionCandidateService",
        MagicMock(return_value=service),
    )

    response = await care_action_candidates.list_care_action_candidates(
        elder_id=elder_id,
        candidate_status=None,
        cursor=None,
        limit=25,
        actor_context=actor,
        session=session,
    )

    authorize.assert_awaited_once_with(session, actor, elder_id, "care_action:read")
    service.require_professional.assert_called_once_with(actor)
    service.list_for_elder.assert_awaited_once_with(
        elder_id=elder_id,
        statuses=["PENDING_REVIEW"],
        limit=25,
        cursor=None,
    )
    assert response["data"] == {"items": [], "next_cursor": None, "has_more": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["adopt", "dismiss"])
async def test_decision_replay_returns_immutable_snapshot_without_second_write(
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    actor = _actor()
    elder_id = uuid4()
    candidate_id = uuid4()
    session = MagicMock()
    snapshot = {
        "care_action_candidate_id": str(candidate_id),
        "elder_id": str(elder_id),
        "status": "ADOPTED" if operation == "adopt" else "REJECTED",
        "version": 2,
    }
    repository = SimpleNamespace(
        begin=AsyncMock(
            return_value=IdempotencyResult(
                replayed=True,
                resource_type="care_action_candidate",
                resource_id=candidate_id,
                response_status=200,
                response_body=snapshot,
            )
        )
    )
    service = SimpleNamespace(
        require_professional=MagicMock(),
        get=AsyncMock(),
        adopt=AsyncMock(),
        dismiss=AsyncMock(),
    )
    monkeypatch.setattr(care_action_candidates, "authorize_elder", AsyncMock())
    monkeypatch.setattr(
        care_action_candidates,
        "IdempotencyRepository",
        MagicMock(return_value=repository),
    )
    monkeypatch.setattr(
        care_action_candidates,
        "CareActionCandidateService",
        MagicMock(return_value=service),
    )

    if operation == "adopt":
        response = await care_action_candidates.adopt_care_action_candidate(
            request=AdoptCareActionCandidateRequest(expected_version=1),
            elder_id=elder_id,
            candidate_id=candidate_id,
            idempotency_key="same-candidate-decision",
            actor_context=actor,
            session=session,
        )
    else:
        response = await care_action_candidates.dismiss_care_action_candidate(
            request=DismissCareActionCandidateRequest(
                decision="REJECT",
                expected_version=1,
                reason_code="NOT_NEEDED",
            ),
            elder_id=elder_id,
            candidate_id=candidate_id,
            idempotency_key="same-candidate-decision",
            actor_context=actor,
            session=session,
        )

    assert response["data"] == snapshot
    service.get.assert_not_awaited()
    service.adopt.assert_not_awaited()
    service.dismiss.assert_not_awaited()

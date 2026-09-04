from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.middleware.auth import ActorContext
from app.schemas.care_event import ReviewCareEventRequest
from app.services import care_event_service
from app.services.care_event_service import CareEventService


def _actor(tenant_id):
    return ActorContext(
        actor_id=uuid4(),
        actor_role="FAMILY_MEMBER",
        tenant_id=tenant_id,
    )


def _proposal() -> dict:
    return {
        "memory_type": "ROUTINE",
        "memory_kind": "DAILY_ROUTINE",
        "normalized_content": "每天早餐習慣吃粥。",
        "confirmation_question": "要記住您每天早餐習慣吃粥嗎？",
        "extraction_confidence": 0.9,
        "proposal_risk_hint": "MEDIUM",
        "extractor_version": "memory-extractor-v1",
    }


@pytest.mark.asyncio
async def test_verify_promotes_private_proposal_after_event_becomes_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = _actor(tenant_id)
    event = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        status="NEEDS_REVIEW",
        current_version=1,
        consent_version=2,
    )
    version = SimpleNamespace(
        memory_candidate_proposal=_proposal(),
        care_action_candidate_proposal=None,
    )
    repository = SimpleNamespace(
        get_current_version=AsyncMock(return_value=version),
        add_review=MagicMock(),
    )
    session = MagicMock()
    session.flush = AsyncMock()
    service = CareEventService(session, tenant_id)
    service._events = repository
    promote = AsyncMock()
    service._promote_memory_candidate = promote
    require_active = AsyncMock(return_value=SimpleNamespace(version=2))
    monkeypatch.setattr(
        care_event_service,
        "ConsentService",
        MagicMock(return_value=SimpleNamespace(require_active=require_active)),
    )
    monkeypatch.setattr(care_event_service, "write_outbox_entry", AsyncMock())

    await service.review(
        event=event,
        actor_context=actor,
        request=ReviewCareEventRequest(
            decision="VERIFY",
            reason_code="SOURCE_CONFIRMED",
            expected_version=1,
        ),
        trace_id="trace-review-1",
        idempotency_key="review-1",
    )

    assert event.status == "VERIFIED"
    promote.assert_awaited_once()
    assert promote.await_args.kwargs["proposal"] == _proposal()
    assert promote.await_args.kwargs["actor_context"] is actor


@pytest.mark.asyncio
async def test_promotion_reauthorizes_and_binds_core_owned_source_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = _actor(tenant_id)
    event = SimpleNamespace(id=uuid4(), elder_id=uuid4())
    authorize = AsyncMock()
    create_candidate = AsyncMock()
    session = MagicMock()
    monkeypatch.setattr(care_event_service, "authorize_elder", authorize)
    monkeypatch.setattr(
        care_event_service,
        "MemoryService",
        MagicMock(return_value=SimpleNamespace(create_candidate=create_candidate)),
    )

    await CareEventService(session, tenant_id)._promote_memory_candidate(
        event=event,
        actor_context=actor,
        proposal=_proposal(),
        trace_id="trace-promote-1",
        idempotency_key="memory-promote-1",
    )

    authorize.assert_awaited_once_with(
        session,
        actor,
        event.elder_id,
        "memory:candidate:create",
    )
    request = create_candidate.await_args.kwargs["request"]
    assert request.source_event_ids == [event.id]
    assert request.memory_type.value == "ROUTINE"
    assert request.memory_kind.value == "DAILY_ROUTINE"
    assert request.extraction_confidence == 0.9
    assert request.proposal_risk_hint.value == "MEDIUM"
    assert create_candidate.await_args.kwargs["actor_id"] == actor.actor_id


@pytest.mark.asyncio
async def test_revoked_memory_gate_does_not_block_event_review_or_write_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = _actor(tenant_id)
    event = SimpleNamespace(id=uuid4(), elder_id=uuid4())
    create_candidate = AsyncMock()
    monkeypatch.setattr(
        care_event_service,
        "authorize_elder",
        AsyncMock(side_effect=NotFoundError("Resource not found")),
    )
    monkeypatch.setattr(
        care_event_service,
        "MemoryService",
        MagicMock(return_value=SimpleNamespace(create_candidate=create_candidate)),
    )

    await CareEventService(MagicMock(), tenant_id)._promote_memory_candidate(
        event=event,
        actor_context=actor,
        proposal=_proposal(),
        trace_id="trace-promote-closed",
        idempotency_key="memory-promote-closed",
    )

    create_candidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_verify_promotes_action_proposal_only_after_event_becomes_formal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    actor = _actor(tenant_id)
    event = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        status="NEEDS_REVIEW",
        current_version=1,
        consent_version=2,
    )
    proposal = {
        "action_type": "CONTACT_FAMILY",
        "suggested_title": "確認預期聯繫狀況",
        "trigger_reason": "預期聯繫未發生，需要由照護者確認。",
        "suggested_due_at": "2026-09-05T06:00:00+00:00",
        "priority": "MEDIUM",
        "extractor_version": "care-action-candidate-v1",
    }
    version = SimpleNamespace(
        memory_candidate_proposal=None,
        care_action_candidate_proposal=proposal,
    )
    repository = SimpleNamespace(
        get_current_version=AsyncMock(return_value=version),
        add_review=MagicMock(),
    )
    session = MagicMock()
    session.flush = AsyncMock()
    service = CareEventService(session, tenant_id)
    service._events = repository
    promote = AsyncMock()
    service._promote_care_action_candidate = promote
    monkeypatch.setattr(
        care_event_service,
        "ConsentService",
        MagicMock(
            return_value=SimpleNamespace(
                require_active=AsyncMock(return_value=SimpleNamespace(version=2))
            )
        ),
    )
    monkeypatch.setattr(care_event_service, "write_outbox_entry", AsyncMock())

    await service.review(
        event=event,
        actor_context=actor,
        request=ReviewCareEventRequest(
            decision="VERIFY",
            reason_code="SOURCE_CONFIRMED",
            expected_version=1,
        ),
        trace_id="trace-action-candidate-review",
        idempotency_key="action-candidate-review",
    )

    assert event.status == "VERIFIED"
    promote.assert_awaited_once_with(
        event=event,
        event_version=version,
        proposal=proposal,
    )

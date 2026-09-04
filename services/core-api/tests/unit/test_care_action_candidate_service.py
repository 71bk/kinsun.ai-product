"""Human-gated Care Action candidate lifecycle tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.services.care_action_candidate_service as service_module
from app.core.auth import ActorContext
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.care_action_candidate import CareActionCandidate
from app.schemas.care_action import (
    AdoptCareActionCandidateRequest,
    DismissCareActionCandidateRequest,
)
from app.services.care_action_candidate_service import CareActionCandidateService


def _actor(role: str = "DAYCARE_CARE_WORKER") -> ActorContext:
    return ActorContext(actor_id=uuid4(), actor_role=role, tenant_id=uuid4())


def _proposal(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "action_type": "CONTACT_FAMILY",
        "suggested_title": "確認預期聯繫狀況",
        "trigger_reason": "預期聯繫未發生，需要由照護者確認。",
        "suggested_due_at": datetime.now(UTC) + timedelta(days=1),
        "priority": "MEDIUM",
        "extractor_version": "care-action-candidate-v1",
    }
    values.update(overrides)
    return values


def _source(*, status: str = "VERIFIED", current_version: int = 1):
    event_id = uuid4()
    event = SimpleNamespace(
        id=event_id,
        elder_id=uuid4(),
        status=status,
        current_version=current_version,
        event_type="EXPECTED_CONTACT_MISSED",
        event_time=datetime(2026, 9, 4, 5, 0, tzinfo=UTC),
    )
    version = SimpleNamespace(
        event_version_id=uuid4(),
        version=1,
        structured_payload={"contact_status": "MISSED"},
        evidence_text_ref='["evidence:71000000-0000-4000-8000-000000000001"]',
    )
    return event, version


def _pending_candidate(actor: ActorContext) -> SimpleNamespace:
    event, version = _source()
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=actor.tenant_id,
        elder_id=event.elder_id,
        action_type="CONTACT_FAMILY",
        suggested_title="確認預期聯繫狀況",
        trigger_reason="預期聯繫未發生，需要由照護者確認。",
        suggested_due_at=datetime.now(UTC) + timedelta(days=1),
        priority="MEDIUM",
        status="PENDING_REVIEW",
        extractor_version="care-action-candidate-v1",
        version=1,
        source_event_provenance=[
            SimpleNamespace(
                event_id=event.id,
                event_version_id=version.event_version_id,
                event_version=version.version,
            )
        ],
    )


@pytest.mark.asyncio
async def test_verified_event_creates_candidate_with_immutable_source_snapshot() -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    added: list[CareActionCandidate] = []
    service = CareActionCandidateService(session, actor.tenant_id)
    service._candidates = SimpleNamespace(add=added.append)
    event, version = _source()

    candidate = await service.create_from_verified_event(
        event=event,
        event_version=version,
        proposal_payload=_proposal(),
    )

    assert added == [candidate]
    assert candidate.status == "PENDING_REVIEW"
    assert candidate.elder_id == event.elder_id
    assert candidate.adopted_care_action_id is None
    assert len(candidate.source_event_provenance) == 1
    provenance = candidate.source_event_provenance[0]
    assert provenance.event_id == event.id
    assert provenance.event_version_id == version.event_version_id
    assert provenance.event_version == 1
    assert provenance.snapshot_schema_version == "care-event-provenance.v1"
    assert len(provenance.snapshot_sha256) == 64


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "current_version"),
    [("NEEDS_REVIEW", 1), ("VERIFIED", 2)],
)
async def test_candidate_requires_current_formal_source(
    status: str,
    current_version: int,
) -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    service = CareActionCandidateService(session, actor.tenant_id)
    event, version = _source(status=status, current_version=current_version)

    with pytest.raises(ValidationError):
        await service.create_from_verified_event(
            event=event,
            event_version=version,
            proposal_payload=_proposal(),
        )

    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_adopt_is_the_only_path_that_creates_formal_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    candidate = _pending_candidate(actor)
    action = SimpleNamespace(id=uuid4())
    create_action = AsyncMock(return_value=action)

    async def optimistic(_session, instance, expected_version) -> None:
        instance.version = expected_version + 1

    monkeypatch.setattr(CareActionCandidate, "apply_optimistic_update", optimistic)
    monkeypatch.setattr(
        service_module,
        "CareActionService",
        MagicMock(return_value=SimpleNamespace(create=create_action)),
    )

    updated, created = await CareActionCandidateService(
        session,
        actor.tenant_id,
    ).adopt(
        candidate=candidate,
        actor_context=actor,
        request=AdoptCareActionCandidateRequest(expected_version=1),
        trace_id="trace-adopt-candidate",
        idempotency_key="idem-adopt-candidate",
    )

    assert created is action
    assert updated.status == "ADOPTED"
    assert updated.version == 2
    assert updated.adopted_care_action_id == action.id
    assert updated.disposition_reason_code == "HUMAN_CONFIRMED"
    call = create_action.await_args.kwargs
    assert call["actor_context"] is actor
    assert call["request"].related_event_ids == [candidate.source_event_provenance[0].event_id]
    assert call["expected_source_versions"] == {candidate.source_event_provenance[0].event_id: 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [("REJECT", "REJECTED"), ("EXCLUDE", "EXCLUDED")],
)
async def test_dismiss_records_human_reason_without_creating_formal_action(
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    expected_status: str,
) -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    candidate = _pending_candidate(actor)
    create_action = AsyncMock()

    async def optimistic(_session, instance, expected_version) -> None:
        instance.version = expected_version + 1

    monkeypatch.setattr(CareActionCandidate, "apply_optimistic_update", optimistic)
    monkeypatch.setattr(
        service_module,
        "CareActionService",
        MagicMock(return_value=SimpleNamespace(create=create_action)),
    )

    updated = await CareActionCandidateService(session, actor.tenant_id).dismiss(
        candidate=candidate,
        actor_context=actor,
        request=DismissCareActionCandidateRequest(
            decision=decision,
            expected_version=1,
            reason_code="NOT_NEEDED",
            notes="照護者已直接確認。",
        ),
    )

    assert updated.status == expected_status
    assert updated.version == 2
    assert updated.disposition_reason_code == "NOT_NEEDED"
    assert updated.disposition_notes == "照護者已直接確認。"
    assert updated.adopted_care_action_id is None
    create_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_family_member_cannot_decide_candidate() -> None:
    actor = _actor("FAMILY_MEMBER")
    candidate = _pending_candidate(actor)
    session = SimpleNamespace(flush=AsyncMock())

    with pytest.raises(NotFoundError):
        await CareActionCandidateService(session, actor.tenant_id).dismiss(
            candidate=candidate,
            actor_context=actor,
            request=DismissCareActionCandidateRequest(
                decision="REJECT",
                expected_version=1,
                reason_code="NOT_NEEDED",
            ),
        )

    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_terminal_or_stale_candidate_cannot_be_decided_again() -> None:
    actor = _actor()
    session = SimpleNamespace(flush=AsyncMock())
    service = CareActionCandidateService(session, actor.tenant_id)
    terminal = _pending_candidate(actor)
    terminal.status = "REJECTED"

    with pytest.raises(ConflictError, match="no longer pending"):
        await service.dismiss(
            candidate=terminal,
            actor_context=actor,
            request=DismissCareActionCandidateRequest(
                decision="REJECT",
                expected_version=1,
                reason_code="NOT_NEEDED",
            ),
        )

    stale = _pending_candidate(actor)
    with pytest.raises(ConflictError, match="version conflict"):
        await service.dismiss(
            candidate=stale,
            actor_context=actor,
            request=DismissCareActionCandidateRequest(
                decision="REJECT",
                expected_version=2,
                reason_code="NOT_NEEDED",
            ),
        )

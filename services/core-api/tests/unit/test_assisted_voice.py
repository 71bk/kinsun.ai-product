"""Accountless voice cannot outlive or escape its initiating handoff."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

import app.services.assisted_elder_session_service as assisted
from app.api.assisted_elders import _bound_conversation
from app.core.exceptions import AuthenticationError, NotFoundError
from app.schemas.assisted_elder import (
    AssistedVoiceTicketRequest,
    StaffAssistedAcknowledgementRequest,
)
from app.services.assisted_elder_session_service import (
    AssistedElderSessionPolicy,
    AssistedElderSessionService,
)


def setup_scope(monkeypatch):
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id=uuid4(),
        elder_id=uuid4(),
        tenant_id=uuid4(),
        initiated_by_actor_id=uuid4(),
        status="ACTIVE",
        idle_expires_at=now + timedelta(minutes=20),
        absolute_expires_at=now + timedelta(hours=2),
        pairing_expires_at=now + timedelta(minutes=5),
    )
    repo = SimpleNamespace(get_by_id=AsyncMock(return_value=row))
    service = AssistedElderSessionService(
        AsyncMock(),
        AssistedElderSessionPolicy(timedelta(minutes=5), timedelta(minutes=20), timedelta(hours=2)),
        enabled=True,
        repository=repo,
        clock=lambda: now,
    )
    service._require_live_scope = AsyncMock()
    monkeypatch.setattr(
        assisted,
        "ElderRepository",
        lambda *_: SimpleNamespace(
            get_by_id=AsyncMock(return_value=SimpleNamespace(status="ACTIVE")),
        ),
    )
    conversation = SimpleNamespace(
        assisted_session_id=row.id,
        tenant_id=row.tenant_id,
        elder_id=row.elder_id,
        initiator_actor_id=row.initiated_by_actor_id,
    )
    return now, row, service, conversation


@pytest.mark.asyncio
async def test_live_bound_voice_rechecks_staff_scope_without_extending_idle(monkeypatch):
    _, row, service, conversation = setup_scope(monkeypatch)
    deadline = row.idle_expires_at
    await service.require_bound_conversation(conversation)
    assert (
        service._require_live_scope.await_args.kwargs["requested_action"] == "voice_session:create"
    )
    assert row.idle_expires_at == deadline


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["ended", "idle", "absolute", "tenant", "elder", "actor", "missing", "revoked"]
)
async def test_speech_rejects_dead_or_cross_scope_handoff(monkeypatch, change):
    now, row, service, conversation = setup_scope(monkeypatch)
    if change == "ended":
        row.status = "ENDED"
    elif change == "idle":
        row.idle_expires_at = now
    elif change == "absolute":
        row.absolute_expires_at = now
    elif change == "tenant":
        conversation.tenant_id = uuid4()
    elif change == "elder":
        conversation.elder_id = uuid4()
    elif change == "actor":
        conversation.initiator_actor_id = uuid4()
    elif change == "missing":
        service._repository.get_by_id.return_value = None
    elif change == "revoked":
        service._require_live_scope.side_effect = AuthenticationError("unavailable")
    with pytest.raises(AuthenticationError):
        await service.require_bound_conversation(conversation)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field", ["assisted_session_id", "tenant_id", "elder_id", "initiator_actor_id"]
)
async def test_tablet_cannot_use_other_conversation_even_for_same_elder(monkeypatch, field):
    _, row, _, conversation = setup_scope(monkeypatch)
    resolved = SimpleNamespace(
        assisted_session=SimpleNamespace(id=row.id),
        elder=SimpleNamespace(id=row.elder_id),
        actor_context=SimpleNamespace(actor_id=row.initiated_by_actor_id, tenant_id=row.tenant_id),
    )
    setattr(conversation, field, uuid4())
    with pytest.raises(NotFoundError):
        await _bound_conversation(
            SimpleNamespace(get=AsyncMock(return_value=conversation)), uuid4(), resolved
        )


@pytest.mark.asyncio
async def test_staff_cannot_record_acknowledgement_for_another_initiator(monkeypatch):
    _, row, service, _ = setup_scope(monkeypatch)
    with pytest.raises(NotFoundError):
        await service.require_staff_handoff(
            assisted_session_id=row.id,
            elder_id=row.elder_id,
            actor_context=SimpleNamespace(actor_id=uuid4(), tenant_id=row.tenant_id),
        )
    service._require_live_scope.assert_not_awaited()


def test_staff_ack_requires_explicit_explanation_and_elder_agreement():
    for payload in [
        {},
        {"explanation_given": True},
        {"explanation_given": True, "elder_agreed": False},
    ]:
        with pytest.raises(ValidationError):
            StaffAssistedAcknowledgementRequest(**payload)
    with pytest.raises(ValidationError):
        AssistedVoiceTicketRequest(language_preference="NAN_TW")
    with pytest.raises(ValidationError):
        AssistedVoiceTicketRequest(elder_id=str(uuid4()))

"""Consent provenance and stop semantics for accountless Elder tablets."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.domain.consent import ConsentPurpose
from app.models.consent import ConsentGrant
from app.services import consent_service as consent_service_module
from app.services.consent_service import ConsentService


def _service() -> tuple[ConsentService, AsyncMock]:
    session = AsyncMock()
    session.flush = AsyncMock()
    service = ConsentService(session, uuid4())
    return service, session


@pytest.mark.asyncio
async def test_tablet_acknowledgement_records_session_without_fabricating_consent_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = _service()
    elder_id = uuid4()
    recorder_id = uuid4()
    assisted_session_id = uuid4()
    policy_id = uuid4()
    added: list[ConsentGrant] = []

    def add(grant: ConsentGrant) -> None:
        grant.id = uuid4()
        added.append(grant)

    service._consents = SimpleNamespace(
        get_active=AsyncMock(return_value=None),
        next_version=AsyncMock(return_value=3),
        add=MagicMock(side_effect=add),
    )
    service._policies = SimpleNamespace(
        find_active_consent_policy=AsyncMock(return_value=SimpleNamespace(id=policy_id))
    )
    outbox = AsyncMock()
    monkeypatch.setattr(consent_service_module, "write_outbox_entry", outbox)

    grant = await service.acknowledge_assisted_basic_voice(
        elder_id=elder_id,
        recorded_by_actor_id=recorder_id,
        assisted_session_id=assisted_session_id,
        policy_version="demo-consent-v1",
        trace_id="trace-ack",
        idempotency_key="idem-ack",
    )

    assert added == [grant]
    assert grant.purpose_code == ConsentPurpose.BASIC_VOICE.value
    assert grant.granted_by_actor_id is None
    assert grant.recorded_by_actor_id == recorder_id
    assert grant.assisted_session_id == assisted_session_id
    assert grant.confirmation_method == "ASSISTED_TABLET_ACKNOWLEDGEMENT"
    assert grant.scope == {"share_scopes": []}
    session.flush.assert_awaited_once()
    assert outbox.await_args.kwargs["actor_id"] == recorder_id
    assert outbox.await_args.kwargs["payload"]["confirmation_method"] == (
        "ASSISTED_TABLET_ACKNOWLEDGEMENT"
    )


@pytest.mark.asyncio
async def test_existing_active_voice_grant_is_not_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = _service()
    existing = SimpleNamespace(id=uuid4())
    find_policy = AsyncMock()
    add = MagicMock()
    service._consents = SimpleNamespace(get_active=AsyncMock(return_value=existing), add=add)
    service._policies = SimpleNamespace(find_active_consent_policy=find_policy)
    outbox = AsyncMock()
    monkeypatch.setattr(consent_service_module, "write_outbox_entry", outbox)

    result = await service.acknowledge_assisted_basic_voice(
        elder_id=uuid4(),
        recorded_by_actor_id=uuid4(),
        assisted_session_id=uuid4(),
        policy_version="demo-consent-v1",
        trace_id="trace-existing",
        idempotency_key="idem-existing",
    )

    assert result is existing
    find_policy.assert_not_awaited()
    add.assert_not_called()
    session.flush.assert_not_awaited()
    outbox.assert_not_awaited()


@pytest.mark.asyncio
async def test_tablet_revocation_cancels_active_conversations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, session = _service()
    elder_id = uuid4()
    recorder_id = uuid4()
    assisted_session_id = uuid4()
    consent = SimpleNamespace(
        id=uuid4(),
        purpose_code=ConsentPurpose.BASIC_VOICE.value,
        version=2,
        status="GRANTED",
        revoked_at=None,
    )
    conversation = SimpleNamespace(state="PROCESSING", ended_at=None)
    service._consents = SimpleNamespace(
        get_active=AsyncMock(return_value=consent),
        get_latest_for_purpose=AsyncMock(),
    )
    list_active = AsyncMock(return_value=[conversation])
    monkeypatch.setattr(
        consent_service_module,
        "ConversationRepository",
        lambda *_args: SimpleNamespace(list_active_for_consent_for_update=list_active),
    )
    outbox = AsyncMock()
    monkeypatch.setattr(consent_service_module, "write_outbox_entry", outbox)

    revoked = await service.revoke_assisted_basic_voice(
        elder_id=elder_id,
        recorded_by_actor_id=recorder_id,
        assisted_session_id=assisted_session_id,
        trace_id="trace-revoke",
        idempotency_key="idem-revoke",
    )

    assert revoked is consent
    assert consent.status == "REVOKED"
    assert isinstance(consent.revoked_at, datetime)
    assert consent.revoked_at.tzinfo == UTC
    assert conversation.state == "CANCELLED"
    assert conversation.ended_at is not None
    session.flush.assert_awaited_once()
    assert outbox.await_args.kwargs["payload"]["reason_code"] == ("ELDER_TABLET_REQUESTED_STOP")
    assert outbox.await_args.kwargs["payload"]["assisted_session_id"] == str(assisted_session_id)

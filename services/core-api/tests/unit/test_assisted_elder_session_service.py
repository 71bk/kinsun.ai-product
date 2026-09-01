"""State and revocation tests for staff-assisted Elder tablet sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import app.services.assisted_elder_session_service as service_module
from app.core.auth import ActorContext
from app.core.exceptions import AuthenticationError, ServiceUnavailableError
from app.models.assisted_elder_session import AssistedElderSession
from app.models.elder import Elder
from app.policies.elder_access import ElderAccessDecision
from app.services.assisted_elder_session_service import (
    AssistedElderSessionPolicy,
    AssistedElderSessionService,
)
from app.services.assisted_session_tokens import AssistedSessionTokenCodec

NOW = datetime(2026, 9, 1, 4, 0, tzinfo=UTC)


class FakeAssistedSessionRepository:
    def __init__(self, rows: list[AssistedElderSession] | None = None) -> None:
        self.rows = rows or []
        self.flush_count = 0

    def add(self, assisted_session: AssistedElderSession) -> None:
        assisted_session.id = assisted_session.id or uuid4()
        self.rows.append(assisted_session)

    async def flush(self) -> None:
        self.flush_count += 1

    async def get_by_pairing_digest(
        self, digest: str, *, for_update: bool
    ) -> AssistedElderSession | None:
        assert for_update is True
        return next((row for row in self.rows if row.pairing_token_digest == digest), None)

    async def get_by_session_digest(
        self, digest: str, *, for_update: bool
    ) -> AssistedElderSession | None:
        assert for_update is True
        return next((row for row in self.rows if row.session_token_digest == digest), None)

    async def list_live_for_elder(
        self, *, tenant_id, elder_id, for_update: bool
    ) -> list[AssistedElderSession]:
        assert for_update is True
        return [
            row
            for row in self.rows
            if row.tenant_id == tenant_id
            and row.elder_id == elder_id
            and row.status in {"PAIRING", "ACTIVE"}
        ]


def _policy() -> AssistedElderSessionPolicy:
    return AssistedElderSessionPolicy(
        pairing_ttl=timedelta(minutes=10),
        idle_ttl=timedelta(minutes=30),
        absolute_ttl=timedelta(hours=8),
    )


def _context(*, tenant_id=None) -> ActorContext:
    return ActorContext(
        actor_id=uuid4(),
        actor_role="DAYCARE_CARE_WORKER",
        tenant_id=tenant_id or uuid4(),
    )


def _pairing_row(
    raw_pairing_token: str,
    *,
    context: ActorContext,
    expires_at: datetime | None = None,
) -> AssistedElderSession:
    row = AssistedElderSession(
        tenant_id=context.tenant_id,
        elder_id=uuid4(),
        enrollment_id=uuid4(),
        initiated_by_actor_id=context.actor_id,
        initiator_mode="STAFF_ASSISTED",
        authorization_source_type="RELATIONSHIP",
        authorization_source_id=uuid4(),
        pairing_token_digest=AssistedSessionTokenCodec().digest_pairing(raw_pairing_token),
        status="PAIRING",
        pairing_expires_at=expires_at or NOW + timedelta(minutes=10),
        absolute_expires_at=NOW + timedelta(hours=8),
        version=1,
    )
    row.id = uuid4()
    return row


def _elder(row: AssistedElderSession) -> Elder:
    elder = Elder(
        actor_id=None,
        tenant_id=row.tenant_id,
        display_name="Synthetic Elder",
        preferred_name="Synthetic",
        preferred_language="ZH_TW",
        primary_care_setting="DAYCARE",
        response_length_preference="SHORT",
        timezone="Asia/Taipei",
        status="ACTIVE",
    )
    elder.id = row.elder_id
    return elder


def test_policy_rejects_expiry_ordering_errors() -> None:
    with pytest.raises(ValueError, match="idle TTL"):
        AssistedElderSessionPolicy(
            pairing_ttl=timedelta(minutes=5),
            idle_ttl=timedelta(hours=2),
            absolute_ttl=timedelta(hours=1),
        )


@pytest.mark.asyncio
async def test_disabled_feature_gate_fails_before_repository_access() -> None:
    repository = FakeAssistedSessionRepository()
    service = AssistedElderSessionService(
        AsyncMock(),
        _policy(),
        enabled=False,
        repository=repository,
        clock=lambda: NOW,
    )

    with pytest.raises(ServiceUnavailableError):
        await service.exchange("ep1_" + "A" * 43)
    assert repository.flush_count == 0


@pytest.mark.asyncio
async def test_pairing_exchange_is_single_use(monkeypatch: pytest.MonkeyPatch) -> None:
    codec = AssistedSessionTokenCodec()
    pairing = codec.issue_pairing()
    context = _context()
    row = _pairing_row(pairing.value, context=context)
    repository = FakeAssistedSessionRepository([row])
    service = AssistedElderSessionService(
        AsyncMock(),
        _policy(),
        enabled=True,
        codec=codec,
        repository=repository,
        clock=lambda: NOW,
    )
    monkeypatch.setattr(
        service,
        "_require_live_scope",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(
        service_module,
        "ElderRepository",
        lambda *_args, **_kwargs: SimpleNamespace(
            get_by_id=AsyncMock(return_value=_elder(row))
        ),
    )

    activated = await service.exchange(pairing.value)

    assert activated.session_token.startswith("es1_")
    assert row.status == "ACTIVE"
    assert row.session_token_digest == codec.digest_session(activated.session_token)
    assert row.idle_expires_at == NOW + timedelta(minutes=30)
    with pytest.raises(AuthenticationError):
        await service.exchange(pairing.value)


@pytest.mark.asyncio
async def test_expired_pairing_fails_without_live_scope_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codec = AssistedSessionTokenCodec()
    pairing = codec.issue_pairing()
    context = _context()
    row = _pairing_row(
        pairing.value,
        context=context,
        expires_at=NOW - timedelta(seconds=1),
    )
    service = AssistedElderSessionService(
        AsyncMock(),
        _policy(),
        enabled=True,
        codec=codec,
        repository=FakeAssistedSessionRepository([row]),
        clock=lambda: NOW,
    )
    live_scope = AsyncMock(return_value=context)
    monkeypatch.setattr(service, "_require_live_scope", live_scope)

    with pytest.raises(AuthenticationError):
        await service.exchange(pairing.value)
    live_scope.assert_not_awaited()


@pytest.mark.asyncio
async def test_reissue_ends_previous_live_session(monkeypatch: pytest.MonkeyPatch) -> None:
    context = _context()
    prior_token = AssistedSessionTokenCodec().issue_pairing()
    previous = _pairing_row(prior_token.value, context=context)
    repository = FakeAssistedSessionRepository([previous])
    enrollment = SimpleNamespace(id=uuid4())
    decision = ElderAccessDecision(
        allowed=True,
        reason_code="ALLOWED",
        expires_at=None,
        granted_scope=["assisted_session:create"],
        source_type="relationship",
        source_id=uuid4(),
    )
    monkeypatch.setattr(
        service_module,
        "authorize_elder_with_decision",
        AsyncMock(return_value=decision),
    )
    monkeypatch.setattr(
        service_module,
        "ElderEnrollmentRepository",
        lambda *_args, **_kwargs: SimpleNamespace(
            get_active=AsyncMock(return_value=enrollment)
        ),
    )
    service = AssistedElderSessionService(
        AsyncMock(),
        _policy(),
        enabled=True,
        repository=repository,
        clock=lambda: NOW,
    )

    issued = await service.issue(actor_context=context, elder_id=previous.elder_id)

    assert previous.status == "ENDED"
    assert previous.ended_at == NOW
    assert issued.pairing_token.startswith("ep1_")
    assert issued.assisted_session.enrollment_id == enrollment.id


@pytest.mark.asyncio
async def test_live_scope_rejects_cross_tenant_actor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    pairing = AssistedSessionTokenCodec().issue_pairing()
    row = _pairing_row(pairing.value, context=context)
    wrong_tenant_context = _context(tenant_id=uuid4())
    monkeypatch.setattr(
        service_module,
        "ActorRepository",
        lambda *_args, **_kwargs: SimpleNamespace(
            get_active_by_id=AsyncMock(return_value=object())
        ),
    )
    monkeypatch.setattr(
        service_module,
        "resolve_active_actor_context",
        AsyncMock(return_value=wrong_tenant_context),
    )
    authorize = AsyncMock()
    monkeypatch.setattr(service_module, "authorize_elder_with_decision", authorize)
    service = AssistedElderSessionService(
        AsyncMock(),
        _policy(),
        enabled=True,
        repository=FakeAssistedSessionRepository([row]),
        clock=lambda: NOW,
    )

    with pytest.raises(AuthenticationError):
        await service._require_live_scope(
            row,
            requested_action="voice_session:read",
            now=NOW,
        )
    authorize.assert_not_awaited()

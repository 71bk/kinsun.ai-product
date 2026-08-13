"""Unit tests for consent-bound family invitation issuance."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ConflictError, NotFoundError
from app.models.family_invitation import FamilyInvitation
from app.schemas.family_invitation import CreateFamilyInvitationRequest
from app.services.family_invitation_service import FamilyInvitationService
from app.services.family_invitation_tokens import FamilyInvitationTokenCodec

NOW = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)
SECRET = "unit-test-family-invitation-secret-32-bytes"
VALID_CODE = "ABCD-2345-EFGH-6789"


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _Result:
    def __init__(
        self,
        *,
        single: object | None = None,
        rows: list[object] | None = None,
    ) -> None:
        self._single = single
        self._rows = rows or []

    def scalar_one_or_none(self) -> object | None:
        return self._single

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


class _FakeSession:
    def __init__(
        self,
        *,
        scalar_results: list[object | None] | None = None,
        execute_results: list[object] | None = None,
    ) -> None:
        self._scalar_results = deque(scalar_results or [])
        self._execute_results = deque(execute_results or [])
        self.added: list[object] = []
        self.execute_calls: list[tuple[object, object | None]] = []

    async def execute(self, statement: object, parameters: object | None = None) -> object:
        self.execute_calls.append((statement, parameters))
        return self._execute_results.popleft() if self._execute_results else _Result()

    async def scalar(self, statement: object) -> object | None:
        del statement
        return self._scalar_results.popleft()

    def add(self, entity: object) -> None:
        self.added.append(entity)

    async def flush(self) -> None:
        for entity in self.added:
            if getattr(entity, "id", None) is None:
                entity.id = uuid4()
            if getattr(entity, "created_at", None) is None:
                entity.created_at = NOW
            if getattr(entity, "updated_at", None) is None:
                entity.updated_at = NOW
            if isinstance(entity, FamilyInvitation) and getattr(entity, "version", None) is None:
                entity.version = 1


def _invitation(
    *,
    status: str = "ISSUED",
    expires_at: datetime | None = None,
    redeemed_by_actor_id=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        elder_id=uuid4(),
        issued_by_actor_id=uuid4(),
        invitee_email_hmac=None,
        token_hash=FamilyInvitationTokenCodec(SECRET).hash_code(VALID_CODE),
        share_scope=["REPORT_DAILY", "REPORT_WEEKLY"],
        consent_id=uuid4(),
        status=status,
        expires_at=expires_at or NOW + timedelta(hours=1),
        attempt_count=0,
        max_attempts=5,
        redeemed_by_actor_id=redeemed_by_actor_id,
        redeemed_at=NOW if status == "REDEEMED" else None,
        version=2 if status == "REDEEMED" else 1,
        created_at=NOW - timedelta(minutes=10),
    )


def _service(session: _FakeSession) -> FamilyInvitationService:
    return FamilyInvitationService(session, FamilyInvitationTokenCodec(SECRET), now=lambda: NOW)


def _patch_consent(
    monkeypatch: pytest.MonkeyPatch,
    consent: object | None,
) -> AsyncMock:
    get_active = AsyncMock(return_value=consent)
    repository = MagicMock()
    repository.get_active = get_active
    monkeypatch.setattr(
        "app.services.family_invitation_service.ConsentRepository",
        lambda *_args, **_kwargs: repository,
    )
    return get_active


@pytest.mark.asyncio
async def test_create_requires_elder_role_before_database_lookup() -> None:
    session = _FakeSession()

    with pytest.raises(NotFoundError):
        await _service(session).create(
            tenant_id=uuid4(),
            elder_id=uuid4(),
            actor_id=uuid4(),
            actor_role="FAMILY_MEMBER",
            request=CreateFamilyInvitationRequest(),
            trace_id="trace-not-elder",
            idempotency_key="idem-not-elder",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_create_hides_cross_tenant_or_cross_elder_target() -> None:
    session = _FakeSession(scalar_results=[None])

    with pytest.raises(NotFoundError, match="Resource not found"):
        await _service(session).create(
            tenant_id=uuid4(),
            elder_id=uuid4(),
            actor_id=uuid4(),
            actor_role="ELDER",
            request=CreateFamilyInvitationRequest(),
            trace_id="trace-cross-scope",
            idempotency_key="idem-cross-scope",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_create_requires_active_family_sharing_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, elder_id, actor_id = uuid4(), uuid4(), uuid4()
    elder = SimpleNamespace(id=elder_id, tenant_id=tenant_id, actor_id=actor_id, status="ACTIVE")
    session = _FakeSession(scalar_results=[elder])
    _patch_consent(monkeypatch, None)

    with pytest.raises(ConflictError, match="consent must be active"):
        await _service(session).create(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role="ELDER",
            request=CreateFamilyInvitationRequest(),
            trace_id="trace-no-consent",
            idempotency_key="idem-no-consent",
        )

    assert session.added == []


@pytest.mark.asyncio
async def test_create_persists_only_code_and_email_hmac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, elder_id, actor_id = uuid4(), uuid4(), uuid4()
    elder = SimpleNamespace(id=elder_id, tenant_id=tenant_id, actor_id=actor_id, status="ACTIVE")
    consent = SimpleNamespace(
        id=uuid4(),
        version=3,
        scope={"share_scopes": ["REPORT_DAILY", "REPORT_WEEKLY", "REPORT_MONTHLY"]},
    )
    session = _FakeSession(scalar_results=[elder])
    _patch_consent(monkeypatch, consent)
    outbox = AsyncMock()
    monkeypatch.setattr("app.services.family_invitation_service.write_outbox_entry", outbox)
    service = _service(session)

    result = await service.create(
        tenant_id=tenant_id,
        elder_id=elder_id,
        actor_id=actor_id,
        actor_role="ELDER",
        request=CreateFamilyInvitationRequest(invitee_email="Family@Example.COM"),
        trace_id="trace-create",
        idempotency_key="idem-create",
    )

    invitation = next(entity for entity in session.added if isinstance(entity, FamilyInvitation))
    assert result.invitation_code != invitation.token_hash
    assert len(invitation.token_hash) == 64
    assert invitation.invitee_email_hmac == FamilyInvitationTokenCodec(SECRET).hash_email(
        "family@example.com"
    )
    assert "invitation_code" not in invitation.__dict__
    assert "invitee_email" not in invitation.__dict__
    outbox_payload = outbox.await_args.kwargs["payload"]
    assert result.invitation_code not in repr(outbox_payload)
    assert "family@example.com" not in repr(outbox_payload)


@pytest.mark.asyncio
async def test_create_rejects_scope_outside_active_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id, elder_id, actor_id = uuid4(), uuid4(), uuid4()
    elder = SimpleNamespace(id=elder_id, tenant_id=tenant_id, actor_id=actor_id, status="ACTIVE")
    consent = SimpleNamespace(
        id=uuid4(),
        version=1,
        scope={"share_scopes": ["REPORT_DAILY"]},
    )
    session = _FakeSession(scalar_results=[elder])
    _patch_consent(monkeypatch, consent)

    with pytest.raises(ConflictError, match="scope exceeds"):
        await _service(session).create(
            tenant_id=tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            actor_role="ELDER",
            request=CreateFamilyInvitationRequest(share_scope=["REPORT_DAILY", "REPORT_WEEKLY"]),
            trace_id="trace-scope-exceeds",
            idempotency_key="idem-scope-exceeds",
        )

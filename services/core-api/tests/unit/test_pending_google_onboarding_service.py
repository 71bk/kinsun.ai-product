"""Unit tests for one-time pending Google onboarding consumption."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.exceptions import AuthenticationError, ConflictError
from app.models.actor import Actor
from app.models.line_identity import ExternalIdentity
from app.models.pending_identity import PendingExternalIdentity
from app.schemas.family_invitation import FamilyInvitationRedeemedResponse
from app.services.app_session_service import IssuedAppSession
from app.services.pending_google_onboarding_service import PendingGoogleOnboardingService

NOW = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
TOKEN = "kp1_" + "a" * 43


class _Session:
    def __init__(self, *, scalar_result=None, actor=None) -> None:
        self.scalar_result = scalar_result
        self.actor = actor
        self.added: list[object] = []
        self.execute_count = 0

    async def execute(self, statement, parameters=None):
        del statement, parameters
        self.execute_count += 1
        return object()

    async def scalar(self, statement):
        del statement
        return self.scalar_result

    async def get(self, model, entity_id):
        del model
        return self.actor if self.actor is not None and self.actor.id == entity_id else None

    def add_all(self, entities) -> None:
        self.added.extend(entities)

    async def flush(self) -> None:
        for entity in self.added:
            if getattr(entity, "id", None) is None:
                entity.id = uuid4()


class _Repository:
    def __init__(self, pending: PendingExternalIdentity | None) -> None:
        self.pending = pending
        self.identities: list[ExternalIdentity] = []
        self.locked = False
        self.flush_count = 0

    async def get_pending_by_token_digest(self, token_digest, *, for_update=False):
        assert len(token_digest) == 64
        assert for_update is True
        return self.pending

    async def acquire_subject_lock(self, *, subject_digest, key_version):
        assert subject_digest == "b" * 64
        assert key_version == 1
        self.locked = True

    async def list_identities_by_subject(self, *, subject_digest, key_version, for_update=False):
        assert subject_digest == "b" * 64
        assert key_version == 1
        assert for_update is True
        return self.identities

    async def flush(self) -> None:
        self.flush_count += 1


class _AppSessions:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.result = IssuedAppSession(
            token="ks1_" + "c" * 43,
            session_id=uuid4(),
            idle_expires_at=NOW + timedelta(days=7),
            absolute_expires_at=NOW + timedelta(days=30),
        )

    async def issue(self, *, external_identity_id):
        self.calls.append(external_identity_id)
        return self.result


class _FamilyInvitations:
    def __init__(self, actor: Actor, external_identity: ExternalIdentity) -> None:
        self.actor = actor
        self.external_identity = external_identity
        self.calls: list[tuple[object, str]] = []

    async def redeem_pending_external_identity(
        self, *, pending, invitation_code, trace_id, idempotency_key
    ):
        del trace_id, idempotency_key
        self.calls.append((pending, invitation_code))
        return (
            FamilyInvitationRedeemedResponse(
                invitation_id=uuid4(),
                actor_id=self.actor.id,
                tenant_id=uuid4(),
                elder_id=uuid4(),
                relationship_id=uuid4(),
                family_relationship_id=uuid4(),
            ),
            self.external_identity,
        )


def _pending(*, intent="ELDER", expires_at=None, provider="GOOGLE") -> PendingExternalIdentity:
    value = PendingExternalIdentity(
        token_digest="d" * 64,
        provider=provider,
        external_subject_digest="b" * 64,
        digest_key_version=1,
        verified_email="synthetic@example.com",
        display_name="Synthetic Person",
        intent=intent,
        status="PENDING",
        expires_at=expires_at or NOW + timedelta(minutes=10),
        version=1,
    )
    value.id = uuid4()
    return value


@pytest.mark.asyncio
async def test_elder_completion_creates_identity_consumes_pending_and_issues_session() -> None:
    pending = _pending()
    repository = _Repository(pending)
    session = _Session()
    app_sessions = _AppSessions()
    service = PendingGoogleOnboardingService(
        session,  # type: ignore[arg-type]
        app_session_service=app_sessions,  # type: ignore[arg-type]
        family_invitation_service=object(),  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    result = await service.complete(
        pending_token=TOKEN,
        invitation_code=None,
        display_name="測試長者",
        trace_id="trace",
        idempotency_key="idem",
    )

    external_identity = next(
        entity for entity in session.added if isinstance(entity, ExternalIdentity)
    )
    actor = next(entity for entity in session.added if isinstance(entity, Actor))
    assert result.intent == "ELDER"
    assert result.status == "ACTIVE"
    assert result.actor_id == actor.id
    assert external_identity.external_subject_digest == "b" * 64
    assert app_sessions.calls == [external_identity.id]
    assert pending.status == "CONSUMED"
    assert pending.consumed_at == NOW
    assert pending.version == 2
    assert repository.locked is True


@pytest.mark.asyncio
async def test_line_elder_completion_uses_pending_provider() -> None:
    pending = _pending(provider="LINE")
    repository = _Repository(pending)
    session = _Session()
    app_sessions = _AppSessions()
    service = PendingGoogleOnboardingService(
        session,  # type: ignore[arg-type]
        app_session_service=app_sessions,  # type: ignore[arg-type]
        family_invitation_service=object(),  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
        provider="LINE",
    )

    await service.complete(
        pending_token=TOKEN,
        invitation_code=None,
        display_name="LINE User",
        trace_id="trace",
        idempotency_key="idem",
    )

    external_identity = next(
        entity for entity in session.added if isinstance(entity, ExternalIdentity)
    )
    assert external_identity.provider == "LINE"


@pytest.mark.asyncio
async def test_family_completion_delegates_invitation_before_issuing_session() -> None:
    pending = _pending(intent="FAMILY")
    actor = Actor(actor_type="FAMILY_MEMBER", display_name="Family", status="ACTIVE")
    actor.id = uuid4()
    external_identity = ExternalIdentity(
        provider="GOOGLE",
        external_subject_digest="b" * 64,
        digest_key_version=1,
        actor_id=actor.id,
        status="ACTIVE",
        version=1,
    )
    external_identity.id = uuid4()
    family = _FamilyInvitations(actor, external_identity)
    repository = _Repository(pending)
    app_sessions = _AppSessions()
    service = PendingGoogleOnboardingService(
        _Session(actor=actor),  # type: ignore[arg-type]
        app_session_service=app_sessions,  # type: ignore[arg-type]
        family_invitation_service=family,  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    result = await service.complete(
        pending_token=TOKEN,
        invitation_code="ABCD-2345-EFGH-6789",
        display_name=None,
        trace_id="trace",
        idempotency_key="idem",
    )

    assert result.intent == "FAMILY"
    assert result.status == "REDEEMED"
    assert family.calls == [(pending, "ABCD-2345-EFGH-6789")]
    assert app_sessions.calls == [external_identity.id]
    assert pending.status == "CONSUMED"


@pytest.mark.asyncio
async def test_expired_pending_token_fails_without_issuing_session() -> None:
    repository = _Repository(_pending(expires_at=NOW))
    app_sessions = _AppSessions()
    service = PendingGoogleOnboardingService(
        _Session(),  # type: ignore[arg-type]
        app_session_service=app_sessions,  # type: ignore[arg-type]
        family_invitation_service=object(),  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await service.complete(
            pending_token=TOKEN,
            invitation_code=None,
            display_name="Test",
            trace_id="trace",
            idempotency_key="idem",
        )

    assert repository.locked is False
    assert app_sessions.calls == []


@pytest.mark.asyncio
async def test_existing_email_requires_review_and_never_auto_links() -> None:
    pending = _pending()
    existing = Actor(actor_type="ELDER", display_name="Existing", status="ACTIVE")
    existing.id = uuid4()
    repository = _Repository(pending)
    app_sessions = _AppSessions()
    service = PendingGoogleOnboardingService(
        _Session(scalar_result=existing),  # type: ignore[arg-type]
        app_session_service=app_sessions,  # type: ignore[arg-type]
        family_invitation_service=object(),  # type: ignore[arg-type]
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    with pytest.raises(ConflictError, match="administrator review"):
        await service.complete(
            pending_token=TOKEN,
            invitation_code=None,
            display_name="Test",
            trace_id="trace",
            idempotency_key="idem",
        )

    assert pending.status == "PENDING"
    assert app_sessions.calls == []

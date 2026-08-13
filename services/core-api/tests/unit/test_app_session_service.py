"""Security and lifecycle tests for Core-owned opaque App Sessions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.core.exceptions import AuthenticationError
from app.middleware.auth import ActorContext
from app.models.actor import Actor
from app.models.app_session import AppSession
from app.models.line_identity import ExternalIdentity
from app.repositories.app_session_repo import ResolvedAppSession, ResolvedExternalIdentity
from app.services.app_session_service import AppSessionPolicy, AppSessionService
from app.services.app_session_tokens import AppSessionTokenCodec

_NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _MembershipResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> _ScalarRows:
        return _ScalarRows(self._rows)


class _FakeSession:
    def __init__(self, tenant_id=None, *, membership_count: int = 1) -> None:
        self.tenant_id = tenant_id or uuid4()
        self.membership_count = membership_count
        self.statements: list[object] = []

    async def execute(self, statement: object) -> _MembershipResult:
        self.statements.append(statement)
        memberships = [
            type("Membership", (), {"tenant_id": self.tenant_id})()
            for _ in range(self.membership_count)
        ]
        return _MembershipResult(memberships)


class _FakeRepository:
    def __init__(self) -> None:
        self.identity_result: ResolvedExternalIdentity | None = None
        self.session_result: ResolvedAppSession | None = None
        self.live_sessions: list[AppSession] = []
        self.added: list[AppSession] = []
        self.flush_count = 0
        self.expired_revoke_calls: list[tuple[object, datetime]] = []
        self.identity_for_update: bool | None = None
        self.session_for_update: bool | None = None

    async def get_active_identity(
        self,
        external_identity_id,
        *,
        for_update: bool = False,
    ) -> ResolvedExternalIdentity | None:
        del external_identity_id
        self.identity_for_update = for_update
        return self.identity_result

    def add(self, app_session: AppSession) -> None:
        app_session.id = uuid4()
        app_session.version = 1
        self.added.append(app_session)

    async def flush(self) -> None:
        self.flush_count += 1

    async def revoke_expired_for_actor(self, *, actor_id, now: datetime) -> None:
        self.expired_revoke_calls.append((actor_id, now))

    async def list_live_for_actor(
        self,
        *,
        actor_id,
        now: datetime,
        for_update: bool = False,
    ) -> list[AppSession]:
        del actor_id, now, for_update
        return [*self.added, *self.live_sessions]

    async def get_by_digest(
        self,
        token_digest: str,
        *,
        for_update: bool = False,
    ) -> ResolvedAppSession | None:
        del token_digest
        self.session_for_update = for_update
        return self.session_result


def _policy(*, max_active: int = 5) -> AppSessionPolicy:
    return AppSessionPolicy(
        elder_family_idle_ttl=timedelta(days=7),
        elder_family_absolute_ttl=timedelta(days=30),
        workforce_idle_ttl=timedelta(hours=8),
        workforce_absolute_ttl=timedelta(hours=24),
        touch_interval=timedelta(minutes=5),
        recent_auth_window=timedelta(minutes=10),
        max_active_per_actor=max_active,
    )


def _identity_and_actor(
    *,
    actor_type: str = "ELDER",
    actor_status: str = "ACTIVE",
    identity_status: str = "ACTIVE",
) -> tuple[ExternalIdentity, Actor]:
    actor = Actor(
        actor_type=actor_type,
        display_name="Test actor",
        status=actor_status,
    )
    actor.id = uuid4()
    identity = ExternalIdentity(
        provider="GOOGLE",
        external_subject_digest="a" * 64,
        digest_key_version=1,
        actor_id=actor.id,
        status=identity_status,
    )
    identity.id = uuid4()
    return identity, actor


def _app_session(
    identity: ExternalIdentity,
    actor: Actor,
    *,
    authenticated_at: datetime = _NOW - timedelta(hours=1),
    last_seen_at: datetime = _NOW - timedelta(minutes=1),
    idle_expires_at: datetime = _NOW + timedelta(hours=1),
    absolute_expires_at: datetime = _NOW + timedelta(days=1),
    status: str = "ACTIVE",
) -> AppSession:
    session = AppSession(
        token_digest="b" * 64,
        actor_id=actor.id,
        external_identity_id=identity.id,
        status=status,
        authenticated_at=authenticated_at,
        last_seen_at=last_seen_at,
        idle_expires_at=idle_expires_at,
        absolute_expires_at=absolute_expires_at,
        revoked_at=_NOW if status == "REVOKED" else None,
        version=1,
    )
    session.id = uuid4()
    return session


def _service(
    fake_session: _FakeSession,
    repository: _FakeRepository,
    *,
    policy: AppSessionPolicy | None = None,
) -> AppSessionService:
    return AppSessionService(
        fake_session,  # type: ignore[arg-type]
        policy or _policy(),
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )


@pytest.mark.asyncio
async def test_issue_persists_digest_only_applies_elder_ttls_and_locks_identity() -> None:
    identity, actor = _identity_and_actor(actor_type="ELDER")
    repository = _FakeRepository()
    repository.identity_result = ResolvedExternalIdentity(identity=identity, actor=actor)
    service = _service(_FakeSession(), repository)

    issued = await service.issue(external_identity_id=identity.id)

    persisted = repository.added[0]
    assert repository.identity_for_update is True
    assert persisted.token_digest == AppSessionTokenCodec().digest(issued.token)
    assert issued.token not in vars(persisted).values()
    assert persisted.idle_expires_at == _NOW + timedelta(days=7)
    assert persisted.absolute_expires_at == _NOW + timedelta(days=30)
    assert repository.expired_revoke_calls == [(actor.id, _NOW)]
    assert issued.session_id == persisted.id


@pytest.mark.asyncio
async def test_issue_applies_shorter_workforce_policy() -> None:
    identity, actor = _identity_and_actor(actor_type="ADMIN")
    repository = _FakeRepository()
    repository.identity_result = ResolvedExternalIdentity(identity=identity, actor=actor)

    issued = await _service(_FakeSession(), repository).issue(external_identity_id=identity.id)

    assert issued.idle_expires_at == _NOW + timedelta(hours=8)
    assert issued.absolute_expires_at == _NOW + timedelta(hours=24)


@pytest.mark.asyncio
async def test_issue_always_retains_new_token_and_revokes_oldest_over_cap() -> None:
    identity, actor = _identity_and_actor()
    repository = _FakeRepository()
    repository.identity_result = ResolvedExternalIdentity(identity=identity, actor=actor)
    newest_old = _app_session(identity, actor, authenticated_at=_NOW - timedelta(minutes=2))
    oldest = _app_session(identity, actor, authenticated_at=_NOW - timedelta(days=1))
    repository.live_sessions = [newest_old, oldest]

    issued = await _service(
        _FakeSession(),
        repository,
        policy=_policy(max_active=2),
    ).issue(external_identity_id=identity.id)

    assert issued.session_id == repository.added[0].id
    assert repository.added[0].status == "ACTIVE"
    assert newest_old.status == "ACTIVE"
    assert oldest.status == "REVOKED"
    assert oldest.revoked_at == _NOW
    assert oldest.version == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("actor_type", ["SYSTEM_SERVICE"])
async def test_issue_rejects_non_browser_actor(actor_type: str) -> None:
    identity, actor = _identity_and_actor(actor_type=actor_type)
    repository = _FakeRepository()
    repository.identity_result = ResolvedExternalIdentity(identity=identity, actor=actor)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _service(_FakeSession(), repository).issue(external_identity_id=identity.id)

    assert repository.added == []


@pytest.mark.asyncio
async def test_issue_rejects_actor_without_exactly_one_live_membership() -> None:
    identity, actor = _identity_and_actor()
    repository = _FakeRepository()
    repository.identity_result = ResolvedExternalIdentity(identity=identity, actor=actor)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _service(_FakeSession(membership_count=0), repository).issue(
            external_identity_id=identity.id
        )

    assert repository.added == []


@pytest.mark.asyncio
async def test_authenticate_returns_live_database_context_without_touching_too_soon() -> None:
    tenant_id = uuid4()
    fake_session = _FakeSession(tenant_id)
    identity, actor = _identity_and_actor(actor_type="FAMILY_MEMBER")
    app_session = _app_session(identity, actor, last_seen_at=_NOW - timedelta(minutes=4))
    repository = _FakeRepository()
    repository.session_result = ResolvedAppSession(app_session, identity, actor)
    token = AppSessionTokenCodec().issue().value

    context = await _service(fake_session, repository).authenticate(token)

    assert context == ActorContext(
        actor_id=actor.id,
        actor_role="FAMILY_MEMBER",
        tenant_id=tenant_id,
        status="ACTIVE",
    )
    assert app_session.last_seen_at == _NOW - timedelta(minutes=4)
    assert repository.flush_count == 0
    assert repository.session_for_update is False


@pytest.mark.asyncio
async def test_authenticate_throttles_touch_and_never_extends_past_absolute_expiry() -> None:
    identity, actor = _identity_and_actor()
    app_session = _app_session(
        identity,
        actor,
        last_seen_at=_NOW - timedelta(minutes=5),
        absolute_expires_at=_NOW + timedelta(days=2),
    )
    repository = _FakeRepository()
    repository.session_result = ResolvedAppSession(app_session, identity, actor)

    await _service(_FakeSession(), repository).authenticate(AppSessionTokenCodec().issue().value)

    assert app_session.last_seen_at == _NOW
    assert app_session.idle_expires_at == _NOW + timedelta(days=2)
    assert app_session.version == 2
    assert repository.flush_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_status", "identity_status", "actor_status", "idle_delta", "absolute_delta"),
    [
        ("REVOKED", "ACTIVE", "ACTIVE", timedelta(hours=1), timedelta(days=1)),
        ("ACTIVE", "SUSPENDED", "ACTIVE", timedelta(hours=1), timedelta(days=1)),
        ("ACTIVE", "ACTIVE", "SUSPENDED", timedelta(hours=1), timedelta(days=1)),
        ("ACTIVE", "ACTIVE", "ACTIVE", timedelta(0), timedelta(days=1)),
        ("ACTIVE", "ACTIVE", "ACTIVE", timedelta(hours=1), timedelta(0)),
    ],
)
async def test_authenticate_rejects_revoked_or_inactive_or_expired_state(
    session_status: str,
    identity_status: str,
    actor_status: str,
    idle_delta: timedelta,
    absolute_delta: timedelta,
) -> None:
    identity, actor = _identity_and_actor(
        actor_status=actor_status,
        identity_status=identity_status,
    )
    app_session = _app_session(
        identity,
        actor,
        status=session_status,
        idle_expires_at=_NOW + idle_delta,
        absolute_expires_at=_NOW + absolute_delta,
    )
    repository = _FakeRepository()
    repository.session_result = ResolvedAppSession(app_session, identity, actor)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _service(_FakeSession(), repository).authenticate(
            AppSessionTokenCodec().issue().value
        )


@pytest.mark.asyncio
async def test_authenticate_hides_malformed_and_unknown_token_details() -> None:
    repository = _FakeRepository()
    service = _service(_FakeSession(), repository)

    with pytest.raises(AuthenticationError, match="^Authentication required$"):
        await service.authenticate("not-a-token")
    with pytest.raises(AuthenticationError, match="^Authentication required$"):
        await service.authenticate(AppSessionTokenCodec().issue().value)


@pytest.mark.asyncio
async def test_revoke_is_idempotent_and_uses_row_lock() -> None:
    identity, actor = _identity_and_actor()
    app_session = _app_session(identity, actor)
    repository = _FakeRepository()
    repository.session_result = ResolvedAppSession(app_session, identity, actor)
    service = _service(_FakeSession(), repository)
    token = AppSessionTokenCodec().issue().value

    assert await service.revoke(token) is True
    assert repository.session_for_update is True
    assert app_session.status == "REVOKED"
    assert app_session.revoked_at == _NOW
    assert app_session.version == 2
    assert await service.revoke(token) is False
    assert await service.revoke("malformed") is False


def test_recent_auth_window_requires_live_recent_session() -> None:
    identity, actor = _identity_and_actor()
    recent = _app_session(identity, actor, authenticated_at=_NOW - timedelta(minutes=10))
    old = _app_session(identity, actor, authenticated_at=_NOW - timedelta(minutes=10, seconds=1))
    service = _service(_FakeSession(), _FakeRepository())

    assert service.is_recently_authenticated(recent) is True
    assert service.is_recently_authenticated(old) is False


def test_policy_rejects_an_unbounded_or_incoherent_manual_configuration() -> None:
    with pytest.raises(ValueError, match="idle TTL"):
        AppSessionPolicy(
            elder_family_idle_ttl=timedelta(days=31),
            elder_family_absolute_ttl=timedelta(days=30),
            workforce_idle_ttl=timedelta(hours=8),
            workforce_absolute_ttl=timedelta(days=1),
            touch_interval=timedelta(minutes=5),
            recent_auth_window=timedelta(minutes=10),
            max_active_per_actor=5,
        )

"""Security tests for Google identity handoff resolution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.adapters.auth.google_oidc import VerifiedGoogleIdentity
from app.core.exceptions import AuthenticationError
from app.models.line_identity import ExternalIdentity
from app.models.pending_identity import PendingExternalIdentity
from app.services.app_session_service import IssuedAppSession
from app.services.google_identity_codec import GoogleIdentityCodec
from app.services.google_oidc_handoff_service import (
    AuthenticatedGoogleHandoff,
    GoogleOidcHandoffService,
    PendingGoogleHandoff,
    PendingIdentityPolicy,
)
from app.services.pending_identity_tokens import PendingIdentityTokenCodec

_NOW = datetime(2026, 8, 11, 16, 0, tzinfo=UTC)
_SECRET = "google-identity-handoff-test-secret-material-32-bytes"


class _Verifier:
    def __init__(self, identity: VerifiedGoogleIdentity) -> None:
        self.identity = identity
        self.calls: list[tuple[str, str]] = []

    async def verify_id_token(self, token: str, *, expected_nonce: str):
        self.calls.append((token, expected_nonce))
        return self.identity


class _Repository:
    def __init__(self) -> None:
        self.identities: list[ExternalIdentity] = []
        self.pending: PendingExternalIdentity | None = None
        self.added: list[PendingExternalIdentity] = []
        self.flush_count = 0
        self.locked: tuple[str, int] | None = None
        self.identity_for_update: bool | None = None
        self.pending_for_update: bool | None = None

    async def acquire_subject_lock(self, *, subject_digest: str, key_version: int) -> None:
        self.locked = (subject_digest, key_version)

    async def list_identities_by_subject(
        self, *, subject_digest: str, key_version: int, for_update: bool = False
    ) -> list[ExternalIdentity]:
        del subject_digest, key_version
        self.identity_for_update = for_update
        return self.identities

    async def get_pending_by_subject(
        self, *, subject_digest: str, key_version: int, for_update: bool = False
    ) -> PendingExternalIdentity | None:
        del subject_digest, key_version
        self.pending_for_update = for_update
        return self.pending

    def add_pending(self, pending: PendingExternalIdentity) -> None:
        pending.id = uuid4()
        self.added.append(pending)

    async def flush(self) -> None:
        self.flush_count += 1


class _AppSessionService:
    def __init__(self) -> None:
        self.calls: list[object] = []
        self.issued = IssuedAppSession(
            token="ks1_" + "a" * 43,
            session_id=uuid4(),
            idle_expires_at=_NOW + timedelta(days=7),
            absolute_expires_at=_NOW + timedelta(days=30),
        )

    async def issue(self, *, external_identity_id):
        self.calls.append(external_identity_id)
        return self.issued


def _identity(*, status: str = "ACTIVE") -> ExternalIdentity:
    identity = ExternalIdentity(
        provider="GOOGLE",
        external_subject_digest="a" * 64,
        digest_key_version=1,
        actor_id=uuid4(),
        status=status,
        version=1,
    )
    identity.id = uuid4()
    return identity


def _pending(*, expires_at: datetime) -> PendingExternalIdentity:
    pending = PendingExternalIdentity(
        token_digest="b" * 64,
        provider="GOOGLE",
        external_subject_digest="a" * 64,
        digest_key_version=1,
        verified_email="person@example.com",
        display_name="Person",
        intent="ELDER",
        status="PENDING",
        expires_at=expires_at,
        version=1,
    )
    pending.id = uuid4()
    return pending


def _service(
    repository: _Repository,
    app_sessions: _AppSessionService,
    *,
    identity: VerifiedGoogleIdentity | None = None,
) -> tuple[GoogleOidcHandoffService, _Verifier, GoogleIdentityCodec]:
    verifier = _Verifier(
        identity
        or VerifiedGoogleIdentity(
            subject="google-subject-123",
            email="Person@Example.COM",
            email_verified=True,
            display_name="Person",
        )
    )
    codec = GoogleIdentityCodec(_SECRET, 1)
    service = GoogleOidcHandoffService(
        object(),  # type: ignore[arg-type]
        verifier=verifier,  # type: ignore[arg-type]
        identity_codec=codec,
        app_session_service=app_sessions,  # type: ignore[arg-type]
        pending_policy=PendingIdentityPolicy(timedelta(minutes=10)),
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )
    return service, verifier, codec


@pytest.mark.asyncio
async def test_unknown_subject_issues_pending_token_and_persists_digest_only() -> None:
    repository = _Repository()
    app_sessions = _AppSessionService()
    service, verifier, codec = _service(repository, app_sessions)

    result = await service.handoff(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        intent="ELDER",
    )

    assert isinstance(result, PendingGoogleHandoff)
    assert verifier.calls == [("header.payload.signature", "n" * 32)]
    assert repository.locked == (codec.digest_subject("google-subject-123"), 1)
    assert repository.identity_for_update is True
    assert repository.pending_for_update is True
    persisted = repository.added[0]
    assert persisted.token_digest == PendingIdentityTokenCodec().digest(result.token)
    assert result.token not in vars(persisted).values()
    assert persisted.external_subject_digest == codec.digest_subject("google-subject-123")
    assert persisted.verified_email == "person@example.com"
    assert persisted.intent == "ELDER"
    assert result.expires_at == _NOW + timedelta(minutes=10)
    assert app_sessions.calls == []


@pytest.mark.asyncio
async def test_active_identity_issues_app_session_and_revokes_stale_pending() -> None:
    repository = _Repository()
    identity = _identity()
    repository.identities = [identity]
    repository.pending = _pending(expires_at=_NOW + timedelta(minutes=2))
    app_sessions = _AppSessionService()
    service, _, _ = _service(repository, app_sessions)

    result = await service.handoff(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        intent="FAMILY",
    )

    assert isinstance(result, AuthenticatedGoogleHandoff)
    assert result.session == app_sessions.issued
    assert app_sessions.calls == [identity.id]
    assert identity.last_seen_at == _NOW
    assert identity.version == 2
    assert repository.pending.status == "REVOKED"
    assert repository.pending.invalidated_at == _NOW
    assert repository.added == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["SUSPENDED", "REVOKED"])
async def test_inactive_identity_fails_closed_without_new_pending(status: str) -> None:
    repository = _Repository()
    repository.identities = [_identity(status=status)]
    app_sessions = _AppSessionService()
    service, _, _ = _service(repository, app_sessions)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await service.handoff(
            id_token="header.payload.signature",
            expected_nonce="n" * 32,
            intent="ELDER",
        )

    assert repository.added == []
    assert app_sessions.calls == []


@pytest.mark.asyncio
async def test_unknown_staff_identity_cannot_self_provision() -> None:
    repository = _Repository()
    app_sessions = _AppSessionService()
    service, _, _ = _service(repository, app_sessions)

    with pytest.raises(AuthenticationError, match="Authentication required"):
        await service.handoff(
            id_token="header.payload.signature",
            expected_nonce="n" * 32,
            intent="STAFF",
        )

    assert repository.added == []
    assert app_sessions.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expires_at", "terminal_status"),
    [
        (_NOW - timedelta(seconds=1), "EXPIRED"),
        (_NOW + timedelta(seconds=1), "REVOKED"),
    ],
)
async def test_replaces_prior_pending_after_terminal_flush(
    expires_at: datetime, terminal_status: str
) -> None:
    repository = _Repository()
    repository.pending = _pending(expires_at=expires_at)
    service, _, _ = _service(repository, _AppSessionService())

    result = await service.handoff(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        intent="ELDER",
    )

    assert isinstance(result, PendingGoogleHandoff)
    assert repository.pending.status == terminal_status
    assert repository.pending.invalidated_at == _NOW
    assert repository.flush_count == 2
    assert len(repository.added) == 1


def test_pending_policy_is_bounded() -> None:
    with pytest.raises(ValueError, match="60 and 900"):
        PendingIdentityPolicy(timedelta(seconds=59))
    with pytest.raises(ValueError, match="60 and 900"):
        PendingIdentityPolicy(timedelta(seconds=901))

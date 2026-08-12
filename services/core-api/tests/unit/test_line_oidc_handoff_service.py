"""Security tests for LINE identity handoff resolution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.adapters.auth.line_oidc import VerifiedLineIdentity
from app.core.exceptions import AuthenticationError
from app.models.line_identity import ExternalIdentity
from app.services.app_session_service import IssuedAppSession
from app.services.google_oidc_handoff_service import PendingIdentityPolicy
from app.services.line_identity_codec import LineIdentityCodec
from app.services.line_oidc_handoff_service import (
    AuthenticatedLineHandoff,
    LineOidcHandoffService,
    PendingLineHandoff,
)
from app.services.pending_identity_tokens import PendingIdentityTokenCodec

_NOW = datetime(2026, 8, 12, 0, 0, tzinfo=UTC)


class _Verifier:
    async def verify_id_token(self, token: str, *, expected_nonce: str):
        assert token == "header.payload.signature"
        assert expected_nonce == "n" * 32
        return VerifiedLineIdentity(
            subject="U1234567890abcdef",
            display_name="LINE User",
        )


class _Repository:
    def __init__(self) -> None:
        self.identities: list[ExternalIdentity] = []
        self.added = []
        self.locked = None

    async def acquire_subject_lock(self, *, subject_digest: str, key_version: int) -> None:
        self.locked = (subject_digest, key_version)

    async def list_identities_by_subject(self, **_kwargs):
        return self.identities

    async def get_pending_by_subject(self, **_kwargs):
        return None

    def add_pending(self, pending) -> None:
        pending.id = uuid4()
        self.added.append(pending)

    async def flush(self) -> None:
        return None


class _AppSessions:
    def __init__(self) -> None:
        self.calls = []
        self.issued = IssuedAppSession(
            token="ks1_" + "a" * 43,
            session_id=uuid4(),
            idle_expires_at=_NOW + timedelta(days=7),
            absolute_expires_at=_NOW + timedelta(days=30),
        )

    async def issue(self, *, external_identity_id):
        self.calls.append(external_identity_id)
        return self.issued


def _service(repository: _Repository, app_sessions: _AppSessions) -> LineOidcHandoffService:
    return LineOidcHandoffService(
        object(),  # type: ignore[arg-type]
        verifier=_Verifier(),  # type: ignore[arg-type]
        identity_codec=LineIdentityCodec("line-identity-secret-material-at-least-32-bytes", 1),
        app_session_service=app_sessions,  # type: ignore[arg-type]
        pending_policy=PendingIdentityPolicy(timedelta(minutes=10)),
        repository=repository,  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )


@pytest.mark.asyncio
async def test_unknown_line_subject_creates_line_pending_identity_without_email() -> None:
    repository = _Repository()
    app_sessions = _AppSessions()

    result = await _service(repository, app_sessions).handoff(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        intent="ELDER",
    )

    assert isinstance(result, PendingLineHandoff)
    persisted = repository.added[0]
    assert persisted.provider == "LINE"
    assert persisted.verified_email is None
    assert persisted.token_digest == PendingIdentityTokenCodec().digest(result.token)
    assert result.token not in vars(persisted).values()
    assert app_sessions.calls == []


@pytest.mark.asyncio
async def test_active_line_identity_issues_core_app_session() -> None:
    repository = _Repository()
    identity = ExternalIdentity(
        provider="LINE",
        external_subject_digest="a" * 64,
        digest_key_version=1,
        actor_id=uuid4(),
        status="ACTIVE",
        version=1,
    )
    identity.id = uuid4()
    repository.identities = [identity]
    app_sessions = _AppSessions()

    result = await _service(repository, app_sessions).handoff(
        id_token="header.payload.signature",
        expected_nonce="n" * 32,
        intent="FAMILY",
    )

    assert isinstance(result, AuthenticatedLineHandoff)
    assert app_sessions.calls == [identity.id]


@pytest.mark.asyncio
async def test_unknown_staff_line_identity_cannot_self_provision() -> None:
    repository = _Repository()
    with pytest.raises(AuthenticationError, match="Authentication required"):
        await _service(repository, _AppSessions()).handoff(
            id_token="header.payload.signature",
            expected_nonce="n" * 32,
            intent="STAFF",
        )
    assert repository.added == []

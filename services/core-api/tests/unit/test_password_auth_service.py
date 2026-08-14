from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.models.line_identity import ExternalIdentity
from app.models.password_credential import PasswordCredential
from app.services.kinsun_identity_codec import KinsunIdentityCodec
from app.services.password_auth_service import (
    CompletedPasswordAuthentication,
    PasswordAuthService,
    PasswordLockoutPolicy,
    RejectedPasswordAuthentication,
)

_NOW = datetime(2026, 8, 14, 19, 0, tzinfo=UTC)
_ACTOR_ID = UUID("20000000-0000-4000-8000-000000000010")
_IDENTITY_ID = UUID("29000000-0000-4000-8000-000000000010")
_CODEC = KinsunIdentityCodec("password-auth-identity-secret-material-32-bytes", 1)


class _Hasher:
    policy = SimpleNamespace(parameter_version=1)

    def hash(self, password: str) -> str:
        return f"hash:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hash:{password}"

    def verify_dummy(self, password: str) -> None:
        del password


class _IdentityRepository:
    def __init__(self, identities: list[ExternalIdentity]) -> None:
        self.identities = identities

    async def acquire_subject_lock(self, **kwargs) -> None:
        del kwargs

    async def list_identities_by_subject(self, **kwargs) -> list[ExternalIdentity]:
        del kwargs
        return self.identities


class _CredentialRepository:
    def __init__(self, credential: PasswordCredential | None) -> None:
        self.credential = credential
        self.flush_count = 0

    async def get_by_actor(self, actor_id: UUID, *, for_update: bool = False):
        del actor_id, for_update
        return self.credential

    def add(self, credential: PasswordCredential) -> None:
        self.credential = credential

    async def flush(self) -> None:
        self.flush_count += 1


class _AppSessions:
    def __init__(self) -> None:
        self.issued_for: UUID | None = None
        self.result = SimpleNamespace(token="ks1_session")

    async def issue(self, *, external_identity_id: UUID):
        self.issued_for = external_identity_id
        return self.result


def _identity() -> ExternalIdentity:
    return ExternalIdentity(
        id=_IDENTITY_ID,
        provider="KINSUN",
        external_subject_digest=_CODEC.digest_email("staff.demo@kinsun.local"),
        digest_key_version=1,
        actor_id=_ACTOR_ID,
        status="ACTIVE",
        version=1,
    )


def _credential() -> PasswordCredential:
    return PasswordCredential(
        actor_id=_ACTOR_ID,
        password_hash="hash:a-valid-demo-password",
        algorithm="ARGON2ID",
        parameter_version=1,
        status="ACTIVE",
        failed_attempt_count=0,
        locked_until=None,
        password_changed_at=_NOW,
        version=1,
    )


def _service(
    credential: PasswordCredential | None,
    identities: list[ExternalIdentity] | None = None,
):
    app_sessions = _AppSessions()
    repository = _CredentialRepository(credential)
    service = PasswordAuthService(
        SimpleNamespace(),  # type: ignore[arg-type]
        identity_codec=_CODEC,
        password_hasher=_Hasher(),  # type: ignore[arg-type]
        app_session_service=app_sessions,  # type: ignore[arg-type]
        lockout_policy=PasswordLockoutPolicy(
            max_attempts=3,
            duration=timedelta(minutes=15),
        ),
        identity_repository=_IdentityRepository(identities or [_identity()]),  # type: ignore[arg-type]
        credential_repository=repository,  # type: ignore[arg-type]
        clock=lambda: _NOW,
    )
    return service, repository, app_sessions


@pytest.mark.asyncio
async def test_successful_password_login_issues_existing_app_session() -> None:
    credential = _credential()
    service, repository, app_sessions = _service(credential)

    result = await service.authenticate(
        email=" STAFF.DEMO@KINSUN.LOCAL ",
        password="a-valid-demo-password",
    )

    assert isinstance(result, CompletedPasswordAuthentication)
    assert result.session is app_sessions.result
    assert app_sessions.issued_for == _IDENTITY_ID
    assert credential.failed_attempt_count == 0
    assert credential.last_verified_at == _NOW
    assert repository.flush_count == 1


@pytest.mark.asyncio
async def test_wrong_password_locks_after_bounded_attempts() -> None:
    credential = _credential()
    credential.failed_attempt_count = 2
    service, _, app_sessions = _service(credential)

    result = await service.authenticate(
        email="staff.demo@kinsun.local",
        password="a-wrong-demo-password",
    )

    assert isinstance(result, RejectedPasswordAuthentication)
    assert credential.status == "LOCKED"
    assert credential.failed_attempt_count == 3
    assert credential.locked_until == _NOW + timedelta(minutes=15)
    assert app_sessions.issued_for is None


@pytest.mark.asyncio
async def test_missing_credential_fails_without_issuing_session() -> None:
    service, _, app_sessions = _service(None)

    result = await service.authenticate(
        email="staff.demo@kinsun.local",
        password="a-valid-demo-password",
    )

    assert isinstance(result, RejectedPasswordAuthentication)
    assert app_sessions.issued_for is None

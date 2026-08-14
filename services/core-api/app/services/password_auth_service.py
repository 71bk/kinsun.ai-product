"""Kinsun Email and Password credential lifecycle and App Session login."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.models.password_credential import PasswordCredential
from app.repositories.kinsun_identity_repo import KinsunIdentityRepository
from app.repositories.password_credential_repo import PasswordCredentialRepository
from app.services.app_session_service import AppSessionService, IssuedAppSession
from app.services.kinsun_identity_codec import KinsunIdentityCodec
from app.services.password_hasher import PasswordHasher


@dataclass(frozen=True)
class PasswordLockoutPolicy:
    max_attempts: int
    duration: timedelta

    def __post_init__(self) -> None:
        if not 3 <= self.max_attempts <= 20:
            raise ValueError("Password attempts must be between 3 and 20")
        if not timedelta(seconds=30) <= self.duration <= timedelta(hours=24):
            raise ValueError("Password lockout must be between 30 seconds and 24 hours")


@dataclass(frozen=True)
class CompletedPasswordAuthentication:
    session: IssuedAppSession


@dataclass(frozen=True)
class RejectedPasswordAuthentication:
    """Uniform rejection whose bounded state updates must still commit."""


PasswordAuthentication = CompletedPasswordAuthentication | RejectedPasswordAuthentication


class PasswordAuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        identity_codec: KinsunIdentityCodec,
        password_hasher: PasswordHasher,
        app_session_service: AppSessionService,
        lockout_policy: PasswordLockoutPolicy,
        identity_repository: KinsunIdentityRepository | None = None,
        credential_repository: PasswordCredentialRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._identity_codec = identity_codec
        self._password_hasher = password_hasher
        self._app_sessions = app_session_service
        self._lockout = lockout_policy
        self._identities = identity_repository or KinsunIdentityRepository(session)
        self._credentials = credential_repository or PasswordCredentialRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def create_credential(self, *, actor_id: UUID, password: str) -> PasswordCredential:
        existing = await self._credentials.get_by_actor(actor_id, for_update=True)
        if existing is not None:
            raise ConflictError("Password credential already exists")
        now = self._clock()
        credential = PasswordCredential(
            actor_id=actor_id,
            password_hash=self._password_hasher.hash(password),
            algorithm="ARGON2ID",
            parameter_version=self._password_hasher.policy.parameter_version,
            status="ACTIVE",
            failed_attempt_count=0,
            locked_until=None,
            password_changed_at=now,
            last_verified_at=None,
            revoked_at=None,
            version=1,
        )
        self._credentials.add(credential)
        await self._credentials.flush()
        return credential

    async def authenticate(self, *, email: str, password: str) -> PasswordAuthentication:
        try:
            normalized_email = self._identity_codec.normalize_email(email)
        except ValueError:
            self._password_hasher.verify_dummy(password)
            return RejectedPasswordAuthentication()

        subject_digest = self._identity_codec.digest_email(normalized_email)
        key_version = self._identity_codec.key_version
        await self._identities.acquire_subject_lock(
            subject_digest=subject_digest,
            key_version=key_version,
        )
        identities = await self._identities.list_identities_by_subject(
            subject_digest=subject_digest,
            key_version=key_version,
            for_update=True,
        )
        active = [identity for identity in identities if identity.status == "ACTIVE"]
        if len(active) != 1:
            self._password_hasher.verify_dummy(password)
            return RejectedPasswordAuthentication()

        identity = active[0]
        credential = await self._credentials.get_by_actor(identity.actor_id, for_update=True)
        if credential is None or credential.algorithm != "ARGON2ID":
            self._password_hasher.verify_dummy(password)
            return RejectedPasswordAuthentication()

        now = self._clock()
        verified = self._password_hasher.verify(password, credential.password_hash)
        if credential.status == "REVOKED":
            return RejectedPasswordAuthentication()
        if credential.status == "LOCKED" and credential.locked_until is not None:
            if credential.locked_until > now:
                return RejectedPasswordAuthentication()
            credential.status = "ACTIVE"
            credential.failed_attempt_count = 0
            credential.locked_until = None

        if not verified:
            credential.failed_attempt_count = min(
                credential.failed_attempt_count + 1,
                self._lockout.max_attempts,
            )
            if credential.failed_attempt_count >= self._lockout.max_attempts:
                credential.status = "LOCKED"
                credential.locked_until = now + self._lockout.duration
            credential.version = (credential.version or 0) + 1
            await self._credentials.flush()
            return RejectedPasswordAuthentication()

        if credential.parameter_version < self._password_hasher.policy.parameter_version:
            credential.password_hash = self._password_hasher.hash(password)
            credential.parameter_version = self._password_hasher.policy.parameter_version
            credential.password_changed_at = now
        credential.status = "ACTIVE"
        credential.failed_attempt_count = 0
        credential.locked_until = None
        credential.last_verified_at = now
        credential.version = (credential.version or 0) + 1
        identity.last_seen_at = now
        identity.version = (identity.version or 0) + 1
        await self._credentials.flush()
        issued_session = await self._app_sessions.issue(external_identity_id=identity.id)
        return CompletedPasswordAuthentication(session=issued_session)

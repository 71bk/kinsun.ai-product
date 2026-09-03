"""Kinsun-owned email verification and App Session issuance."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.models.kinsun_identity import KinsunEmailChallenge
from app.models.pending_identity import PendingExternalIdentity
from app.repositories.google_identity_repo import GoogleIdentityRepository
from app.repositories.kinsun_identity_repo import KinsunIdentityRepository
from app.services.app_session_service import AppSessionService, IssuedAppSession
from app.services.family_invitation_service import FamilyInvitationService
from app.services.kinsun_identity_codec import (
    KinsunEmailChallengeCodec,
    KinsunIdentityCodec,
)
from app.services.password_auth_service import PasswordAuthService
from app.services.pending_google_onboarding_service import PendingGoogleOnboardingService
from app.services.pending_identity_tokens import PendingIdentityTokenCodec


@dataclass(frozen=True)
class KinsunEmailChallengePolicy:
    ttl: timedelta
    max_attempts: int

    def __post_init__(self) -> None:
        if not timedelta(minutes=2) <= self.ttl <= timedelta(minutes=15):
            raise ValueError("Kinsun email challenge TTL must be between 120 and 900 seconds")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("Kinsun email challenge attempts must be between 1 and 5")


@dataclass(frozen=True)
class StartedKinsunEmailChallenge:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class CompletedKinsunEmailAuthentication:
    session: IssuedAppSession


@dataclass(frozen=True)
class RejectedKinsunEmailAuthentication:
    """A uniform rejection whose state changes must still be committed."""


KinsunEmailCompletion = CompletedKinsunEmailAuthentication | RejectedKinsunEmailAuthentication


class KinsunEmailAuthService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        identity_codec: KinsunIdentityCodec,
        challenge_codec: KinsunEmailChallengeCodec,
        app_session_service: AppSessionService,
        family_invitation_service: FamilyInvitationService,
        password_auth_service: PasswordAuthService,
        policy: KinsunEmailChallengePolicy,
        verification_code: str,
        repository: KinsunIdentityRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if len(verification_code) != 6 or not verification_code.isdecimal():
            raise ValueError("Synthetic verification code must contain exactly six digits")
        self._session = session
        self._identity_codec = identity_codec
        self._challenge_codec = challenge_codec
        self._app_sessions = app_session_service
        self._family_invitations = family_invitation_service
        self._password_auth = password_auth_service
        self._policy = policy
        self._verification_code = verification_code
        self._repository = repository or KinsunIdentityRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def start(
        self,
        *,
        email: str,
        intent: Literal["ELDER", "FAMILY", "STAFF"],
        display_name: str | None,
    ) -> StartedKinsunEmailChallenge:
        normalized_email = self._identity_codec.normalize_email(email)
        subject_digest = self._identity_codec.digest_email(normalized_email)
        key_version = self._identity_codec.key_version
        await self._repository.acquire_subject_lock(
            subject_digest=subject_digest,
            key_version=key_version,
        )
        now = self._clock()
        previous = await self._repository.get_pending_by_subject(
            subject_digest=subject_digest,
            key_version=key_version,
            for_update=True,
        )
        if previous is not None:
            previous.status = "EXPIRED" if previous.expires_at <= now else "REVOKED"
            previous.invalidated_at = now
            previous.version = (previous.version or 0) + 1
            await self._repository.flush()

        issued = self._challenge_codec.issue()
        expires_at = now + self._policy.ttl
        challenge = KinsunEmailChallenge(
            token_digest=issued.digest,
            email_address=normalized_email,
            external_subject_digest=subject_digest,
            digest_key_version=key_version,
            code_digest=self._challenge_codec.digest_code(
                token_digest=issued.digest,
                code=self._verification_code,
            ),
            intent=intent,
            display_name=display_name.strip() if display_name else None,
            status="PENDING",
            expires_at=expires_at,
            attempt_count=0,
            max_attempts=self._policy.max_attempts,
            consumed_at=None,
            invalidated_at=None,
            version=1,
        )
        self._repository.add_challenge(challenge)
        await self._repository.flush()
        return StartedKinsunEmailChallenge(token=issued.value, expires_at=expires_at)

    async def complete(
        self,
        *,
        challenge_token: str,
        verification_code: str,
        password: str,
        invitation_code: str | None,
        trace_id: str,
        idempotency_key: str,
    ) -> KinsunEmailCompletion:
        try:
            token_digest = self._challenge_codec.digest_token(challenge_token)
        except ValueError:
            raise AuthenticationError("Authentication required") from None

        challenge = await self._repository.get_by_token_digest(token_digest, for_update=True)
        now = self._clock()
        if challenge is None or challenge.status != "PENDING":
            raise AuthenticationError("Authentication required")
        if challenge.expires_at <= now:
            challenge.status = "EXPIRED"
            challenge.invalidated_at = now
            challenge.version = (challenge.version or 0) + 1
            await self._repository.flush()
            return RejectedKinsunEmailAuthentication()

        challenge.attempt_count += 1
        challenge.version = (challenge.version or 0) + 1
        try:
            candidate_digest = self._challenge_codec.digest_code(
                token_digest=token_digest,
                code=verification_code,
            )
        except ValueError:
            candidate_digest = "0" * 64
        if not hmac.compare_digest(candidate_digest, challenge.code_digest):
            if challenge.attempt_count >= challenge.max_attempts:
                challenge.status = "LOCKED"
                challenge.invalidated_at = now
            await self._repository.flush()
            return RejectedKinsunEmailAuthentication()

        await self._repository.acquire_subject_lock(
            subject_digest=challenge.external_subject_digest,
            key_version=challenge.digest_key_version,
        )
        identities = await self._repository.list_identities_by_subject(
            subject_digest=challenge.external_subject_digest,
            key_version=challenge.digest_key_version,
            for_update=True,
        )
        active = [identity for identity in identities if identity.status == "ACTIVE"]
        if len(active) > 1 or (identities and not active):
            challenge.status = "REVOKED"
            challenge.invalidated_at = now
            await self._repository.flush()
            return RejectedKinsunEmailAuthentication()

        if active:
            # Email verification is registration proof, not a passwordless
            # alternate login route for an existing account.
            challenge.status = "REVOKED"
            challenge.invalidated_at = now
            await self._repository.flush()
            return RejectedKinsunEmailAuthentication()
        else:
            if challenge.intent == "STAFF":
                challenge.status = "REVOKED"
                challenge.invalidated_at = now
                await self._repository.flush()
                return RejectedKinsunEmailAuthentication()
            pending_codec = PendingIdentityTokenCodec()
            issued_pending = pending_codec.issue()
            pending = PendingExternalIdentity(
                token_digest=issued_pending.digest,
                provider="KINSUN",
                external_subject_digest=challenge.external_subject_digest,
                digest_key_version=challenge.digest_key_version,
                verified_email=challenge.email_address,
                display_name=challenge.display_name,
                intent=challenge.intent,
                status="PENDING",
                expires_at=challenge.expires_at,
                consumed_at=None,
                invalidated_at=None,
                version=1,
            )
            provider_repository = GoogleIdentityRepository(self._session, provider="KINSUN")
            provider_repository.add_pending(pending)
            await provider_repository.flush()
            onboarding = await PendingGoogleOnboardingService(
                self._session,
                app_session_service=self._app_sessions,
                family_invitation_service=self._family_invitations,
                repository=provider_repository,
                token_codec=pending_codec,
                clock=self._clock,
                provider="KINSUN",
            ).complete(
                pending_token=issued_pending.value,
                invitation_code=invitation_code,
                display_name=challenge.display_name,
                trace_id=trace_id,
                idempotency_key=idempotency_key,
            )
            await self._password_auth.create_credential(
                actor_id=onboarding.actor_id,
                password=password,
            )
            issued_session = onboarding.session

        challenge.status = "CONSUMED"
        challenge.consumed_at = now
        await self._repository.flush()
        return CompletedKinsunEmailAuthentication(session=issued_session)

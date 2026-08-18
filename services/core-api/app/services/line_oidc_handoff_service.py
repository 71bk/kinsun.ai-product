"""Resolve a verified LINE sign-in into a session or pending onboarding."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.core.oidc import LineTokenVerifier
from app.models.pending_identity import PendingExternalIdentity
from app.repositories.google_identity_repo import GoogleIdentityRepository
from app.services.app_session_service import AppSessionService, IssuedAppSession
from app.services.google_oidc_handoff_service import PendingIdentityPolicy
from app.services.line_identity_codec import LineIdentityCodec
from app.services.pending_identity_tokens import PendingIdentityTokenCodec

_AUTHENTICATION_REQUIRED = "Authentication required"


@dataclass(frozen=True)
class AuthenticatedLineHandoff:
    status: Literal["AUTHENTICATED"]
    session: IssuedAppSession


@dataclass(frozen=True)
class PendingLineHandoff:
    status: Literal["PENDING"]
    token: str
    expires_at: datetime


LineHandoffResult = AuthenticatedLineHandoff | PendingLineHandoff


class LineOidcHandoffService:
    """Fail-closed LINE handoff that never links accounts by matching email."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        verifier: LineTokenVerifier,
        identity_codec: LineIdentityCodec,
        app_session_service: AppSessionService,
        pending_policy: PendingIdentityPolicy,
        repository: GoogleIdentityRepository | None = None,
        token_codec: PendingIdentityTokenCodec | None = None,
        clock: Callable[[], datetime] | None = None,
        allow_new_accounts: bool = True,
    ) -> None:
        self._session = session
        self._verifier = verifier
        self._identity_codec = identity_codec
        self._app_session_service = app_session_service
        self._pending_policy = pending_policy
        self._repository = repository or GoogleIdentityRepository(session, provider="LINE")
        self._token_codec = token_codec or PendingIdentityTokenCodec()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._allow_new_accounts = allow_new_accounts

    async def handoff(
        self,
        *,
        id_token: str,
        expected_nonce: str,
        intent: Literal["ELDER", "FAMILY", "STAFF"],
    ) -> LineHandoffResult:
        identity = await self._verifier.verify_id_token(
            id_token,
            expected_nonce=expected_nonce,
        )
        subject_digest = self._identity_codec.digest_subject(identity.subject)
        key_version = self._identity_codec.key_version

        await self._repository.acquire_subject_lock(
            subject_digest=subject_digest,
            key_version=key_version,
        )
        identities = await self._repository.list_identities_by_subject(
            subject_digest=subject_digest,
            key_version=key_version,
            for_update=True,
        )
        pending = await self._repository.get_pending_by_subject(
            subject_digest=subject_digest,
            key_version=key_version,
            for_update=True,
        )
        now = self._clock()
        active = [candidate for candidate in identities if candidate.status == "ACTIVE"]

        if len(active) > 1:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        if active:
            if pending is not None:
                self._invalidate_pending(pending, now=now, status="REVOKED")
                await self._repository.flush()
            active[0].last_seen_at = now
            active[0].version = (active[0].version or 0) + 1
            issued = await self._app_session_service.issue(external_identity_id=active[0].id)
            return AuthenticatedLineHandoff(status="AUTHENTICATED", session=issued)

        if identities or intent == "STAFF" or not self._allow_new_accounts:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        if pending is not None:
            terminal_status: Literal["EXPIRED", "REVOKED"] = (
                "EXPIRED" if pending.expires_at <= now else "REVOKED"
            )
            self._invalidate_pending(pending, now=now, status=terminal_status)
            await self._repository.flush()

        issued_pending = self._token_codec.issue()
        expires_at = now + self._pending_policy.ttl
        record = PendingExternalIdentity(
            token_digest=issued_pending.digest,
            provider="LINE",
            external_subject_digest=subject_digest,
            digest_key_version=key_version,
            verified_email=identity.email,
            display_name=identity.display_name,
            intent=intent,
            status="PENDING",
            expires_at=expires_at,
            consumed_at=None,
            invalidated_at=None,
            version=1,
        )
        self._repository.add_pending(record)
        await self._repository.flush()
        return PendingLineHandoff(
            status="PENDING",
            token=issued_pending.value,
            expires_at=expires_at,
        )

    @staticmethod
    def _invalidate_pending(
        pending: PendingExternalIdentity,
        *,
        now: datetime,
        status: Literal["EXPIRED", "REVOKED"],
    ) -> None:
        pending.status = status
        pending.invalidated_at = now
        pending.version = (pending.version or 0) + 1

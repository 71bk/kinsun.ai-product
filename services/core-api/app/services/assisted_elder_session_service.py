"""Issue, exchange, validate, touch, and end accountless Elder tablet sessions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.config import Settings
from app.core.exceptions import AuthenticationError, NotFoundError, ServiceUnavailableError
from app.models.assisted_elder_session import AssistedElderSession
from app.models.elder import Elder
from app.repositories.actor_repo import ActorRepository
from app.repositories.assisted_elder_session_repo import AssistedElderSessionRepository
from app.repositories.elder_enrollment_repo import ElderEnrollmentRepository
from app.repositories.elder_repo import ElderRepository
from app.services.actor_context_resolver import resolve_active_actor_context
from app.services.assisted_session_tokens import AssistedSessionTokenCodec
from app.services.authorization_service import authorize_elder_with_decision

_AUTHENTICATION_REQUIRED = "Assisted Elder Session is unavailable"


@dataclass(frozen=True)
class AssistedElderSessionPolicy:
    pairing_ttl: timedelta
    idle_ttl: timedelta
    absolute_ttl: timedelta
    touch_interval: timedelta = timedelta(minutes=1)

    def __post_init__(self) -> None:
        durations = (
            self.pairing_ttl,
            self.idle_ttl,
            self.absolute_ttl,
            self.touch_interval,
        )
        if min(durations) <= timedelta(0):
            raise ValueError("Assisted Elder Session policy durations must be positive")
        if self.idle_ttl > self.absolute_ttl:
            raise ValueError("Assisted Elder Session idle TTL must not exceed absolute TTL")
        if self.pairing_ttl > self.absolute_ttl:
            raise ValueError("Pairing TTL must not exceed Assisted Elder Session absolute TTL")
        if self.touch_interval >= self.idle_ttl:
            raise ValueError("Touch interval must be shorter than idle TTL")

    @classmethod
    def from_settings(cls, settings: Settings) -> AssistedElderSessionPolicy:
        return cls(
            pairing_ttl=timedelta(seconds=settings.assisted_elder_pairing_ttl_seconds),
            idle_ttl=timedelta(seconds=settings.assisted_elder_idle_ttl_seconds),
            absolute_ttl=timedelta(seconds=settings.assisted_elder_absolute_ttl_seconds),
        )


@dataclass(frozen=True)
class IssuedPairing:
    assisted_session: AssistedElderSession
    pairing_token: str


@dataclass(frozen=True)
class ActivatedAssistedSession:
    assisted_session: AssistedElderSession
    elder: Elder
    session_token: str


@dataclass(frozen=True)
class ResolvedAssistedSession:
    assisted_session: AssistedElderSession
    elder: Elder
    actor_context: ActorContext


class AssistedElderSessionService:
    def __init__(
        self,
        session: AsyncSession,
        policy: AssistedElderSessionPolicy,
        *,
        enabled: bool,
        codec: AssistedSessionTokenCodec | None = None,
        repository: AssistedElderSessionRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._policy = policy
        self._enabled = enabled
        self._codec = codec or AssistedSessionTokenCodec()
        self._repository = repository or AssistedElderSessionRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    def _require_enabled(self) -> None:
        if not self._enabled:
            raise ServiceUnavailableError("Assisted Elder Session is not enabled")

    async def issue(
        self,
        *,
        actor_context: ActorContext,
        elder_id: UUID,
    ) -> IssuedPairing:
        self._require_enabled()
        now = self._clock()
        decision = await authorize_elder_with_decision(
            self._session,
            actor_context,
            elder_id,
            "assisted_session:create",
        )
        if decision.source_id is None or decision.source_type not in {"relationship", "assignment"}:
            raise NotFoundError("Resource not found")
        enrollment = await ElderEnrollmentRepository(
            self._session,
            actor_context.tenant_id,
        ).get_active(elder_id=elder_id, current_time=now, for_update=True)
        if enrollment is None:
            raise NotFoundError("Resource not found")

        for previous in await self._repository.list_live_for_elder(
            tenant_id=actor_context.tenant_id,
            elder_id=elder_id,
            for_update=True,
        ):
            previous.status = "ENDED"
            previous.ended_at = now
            previous.version += 1

        token = self._codec.issue_pairing()
        assisted_session = AssistedElderSession(
            tenant_id=actor_context.tenant_id,
            elder_id=elder_id,
            enrollment_id=enrollment.id,
            initiated_by_actor_id=actor_context.actor_id,
            initiator_mode="STAFF_ASSISTED",
            authorization_source_type=decision.source_type.upper(),
            authorization_source_id=decision.source_id,
            pairing_token_digest=token.digest,
            status="PAIRING",
            pairing_expires_at=now + self._policy.pairing_ttl,
            absolute_expires_at=now + self._policy.absolute_ttl,
        )
        self._repository.add(assisted_session)
        await self._repository.flush()
        return IssuedPairing(assisted_session=assisted_session, pairing_token=token.value)

    async def exchange(self, pairing_token: str) -> ActivatedAssistedSession:
        self._require_enabled()
        try:
            digest = self._codec.digest_pairing(pairing_token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        assisted_session = await self._repository.get_by_pairing_digest(
            digest,
            for_update=True,
        )
        now = self._clock()
        if (
            assisted_session is None
            or assisted_session.status != "PAIRING"
            or assisted_session.pairing_expires_at <= now
            or assisted_session.absolute_expires_at <= now
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        actor_context = await self._require_live_scope(
            assisted_session,
            requested_action="assisted_session:create",
            now=now,
        )
        elder = await ElderRepository(self._session, actor_context.tenant_id).get_by_id(
            assisted_session.elder_id
        )
        if elder is None or elder.status != "ACTIVE":
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        token = self._codec.issue_session()
        assisted_session.session_token_digest = token.digest
        assisted_session.status = "ACTIVE"
        assisted_session.activated_at = now
        assisted_session.last_seen_at = now
        assisted_session.idle_expires_at = min(
            now + self._policy.idle_ttl,
            assisted_session.absolute_expires_at,
        )
        assisted_session.version += 1
        await self._repository.flush()
        return ActivatedAssistedSession(
            assisted_session=assisted_session,
            elder=elder,
            session_token=token.value,
        )

    async def resolve_current(
        self,
        session_token: str,
        *,
        requested_action: str,
    ) -> ResolvedAssistedSession:
        self._require_enabled()
        try:
            digest = self._codec.digest_session(session_token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        assisted_session = await self._repository.get_by_session_digest(
            digest,
            for_update=True,
        )
        now = self._clock()
        if (
            assisted_session is None
            or assisted_session.status != "ACTIVE"
            or assisted_session.idle_expires_at is None
            or assisted_session.last_seen_at is None
            or assisted_session.idle_expires_at <= now
            or assisted_session.absolute_expires_at <= now
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        actor_context = await self._require_live_scope(
            assisted_session,
            requested_action=requested_action,
            now=now,
        )
        elder = await ElderRepository(self._session, actor_context.tenant_id).get_by_id(
            assisted_session.elder_id
        )
        if elder is None or elder.status != "ACTIVE":
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        if now - assisted_session.last_seen_at >= self._policy.touch_interval:
            assisted_session.last_seen_at = now
            assisted_session.idle_expires_at = min(
                now + self._policy.idle_ttl,
                assisted_session.absolute_expires_at,
            )
            assisted_session.version += 1
            await self._repository.flush()
        return ResolvedAssistedSession(assisted_session, elder, actor_context)

    async def end(self, session_token: str) -> None:
        self._require_enabled()
        try:
            digest = self._codec.digest_session(session_token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        assisted_session = await self._repository.get_by_session_digest(
            digest,
            for_update=True,
        )
        if assisted_session is None:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        if assisted_session.status in {"ENDED", "EXPIRED"}:
            return
        if assisted_session.status != "ACTIVE":
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        assisted_session.status = "ENDED"
        assisted_session.ended_at = self._clock()
        assisted_session.version += 1
        await self._repository.flush()

    async def _require_live_scope(
        self,
        assisted_session: AssistedElderSession,
        *,
        requested_action: str,
        now: datetime,
    ) -> ActorContext:
        actor = await ActorRepository(self._session).get_active_by_id(
            assisted_session.initiated_by_actor_id
        )
        if actor is None:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        try:
            actor_context = await resolve_active_actor_context(self._session, actor, now=now)
        except AuthenticationError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        if actor_context.tenant_id != assisted_session.tenant_id:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        enrollment = await ElderEnrollmentRepository(
            self._session,
            assisted_session.tenant_id,
        ).get_active(
            elder_id=assisted_session.elder_id,
            current_time=now,
            for_update=False,
        )
        if enrollment is None or enrollment.id != assisted_session.enrollment_id:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        try:
            decision = await authorize_elder_with_decision(
                self._session,
                actor_context,
                assisted_session.elder_id,
                requested_action,
            )
        except NotFoundError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None
        expected_type = assisted_session.authorization_source_type.casefold()
        if decision.source_id != assisted_session.authorization_source_id or (
            decision.source_type != expected_type
        ):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)
        return actor_context

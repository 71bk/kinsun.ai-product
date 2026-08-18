"""Core-owned opaque application-session lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.models.app_session import AppSession
from app.repositories.app_session_repo import AppSessionRepository, ResolvedAppSession
from app.services.actor_context_resolver import resolve_active_actor_context
from app.services.app_session_tokens import AppSessionTokenCodec

_AUTHENTICATION_REQUIRED = "Authentication required"
_LONG_LIVED_ACTOR_TYPES = frozenset({"ELDER", "FAMILY_MEMBER"})


@dataclass(frozen=True)
class AppSessionPolicy:
    """Validated session lifetimes and bounded write-amplification controls."""

    elder_family_idle_ttl: timedelta
    elder_family_absolute_ttl: timedelta
    workforce_idle_ttl: timedelta
    workforce_absolute_ttl: timedelta
    touch_interval: timedelta
    recent_auth_window: timedelta
    max_active_per_actor: int

    def __post_init__(self) -> None:
        durations = (
            self.elder_family_idle_ttl,
            self.elder_family_absolute_ttl,
            self.workforce_idle_ttl,
            self.workforce_absolute_ttl,
            self.touch_interval,
            self.recent_auth_window,
        )
        if any(duration <= timedelta(0) for duration in durations):
            raise ValueError("App Session policy durations must be positive")
        if self.elder_family_idle_ttl > self.elder_family_absolute_ttl:
            raise ValueError("Elder/family idle TTL must not exceed absolute TTL")
        if self.workforce_idle_ttl > self.workforce_absolute_ttl:
            raise ValueError("Workforce idle TTL must not exceed absolute TTL")
        if self.touch_interval >= min(
            self.elder_family_idle_ttl,
            self.workforce_idle_ttl,
        ):
            raise ValueError("Touch interval must be shorter than every idle TTL")
        if not 1 <= self.max_active_per_actor <= 20:
            raise ValueError("Active App Session cap must be between 1 and 20")

    @classmethod
    def from_settings(cls, settings: Settings) -> AppSessionPolicy:
        return cls(
            elder_family_idle_ttl=timedelta(
                seconds=settings.app_session_elder_family_idle_ttl_seconds
            ),
            elder_family_absolute_ttl=timedelta(
                seconds=settings.app_session_elder_family_absolute_ttl_seconds
            ),
            workforce_idle_ttl=timedelta(seconds=settings.app_session_workforce_idle_ttl_seconds),
            workforce_absolute_ttl=timedelta(
                seconds=settings.app_session_workforce_absolute_ttl_seconds
            ),
            touch_interval=timedelta(seconds=settings.app_session_touch_interval_seconds),
            recent_auth_window=timedelta(seconds=settings.app_session_recent_auth_window_seconds),
            max_active_per_actor=settings.app_session_max_active_per_actor,
        )

    def lifetimes_for(self, actor_type: str) -> tuple[timedelta, timedelta]:
        if actor_type in _LONG_LIVED_ACTOR_TYPES:
            return self.elder_family_idle_ttl, self.elder_family_absolute_ttl
        return self.workforce_idle_ttl, self.workforce_absolute_ttl


@dataclass(frozen=True)
class IssuedAppSession:
    """Raw session credential returned exactly once to the future BFF adapter."""

    token: str
    session_id: UUID
    idle_expires_at: datetime
    absolute_expires_at: datetime


class AppSessionService:
    """Issue, validate, touch and revoke sessions without owning transaction commit."""

    def __init__(
        self,
        session: AsyncSession,
        policy: AppSessionPolicy,
        *,
        codec: AppSessionTokenCodec | None = None,
        repository: AppSessionRepository | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._policy = policy
        self._codec = codec or AppSessionTokenCodec()
        self._repository = repository or AppSessionRepository(session)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def issue(self, *, external_identity_id: UUID) -> IssuedAppSession:
        """Issue a new credential only for an already-verified active identity."""
        now = self._clock()
        resolved = await self._repository.get_active_identity(
            external_identity_id,
            for_update=True,
        )
        if resolved is None or resolved.actor.actor_type == "SYSTEM_SERVICE":
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        # Issuance must obey the same live Core membership gate as requests.
        await resolve_active_actor_context(self._session, resolved.actor, now=now)
        idle_ttl, absolute_ttl = self._policy.lifetimes_for(resolved.actor.actor_type)
        token = self._codec.issue()
        absolute_expires_at = now + absolute_ttl
        app_session = AppSession(
            token_digest=token.digest,
            actor_id=resolved.actor.id,
            external_identity_id=resolved.identity.id,
            status="ACTIVE",
            authenticated_at=now,
            last_seen_at=now,
            idle_expires_at=min(now + idle_ttl, absolute_expires_at),
            absolute_expires_at=absolute_expires_at,
        )
        self._repository.add(app_session)
        await self._repository.flush()

        await self._repository.revoke_expired_for_actor(actor_id=resolved.actor.id, now=now)
        live_sessions = await self._repository.list_live_for_actor(
            actor_id=resolved.actor.id,
            now=now,
            for_update=True,
        )
        # Always retain the credential being returned, even if database clock
        # precision makes its authenticated_at tie with an older session.
        older_sessions = [
            candidate for candidate in live_sessions if candidate.id != app_session.id
        ]
        for superseded in older_sessions[self._policy.max_active_per_actor - 1 :]:
            self._revoke_model(superseded, now)
        await self._repository.flush()

        return IssuedAppSession(
            token=token.value,
            session_id=app_session.id,
            idle_expires_at=app_session.idle_expires_at,
            absolute_expires_at=app_session.absolute_expires_at,
        )

    async def authenticate(self, token: str) -> ActorContext:
        """Resolve one raw token against current session and authorization state."""
        try:
            token_digest = self._codec.digest(token)
        except ValueError:
            raise AuthenticationError(_AUTHENTICATION_REQUIRED) from None

        resolved = await self._repository.get_by_digest(token_digest, for_update=False)
        now = self._clock()
        if resolved is None or not self._is_usable(resolved, now):
            raise AuthenticationError(_AUTHENTICATION_REQUIRED)

        actor_context = await resolve_active_actor_context(
            self._session,
            resolved.actor,
            now=now,
        )
        app_session = resolved.app_session
        if now - app_session.last_seen_at >= self._policy.touch_interval:
            idle_ttl, _ = self._policy.lifetimes_for(resolved.actor.actor_type)
            app_session.last_seen_at = now
            app_session.idle_expires_at = min(
                now + idle_ttl,
                app_session.absolute_expires_at,
            )
            app_session.version += 1
            await self._repository.flush()
        return actor_context

    async def revoke(self, token: str) -> bool:
        """Idempotently revoke a credential without revealing whether it existed."""
        try:
            token_digest = self._codec.digest(token)
        except ValueError:
            return False

        resolved = await self._repository.get_by_digest(token_digest, for_update=True)
        if resolved is None or resolved.app_session.status != "ACTIVE":
            return False
        self._revoke_model(resolved.app_session, self._clock())
        await self._repository.flush()
        return True

    def is_recently_authenticated(self, app_session: AppSession) -> bool:
        """Support the future identity-linking recent-auth gate."""
        now = self._clock()
        return (
            app_session.status == "ACTIVE"
            and app_session.authenticated_at <= now
            and now - app_session.authenticated_at <= self._policy.recent_auth_window
            and app_session.idle_expires_at > now
            and app_session.absolute_expires_at > now
        )

    @staticmethod
    def _is_usable(resolved: ResolvedAppSession, now: datetime) -> bool:
        app_session = resolved.app_session
        return (
            app_session.status == "ACTIVE"
            and resolved.identity.status == "ACTIVE"
            and resolved.actor.status == "ACTIVE"
            and app_session.last_seen_at <= now
            and app_session.authenticated_at <= now
            and app_session.idle_expires_at > now
            and app_session.absolute_expires_at > now
        )

    @staticmethod
    def _revoke_model(app_session: AppSession, now: datetime) -> None:
        app_session.status = "REVOKED"
        app_session.revoked_at = now
        app_session.version += 1

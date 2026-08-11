"""Persistence operations for Core-owned opaque application sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.actor import Actor
from app.models.app_session import AppSession
from app.models.line_identity import ExternalIdentity


@dataclass(frozen=True)
class ResolvedExternalIdentity:
    identity: ExternalIdentity
    actor: Actor


@dataclass(frozen=True)
class ResolvedAppSession:
    app_session: AppSession
    identity: ExternalIdentity
    actor: Actor


class AppSessionRepository:
    """Store digests only and resolve every session against current identity state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, app_session: AppSession) -> None:
        self._session.add(app_session)

    async def flush(self) -> None:
        await self._session.flush()

    async def get_active_identity(
        self,
        external_identity_id: UUID,
        *,
        for_update: bool = False,
    ) -> ResolvedExternalIdentity | None:
        statement = (
            select(ExternalIdentity, Actor)
            .join(Actor, Actor.id == ExternalIdentity.actor_id)
            .where(
                ExternalIdentity.id == external_identity_id,
                ExternalIdentity.status == "ACTIVE",
                Actor.status == "ACTIVE",
            )
        )
        if for_update:
            statement = statement.with_for_update()
        result = (await self._session.execute(statement)).one_or_none()
        if result is None:
            return None
        identity, actor = result
        return ResolvedExternalIdentity(identity=identity, actor=actor)

    async def get_by_digest(
        self,
        token_digest: str,
        *,
        for_update: bool = False,
    ) -> ResolvedAppSession | None:
        statement = (
            select(AppSession, ExternalIdentity, Actor)
            .join(ExternalIdentity, ExternalIdentity.id == AppSession.external_identity_id)
            .join(Actor, Actor.id == AppSession.actor_id)
            .where(AppSession.token_digest == token_digest)
        )
        if for_update:
            statement = statement.with_for_update()
        result = (await self._session.execute(statement)).one_or_none()
        if result is None:
            return None
        app_session, identity, actor = result
        return ResolvedAppSession(
            app_session=app_session,
            identity=identity,
            actor=actor,
        )

    async def revoke_expired_for_actor(self, *, actor_id: UUID, now: datetime) -> None:
        await self._session.execute(
            update(AppSession)
            .where(
                AppSession.actor_id == actor_id,
                AppSession.status == "ACTIVE",
                ((AppSession.idle_expires_at <= now) | (AppSession.absolute_expires_at <= now)),
            )
            .values(
                status="REVOKED",
                revoked_at=now,
                version=AppSession.version + 1,
            )
        )

    async def list_live_for_actor(
        self,
        *,
        actor_id: UUID,
        now: datetime,
        for_update: bool = False,
    ) -> list[AppSession]:
        statement = (
            select(AppSession)
            .where(
                AppSession.actor_id == actor_id,
                AppSession.status == "ACTIVE",
                AppSession.idle_expires_at > now,
                AppSession.absolute_expires_at > now,
            )
            .order_by(
                AppSession.authenticated_at.desc(),
                AppSession.id.desc(),
            )
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        return list(result.scalars().all())

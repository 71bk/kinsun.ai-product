"""Persistence for one-time pairing and active assisted Elder sessions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assisted_elder_session import AssistedElderSession


class AssistedElderSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, assisted_session: AssistedElderSession) -> None:
        self._session.add(assisted_session)

    async def flush(self) -> None:
        await self._session.flush()

    async def get_by_pairing_digest(
        self,
        digest: str,
        *,
        for_update: bool,
    ) -> AssistedElderSession | None:
        stmt = select(AssistedElderSession).where(
            AssistedElderSession.pairing_token_digest == digest
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_session_digest(
        self,
        digest: str,
        *,
        for_update: bool,
    ) -> AssistedElderSession | None:
        stmt = select(AssistedElderSession).where(
            AssistedElderSession.session_token_digest == digest
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_live_for_elder(
        self,
        *,
        tenant_id: UUID,
        elder_id: UUID,
        for_update: bool,
    ) -> list[AssistedElderSession]:
        stmt = select(AssistedElderSession).where(
            AssistedElderSession.tenant_id == tenant_id,
            AssistedElderSession.elder_id == elder_id,
            AssistedElderSession.status.in_(["PAIRING", "ACTIVE"]),
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

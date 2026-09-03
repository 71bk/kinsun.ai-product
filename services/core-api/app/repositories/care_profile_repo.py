"""Tenant-scoped Care Profile persistence and bounded AI context reads."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.care_profile import ElderCareProfileEntry
from app.repositories.base import BaseRepository


class CareProfileRepository(BaseRepository):
    def add(self, entry: ElderCareProfileEntry) -> None:
        self._session.add(entry)

    async def flush(self) -> None:
        await self._session.flush()

    async def list_for_elder(self, elder_id: UUID) -> list[ElderCareProfileEntry]:
        result = await self._session.execute(
            select(ElderCareProfileEntry)
            .where(
                ElderCareProfileEntry.tenant_id == self._tenant_id,
                ElderCareProfileEntry.elder_id == elder_id,
            )
            .order_by(ElderCareProfileEntry.created_at, ElderCareProfileEntry.id)
        )
        return list(result.scalars().all())

    async def list_active_ai_context(
        self,
        *,
        elder_id: UUID,
        limit: int = 20,
    ) -> list[ElderCareProfileEntry]:
        result = await self._session.execute(
            select(ElderCareProfileEntry)
            .where(
                ElderCareProfileEntry.tenant_id == self._tenant_id,
                ElderCareProfileEntry.elder_id == elder_id,
                ElderCareProfileEntry.verification_status.in_(["RECORDED", "VERIFIED"]),
                ElderCareProfileEntry.retired_at.is_(None),
            )
            .order_by(
                ElderCareProfileEntry.category,
                ElderCareProfileEntry.created_at,
                ElderCareProfileEntry.id,
            )
            .limit(limit)
        )
        return list(result.scalars().all())

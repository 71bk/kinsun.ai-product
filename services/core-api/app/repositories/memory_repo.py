"""Tenant-scoped confirmed-memory persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.models.memory import Memory, MemoryVersion
from app.repositories.base import BaseRepository


class MemoryRepository(BaseRepository):
    def add_memory(self, memory: Memory) -> None:
        self._session.add(memory)

    def add_version(self, version: MemoryVersion) -> None:
        self._session.add(version)

    async def get(self, elder_id: UUID, memory_id: UUID) -> Memory | None:
        result = await self._session.execute(
            select(Memory).where(
                Memory.id == memory_id,
                Memory.elder_id == elder_id,
                Memory.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_current_version(self, memory: Memory) -> MemoryVersion:
        result = await self._session.execute(
            select(MemoryVersion).where(
                MemoryVersion.memory_id == memory.id,
                MemoryVersion.version == memory.current_version,
            )
        )
        return result.scalar_one()

    async def list_for_deletion(self, *, elder_id: UUID) -> list[Memory]:
        result = await self._session.execute(
            select(Memory)
            .where(
                Memory.elder_id == elder_id,
                Memory.tenant_id == self._tenant_id,
            )
            .order_by(Memory.id)
            .with_for_update()
        )
        return list(result.scalars().all())

    async def list_versions_for_deletion(
        self,
        *,
        memory_ids: list[UUID],
    ) -> list[MemoryVersion]:
        if not memory_ids:
            return []
        result = await self._session.execute(
            select(MemoryVersion)
            .where(MemoryVersion.memory_id.in_(memory_ids))
            .order_by(MemoryVersion.memory_id, MemoryVersion.version)
            .with_for_update()
        )
        return list(result.scalars().all())

    async def list_for_elder(
        self,
        *,
        elder_id: UUID,
        statuses: list[str],
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> list[Memory]:
        stmt = select(Memory).where(
            Memory.elder_id == elder_id,
            Memory.tenant_id == self._tenant_id,
            Memory.status.in_(statuses),
        )
        if cursor:
            created_at, memory_id = cursor
            stmt = stmt.where(
                or_(
                    Memory.created_at < created_at,
                    and_(
                        Memory.created_at == created_at,
                        Memory.id < memory_id,
                    ),
                )
            )
        result = await self._session.execute(
            stmt.order_by(Memory.created_at.desc(), Memory.id.desc()).limit(limit + 1)
        )
        return list(result.scalars().all())

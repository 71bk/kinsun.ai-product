"""Tenant-scoped confirmed-memory persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.models.memory import Memory, MemoryVersion
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class ConfirmedMemoryContextRecord:
    """Minimal current memory data that may cross the private Agent boundary."""

    memory_id: UUID
    version: int
    memory_type: str
    content: str
    consent_version: int


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

    async def list_active_context_for_elder(
        self,
        *,
        elder_id: UUID,
        max_consent_version: int,
        limit: int,
    ) -> list[ConfirmedMemoryContextRecord]:
        """Return only bounded, current, active memory versions for Agent context."""
        result = await self._session.execute(
            select(
                Memory.id,
                Memory.current_version,
                Memory.memory_type,
                MemoryVersion.content,
                Memory.consent_version,
            )
            .join(
                MemoryVersion,
                and_(
                    MemoryVersion.memory_id == Memory.id,
                    MemoryVersion.version == Memory.current_version,
                ),
            )
            .where(
                Memory.elder_id == elder_id,
                Memory.tenant_id == self._tenant_id,
                Memory.status == "ACTIVE",
                Memory.deleted_at.is_(None),
                Memory.consent_version > 0,
                Memory.consent_version <= max_consent_version,
                MemoryVersion.version_status == "ACTIVE",
                MemoryVersion.valid_to.is_(None),
                func.char_length(MemoryVersion.content).between(1, 500),
            )
            .order_by(Memory.updated_at.desc(), Memory.id.desc())
            .limit(limit)
        )
        return [
            ConfirmedMemoryContextRecord(
                memory_id=row[0],
                version=row[1],
                memory_type=row[2],
                content=row[3],
                consent_version=row[4],
            )
            for row in result.all()
        ]

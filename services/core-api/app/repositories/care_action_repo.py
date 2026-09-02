"""Tenant-scoped Care Action persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.models.care_action import CareAction
from app.repositories.base import BaseRepository


class CareActionRepository(BaseRepository):
    def add(self, action: CareAction) -> None:
        self._session.add(action)

    async def get(self, elder_id: UUID, care_action_id: UUID) -> CareAction | None:
        result = await self._session.execute(
            select(CareAction).where(
                CareAction.id == care_action_id,
                CareAction.elder_id == elder_id,
                CareAction.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_elder(
        self,
        *,
        elder_id: UUID,
        statuses: list[str] | None,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> list[CareAction]:
        stmt = select(CareAction).where(
            CareAction.elder_id == elder_id,
            CareAction.tenant_id == self._tenant_id,
        )
        if statuses:
            stmt = stmt.where(CareAction.status.in_(statuses))
        if cursor is not None:
            created_at, action_id = cursor
            stmt = stmt.where(
                or_(
                    CareAction.created_at < created_at,
                    and_(
                        CareAction.created_at == created_at,
                        CareAction.id < action_id,
                    ),
                )
            )
        result = await self._session.execute(
            stmt.order_by(CareAction.created_at.desc(), CareAction.id.desc()).limit(limit + 1)
        )
        return list(result.scalars().all())

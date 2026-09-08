"""Tenant-scoped Care Action persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.models.care_action import CareAction
from app.repositories.base import BaseRepository


class CareActionRepository(BaseRepository):
    async def count_open_by_elder(self, elder_ids: list[UUID]) -> dict[UUID, int]:
        """Count unfinished formal actions only within the authorized page.

        Authorization is the caller's responsibility. Never load action content
        or join provenance (which could multiply the count).
        """
        if not elder_ids:
            return {}
        result = await self._session.execute(
            select(CareAction.elder_id, func.count(CareAction.id))
            .where(
                CareAction.tenant_id == self._tenant_id,
                CareAction.elder_id.in_(elder_ids),
                CareAction.status.in_(["OPEN", "IN_PROGRESS", "POSTPONED"]),
            )
            .group_by(CareAction.elder_id)
        )
        return {elder_id: count for elder_id, count in result.all()}

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

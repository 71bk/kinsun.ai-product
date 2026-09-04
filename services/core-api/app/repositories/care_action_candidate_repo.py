"""Tenant-scoped Care Action candidate persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.models.care_action_candidate import CareActionCandidate
from app.repositories.base import BaseRepository


class CareActionCandidateRepository(BaseRepository):
    def add(self, candidate: CareActionCandidate) -> None:
        self._session.add(candidate)

    async def get(
        self,
        elder_id: UUID,
        candidate_id: UUID,
        *,
        for_update: bool = False,
    ) -> CareActionCandidate | None:
        stmt = select(CareActionCandidate).where(
            CareActionCandidate.id == candidate_id,
            CareActionCandidate.elder_id == elder_id,
            CareActionCandidate.tenant_id == self._tenant_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_elder(
        self,
        *,
        elder_id: UUID,
        statuses: list[str],
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> list[CareActionCandidate]:
        stmt = select(CareActionCandidate).where(
            CareActionCandidate.elder_id == elder_id,
            CareActionCandidate.tenant_id == self._tenant_id,
            CareActionCandidate.status.in_(statuses),
        )
        if cursor is not None:
            created_at, candidate_id = cursor
            stmt = stmt.where(
                or_(
                    CareActionCandidate.created_at < created_at,
                    and_(
                        CareActionCandidate.created_at == created_at,
                        CareActionCandidate.id < candidate_id,
                    ),
                )
            )
        result = await self._session.execute(
            stmt.order_by(
                CareActionCandidate.created_at.desc(),
                CareActionCandidate.id.desc(),
            ).limit(limit + 1)
        )
        return list(result.scalars().all())

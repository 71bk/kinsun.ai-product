"""Tenant-scoped Elder service-enrollment queries."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select

from app.models.elder_enrollment import ElderEnrollment
from app.repositories.base import BaseRepository


class ElderEnrollmentRepository(BaseRepository):
    def add(self, enrollment: ElderEnrollment) -> None:
        self._session.add(enrollment)

    async def flush(self) -> None:
        await self._session.flush()

    async def get_active(
        self,
        *,
        elder_id: UUID,
        current_time: datetime,
        for_update: bool = False,
    ) -> ElderEnrollment | None:
        stmt = (
            select(ElderEnrollment)
            .where(
                ElderEnrollment.tenant_id == self._tenant_id,
                ElderEnrollment.elder_id == elder_id,
                ElderEnrollment.status == "ACTIVE",
                ElderEnrollment.valid_from <= current_time,
                or_(
                    ElderEnrollment.valid_until.is_(None),
                    current_time < ElderEnrollment.valid_until,
                ),
            )
            .order_by(ElderEnrollment.valid_from.desc(), ElderEnrollment.id.desc())
            .limit(1)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    async def get_created_for_elder(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
    ) -> ElderEnrollment | None:
        result = await self._session.execute(
            select(ElderEnrollment)
            .where(
                ElderEnrollment.tenant_id == self._tenant_id,
                ElderEnrollment.elder_id == elder_id,
                ElderEnrollment.created_by_actor_id == actor_id,
            )
            .order_by(ElderEnrollment.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

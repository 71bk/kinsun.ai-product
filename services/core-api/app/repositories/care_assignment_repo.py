"""CareAssignment repository — tenant-scoped data access for care assignments.

Provides query methods for verifying active care worker assignments
and listing authorized elders. All queries enforce tenant isolation
via BaseRepository and time-bounded authorization checks.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, select

from app.models.care_assignment import CareAssignment
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.repositories.base import BaseRepository
from app.repositories.types import AuthorizedElderRow


class CareAssignmentRepository(BaseRepository):
    """Repository for CareAssignment entities, scoped by tenant_id.

    All queries include an explicit WHERE tenant_id = :tenant_id
    predicate inherited from BaseRepository.
    """

    async def find_valid_for_worker(
        self, worker_id: UUID, elder_id: UUID, current_time: datetime
    ) -> CareAssignment | None:
        """Find an active assignment for the given worker-elder pair.

        Verifies that the worker currently has a valid, time-bounded
        assignment to the specified elder. All of the following must
        be true:
        - worker_id matches
        - elder_id matches
        - tenant_id matches (inherited scope)
        - status is CONFIRMED or IN_PROGRESS
        - service_start <= current_time < service_end

        Args:
            worker_id: The UUID of the care worker.
            elder_id: The UUID of the elder.
            current_time: The current timestamp for time-window checks.

        Returns:
            The matching CareAssignment if found, or None.
        """
        stmt = select(CareAssignment).where(
            and_(
                CareAssignment.worker_id == worker_id,
                CareAssignment.elder_id == elder_id,
                CareAssignment.tenant_id == self._tenant_id,
                CareAssignment.status.in_(["CONFIRMED", "IN_PROGRESS"]),
                CareAssignment.service_start <= current_time,
                current_time < CareAssignment.service_end,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, assignment_id: UUID) -> CareAssignment | None:
        result = await self._session.execute(
            select(CareAssignment).where(
                CareAssignment.id == assignment_id,
                CareAssignment.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_worker(
        self,
        *,
        worker_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> list[CareAssignment]:
        result = await self._session.execute(
            select(CareAssignment)
            .where(
                CareAssignment.worker_id == worker_id,
                CareAssignment.tenant_id == self._tenant_id,
                CareAssignment.service_start < window_end,
                CareAssignment.service_end > window_start,
                CareAssignment.status.notin_(["CANCELLED", "EXPIRED"]),
            )
            .order_by(CareAssignment.service_start, CareAssignment.id)
            .limit(100)
        )
        return list(result.scalars().all())

    def add(self, assignment: CareAssignment) -> None:
        self._session.add(assignment)

    async def find_authorized_elders_by_worker(
        self, worker_id: UUID, current_time: datetime
    ) -> list[AuthorizedElderRow]:
        """List elders that a worker is currently authorized to access.

        Returns distinct elders joined with their care unit name,
        where the worker has at least one active assignment within
        the current time window.

        Args:
            worker_id: The UUID of the care worker.
            current_time: The current timestamp for time-window checks.

        Returns:
            A list of AuthorizedElderRow named tuples, ordered by
            display_name then elder_id.
        """
        deduplicated = (
            select(
                Elder.id.label("elder_id"),
                Elder.display_name.label("display_name"),
                CareUnit.name.label("care_unit_name"),
            )
            .distinct(Elder.id)
            .select_from(CareAssignment)
            .join(
                Elder,
                and_(
                    CareAssignment.elder_id == Elder.id,
                    Elder.tenant_id == CareAssignment.tenant_id,
                ),
            )
            .join(CareUnit, CareAssignment.care_unit_id == CareUnit.id)
            .where(
                and_(
                    CareAssignment.worker_id == worker_id,
                    CareAssignment.tenant_id == self._tenant_id,
                    CareAssignment.status.in_(["CONFIRMED", "IN_PROGRESS"]),
                    CareAssignment.service_start <= current_time,
                    current_time < CareAssignment.service_end,
                )
            )
            # PostgreSQL requires DISTINCT ON expressions to lead ORDER BY.
            # Care-unit name makes the selected row deterministic when more
            # than one active assignment grants access to the same elder.
            .order_by(Elder.id, CareUnit.name)
        )
        authorized_elders = deduplicated.subquery()
        stmt = select(
            authorized_elders.c.elder_id,
            authorized_elders.c.display_name,
            authorized_elders.c.care_unit_name,
        ).order_by(
            authorized_elders.c.display_name,
            authorized_elders.c.elder_id,
        )
        result = await self._session.execute(stmt)
        return [
            AuthorizedElderRow(
                elder_id=row.elder_id,
                display_name=row.display_name,
                care_unit_name=row.care_unit_name,
            )
            for row in result.all()
        ]

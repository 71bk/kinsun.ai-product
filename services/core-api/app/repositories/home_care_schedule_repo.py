"""Minimal, live-authorized schedule projection; never elder clinical content."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Date, and_, cast, exists, func, or_, select, tuple_

from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant
from app.repositories.base import BaseRepository


class HomeCareScheduleRepository(BaseRepository):
    async def list_today(
        self,
        worker_id: UUID,
        now: datetime,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ):
        local_day = cast(func.timezone(Elder.timezone, now), Date)
        membership = exists(
            select(ActorTenantMembership.id).where(
                ActorTenantMembership.actor_id == worker_id,
                ActorTenantMembership.tenant_id == self._tenant_id,
                ActorTenantMembership.role_code == "HOME_CARE_WORKER",
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    ActorTenantMembership.effective_to > now,
                ),
                or_(
                    ActorTenantMembership.care_unit_id.is_(None),
                    ActorTenantMembership.care_unit_id == CareAssignment.care_unit_id,
                ),
            )
        )
        stmt = (
            select(
                CareAssignment.id.label("assignment_id"),
                Elder.id.label("elder_id"),
                Elder.display_name,
                CareAssignment.service_start.label("scheduled_start"),
                CareAssignment.service_end.label("scheduled_end"),
                CareAssignment.status,
                Elder.timezone,
                local_day.label("local_date"),
            )
            .select_from(CareAssignment)
            .join(
                Elder, and_(Elder.id == CareAssignment.elder_id, Elder.tenant_id == self._tenant_id)
            )
            .join(
                CareUnit,
                and_(
                    CareUnit.id == CareAssignment.care_unit_id,
                    CareUnit.tenant_id == self._tenant_id,
                ),
            )
            .join(Actor, Actor.id == CareAssignment.worker_id)
            .join(Tenant, Tenant.id == CareAssignment.tenant_id)
            .where(
                CareAssignment.tenant_id == self._tenant_id,
                CareAssignment.worker_id == worker_id,
                Actor.actor_type == "HOME_CARE_WORKER",
                Actor.status == "ACTIVE",
                Tenant.status == "ACTIVE",
                Elder.status == "ACTIVE",
                CareUnit.status == "ACTIVE",
                membership,
                CareAssignment.status.in_(["CONFIRMED", "IN_PROGRESS"]),
                or_(CareAssignment.status == "CONFIRMED", CareAssignment.service_start <= now),
                CareAssignment.service_scope.contains(["assignment:read", "elder:basic:read"]),
                CareAssignment.service_end > now,
                CareAssignment.service_end > CareAssignment.service_start,
                cast(func.timezone(Elder.timezone, CareAssignment.service_start), Date)
                <= local_day,
            )
            .order_by(CareAssignment.service_start, CareAssignment.id)
            .limit(limit + 1)
        )
        if after is not None:
            stmt = stmt.where(tuple_(CareAssignment.service_start, CareAssignment.id) > after)
        return (await self._session.execute(stmt)).mappings().all()

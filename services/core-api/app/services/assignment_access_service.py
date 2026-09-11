"""Live exact-assignment authorization shared by visit and record commands."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import ActorContext
from app.core.exceptions import NotFoundError
from app.models.actor import Actor
from app.models.care_assignment import CareAssignment
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant


class AssignmentAccessService:
    def __init__(self, session: AsyncSession, actor: ActorContext):
        self.session = session
        self.actor = actor

    async def authorize(
        self,
        assignment_id: UUID,
        *,
        required_scopes: frozenset[str],
        allowed_statuses: frozenset[str],
    ) -> tuple[CareAssignment, str]:
        actor = self.actor
        if actor.status != "ACTIVE" or actor.actor_role != "HOME_CARE_WORKER":
            raise NotFoundError("Resource not found")
        # Serializes submissions for the exact assignment, not another visit for this elder.
        assignment = await self.session.scalar(
            select(CareAssignment)
            .where(
                CareAssignment.id == assignment_id,
                CareAssignment.tenant_id == actor.tenant_id,
                CareAssignment.worker_id == actor.actor_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(UTC)  # After any lock wait, never client-controlled.
        if (
            assignment is None
            or assignment.status not in allowed_statuses
            or not (assignment.service_start <= now < assignment.service_end)
            or not required_scopes.issubset(assignment.service_scope or [])
        ):
            raise NotFoundError("Resource not found")
        membership = exists(
            select(ActorTenantMembership.id).where(
                ActorTenantMembership.actor_id == actor.actor_id,
                ActorTenantMembership.tenant_id == actor.tenant_id,
                ActorTenantMembership.role_code == "HOME_CARE_WORKER",
                ActorTenantMembership.status == "ACTIVE",
                ActorTenantMembership.effective_from <= now,
                or_(
                    ActorTenantMembership.effective_to.is_(None),
                    ActorTenantMembership.effective_to > now,
                ),
                or_(
                    ActorTenantMembership.care_unit_id.is_(None),
                    ActorTenantMembership.care_unit_id == assignment.care_unit_id,
                ),
            )
        )
        timezone = await self.session.scalar(
            select(Elder.timezone).where(
                Elder.id == assignment.elder_id,
                Elder.tenant_id == actor.tenant_id,
                Elder.status == "ACTIVE",
                exists(
                    select(Tenant.id).where(Tenant.id == actor.tenant_id, Tenant.status == "ACTIVE")
                ),
                exists(
                    select(Actor.id).where(
                        Actor.id == actor.actor_id,
                        Actor.status == "ACTIVE",
                        Actor.actor_type == "HOME_CARE_WORKER",
                    )
                ),
                exists(
                    select(CareUnit.id).where(
                        CareUnit.id == assignment.care_unit_id,
                        CareUnit.tenant_id == actor.tenant_id,
                        CareUnit.status == "ACTIVE",
                    )
                ),
                membership,
            )
        )
        if timezone is None:
            raise NotFoundError("Resource not found")
        return assignment, timezone

"""Resolve live Core authorization context from formal database state."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError
from app.middleware.auth import ActorContext
from app.models.actor import Actor
from app.models.membership import ActorTenantMembership
from app.models.tenant import Tenant

_AUTHENTICATION_REQUIRED = "Authentication required"


async def resolve_active_actor_context(
    session: AsyncSession,
    actor: Actor,
    *,
    now: datetime | None = None,
) -> ActorContext:
    """Return one live tenant context or fail closed.

    Authentication mechanisms may prove identity differently, but all of them
    must use the same Core-owned actor, membership, role and tenant rules.
    Ambiguous multi-tenant membership is rejected until an explicit tenant
    selection design is approved.
    """
    resolved_at = now or datetime.now(UTC)
    if actor.status != "ACTIVE":
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)

    result = await session.execute(
        select(ActorTenantMembership)
        .join(Tenant, Tenant.id == ActorTenantMembership.tenant_id)
        .where(
            ActorTenantMembership.actor_id == actor.id,
            ActorTenantMembership.role_code == actor.actor_type,
            ActorTenantMembership.care_unit_id.is_(None),
            ActorTenantMembership.status == "ACTIVE",
            ActorTenantMembership.effective_from <= resolved_at,
            or_(
                ActorTenantMembership.effective_to.is_(None),
                resolved_at < ActorTenantMembership.effective_to,
            ),
            Tenant.status == "ACTIVE",
        )
    )
    memberships = list(result.scalars().all())
    if len(memberships) != 1:
        raise AuthenticationError(_AUTHENTICATION_REQUIRED)

    return ActorContext(
        actor_id=actor.id,
        actor_role=actor.actor_type,
        tenant_id=memberships[0].tenant_id,
        status=actor.status,
    )

"""TenantMembershipRepository — queries tenant membership records.

This repository does NOT extend BaseRepository because membership
is not a tenant-scoped entity itself — it IS the association between
actors and tenants. It takes a session directly.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import ActorTenantMembership


class TenantMembershipRepository:
    """Repository for tenant-level membership lookups.

    Takes session only (no tenant_id in constructor) — tenant_id is
    passed explicitly per query method.

    Reads eldercare_ai.actor_tenant_membership, the same table
    CareUnitMembershipRepository uses. Rows scoped to a care unit still count
    as tenant membership, so this query does not filter on care_unit_id.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active_membership(
        self, actor_id: UUID, tenant_id: UUID
    ) -> ActorTenantMembership | None:
        """Return an active membership for actor in the given tenant.

        An actor may legitimately hold several rows for one tenant — one
        tenant-wide plus one per care unit — so this returns the first match
        rather than requiring exactly one. Without the limit, an actor
        belonging to two care units would raise MultipleResultsFound and fail
        authorization for a reason that has nothing to do with permissions.

        Args:
            actor_id: The actor's UUID.
            tenant_id: The tenant's UUID.

        Returns:
            An active ActorTenantMembership, or None.
        """
        result = await self._session.execute(
            select(ActorTenantMembership)
            .where(
                ActorTenantMembership.actor_id == actor_id,
                ActorTenantMembership.tenant_id == tenant_id,
                ActorTenantMembership.status == "ACTIVE",
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

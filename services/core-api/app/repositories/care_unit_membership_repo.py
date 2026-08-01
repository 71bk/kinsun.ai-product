"""CareUnitMembershipRepository — queries care unit membership records.

This repository does NOT extend BaseRepository because membership
is not a tenant-scoped entity itself — it IS the association between
actors and care units. It takes a session directly.

Reads eldercare_ai.actor_tenant_membership, the same table
TenantMembershipRepository uses, filtered to rows that name a care unit.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import ActorTenantMembership


class CareUnitMembershipRepository:
    """Repository for care-unit-level membership lookups.

    Takes session only (no tenant_id in constructor) — tenant_id is
    passed explicitly per query method.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def is_member(self, actor_id: UUID, care_unit_id: UUID, tenant_id: UUID) -> bool:
        """Check whether actor has an active membership in the given care unit.

        tenant_id is required, not optional: this is a cross-tenant boundary
        check, and a default that silently skips it is a trap.

        Args:
            actor_id: The actor's UUID.
            care_unit_id: The care unit's UUID.
            tenant_id: The tenant the care unit must belong to.

        Returns:
            True if an active membership exists, False otherwise.
        """
        result = await self._session.execute(
            select(ActorTenantMembership.id)
            .where(
                ActorTenantMembership.actor_id == actor_id,
                ActorTenantMembership.care_unit_id == care_unit_id,
                ActorTenantMembership.tenant_id == tenant_id,
                ActorTenantMembership.status == "ACTIVE",
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_care_unit_ids(self, actor_id: UUID, tenant_id: UUID) -> list[UUID]:
        """Return all active care unit IDs for actor within a tenant.

        Rows with a NULL care_unit_id are tenant-wide memberships and are
        excluded — they name no specific care unit.

        Args:
            actor_id: The actor's UUID.
            tenant_id: The tenant's UUID.

        Returns:
            List of care_unit_id UUIDs the actor actively belongs to
            within the specified tenant.
        """
        result = await self._session.execute(
            select(ActorTenantMembership.care_unit_id).where(
                ActorTenantMembership.actor_id == actor_id,
                ActorTenantMembership.tenant_id == tenant_id,
                ActorTenantMembership.care_unit_id.is_not(None),
                ActorTenantMembership.status == "ACTIVE",
            )
        )
        return list(result.scalars().all())

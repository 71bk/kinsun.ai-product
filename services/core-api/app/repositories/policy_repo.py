"""Policy registry queries used by purpose-based consent."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import case, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import PolicyRegistry


class PolicyRepository:
    """Resolve an ACTIVE global or tenant-specific policy version."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    async def find_active_consent_policy(
        self,
        *,
        version: str,
        current_time: datetime,
    ) -> PolicyRegistry | None:
        tenant_priority = case(
            (PolicyRegistry.owner_tenant_id == self._tenant_id, 0),
            else_=1,
        )
        result = await self._session.execute(
            select(PolicyRegistry)
            .where(
                PolicyRegistry.policy_type == "CONSENT",
                PolicyRegistry.version == version,
                PolicyRegistry.status == "ACTIVE",
                or_(
                    PolicyRegistry.owner_tenant_id == self._tenant_id,
                    PolicyRegistry.owner_tenant_id.is_(None),
                ),
                or_(
                    PolicyRegistry.effective_from.is_(None),
                    PolicyRegistry.effective_from <= current_time,
                ),
                or_(
                    PolicyRegistry.effective_to.is_(None),
                    current_time < PolicyRegistry.effective_to,
                ),
            )
            .order_by(tenant_priority, PolicyRegistry.id)
            .limit(1)
        )
        return result.scalar_one_or_none()

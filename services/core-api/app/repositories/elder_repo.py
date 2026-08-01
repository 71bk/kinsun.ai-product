"""Elder repository — tenant-scoped data access for Elder entities.

Provides query methods for retrieving and checking existence of Elder
records, always scoped by tenant_id via BaseRepository.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from app.models.elder import Elder
from app.repositories.base import BaseRepository


class ElderRepository(BaseRepository):
    """Repository for Elder entities, scoped by tenant_id.

    All queries include an explicit WHERE tenant_id = :tenant_id
    predicate inherited from BaseRepository.
    """

    async def get_by_id(self, elder_id: UUID) -> Elder | None:
        """Fetch an Elder by ID, scoped to this repository's tenant.

        Args:
            elder_id: The UUID of the elder to retrieve.

        Returns:
            The Elder instance if found within the tenant scope, or None.
        """
        return await super().get_by_id(Elder, elder_id)

    async def exists(self, elder_id: UUID) -> bool:
        """Check whether an Elder exists within this repository's tenant.

        Uses an efficient SELECT count query rather than loading the
        full entity.

        Args:
            elder_id: The UUID of the elder to check.

        Returns:
            True if the elder exists within the tenant scope, False otherwise.
        """
        result = await self._session.execute(
            select(func.count()).select_from(
                select(Elder.id)
                .where(
                    Elder.id == elder_id,
                    Elder.tenant_id == self._tenant_id,
                )
                .subquery()
            )
        )
        return result.scalar_one() > 0

"""Base repository enforcing tenant-scoped queries.

Provides a base class for all domain repositories. Every query executed
through this layer includes an explicit WHERE tenant_id = :tenant_id
predicate, making cross-tenant data access impossible at the data layer.

Tenant_id is passed EXPLICITLY in the constructor — not pulled from
contextvars. This ensures background jobs, message consumers, and tests
can establish their own trusted context without relying on request-scoped
contextvars.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TenantScopeError


class BaseRepository:
    """Base repository enforcing tenant-scoped queries.

    Tenant_id is passed EXPLICITLY — not pulled from contextvars.
    This ensures:
    - Background jobs and message consumers can establish their own
      trusted context without relying on request-scoped contextvars.
    - SQL WHERE clauses always contain an explicit tenant predicate.
    - The calling service layer is responsible for passing the correct
      tenant_id from the authenticated ActorContext.
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        """Initialize repository with session and tenant scope.

        Args:
            session: The async database session for this unit of work.
            tenant_id: The trusted tenant identifier from ActorContext.
                       All queries will be scoped to this tenant.

        Raises:
            TenantScopeError: If tenant_id is None or not a valid UUID.
        """
        if tenant_id is None:
            raise TenantScopeError("tenant_id is required and cannot be None")
        if not isinstance(tenant_id, UUID):
            raise TenantScopeError(
                f"tenant_id must be a UUID instance, got {type(tenant_id).__name__}"
            )
        self._session = session
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> UUID:
        """The tenant_id this repository is scoped to."""
        return self._tenant_id

    async def get_by_id(self, model_class, entity_id: UUID):
        """Fetch a single entity by ID, scoped to this repository's tenant.

        The SQL always includes: WHERE id = $1 AND tenant_id = $2

        Args:
            model_class: The SQLAlchemy model class to query.
            entity_id: The UUID of the entity to retrieve.

        Returns:
            The entity instance if found within the tenant scope, or None.
        """
        result = await self._session.execute(
            select(model_class).where(
                model_class.id == entity_id,
                model_class.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self, model_class, *, limit: int = 100, offset: int = 0):
        """List entities scoped to this repository's tenant.

        The SQL always includes: WHERE tenant_id = $1

        Args:
            model_class: The SQLAlchemy model class to query.
            limit: Maximum number of results to return (default 100).
            offset: Number of results to skip (default 0).

        Returns:
            A list of entity instances belonging to the tenant.
        """
        result = await self._session.execute(
            select(model_class)
            .where(model_class.tenant_id == self._tenant_id)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

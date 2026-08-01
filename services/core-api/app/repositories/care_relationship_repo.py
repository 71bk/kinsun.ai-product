"""CareRelationship repository — tenant-scoped data access.

Provides query methods for validating authorization via CareRelationship
records and listing authorized elders. All queries are scoped by tenant_id
via BaseRepository, and use time boundary filtering for temporal validity.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select

from app.models.care_relationship import CareRelationship
from app.models.care_unit import CareUnit
from app.models.elder import Elder
from app.repositories.base import BaseRepository
from app.repositories.types import AuthorizedElderRow


class CareRelationshipRepository(BaseRepository):
    """Repository for CareRelationship entities, scoped by tenant_id.

    All queries include an explicit WHERE tenant_id = :tenant_id
    predicate inherited from BaseRepository. Time boundary filtering
    uses strict less-than for effective_to (half-open interval).
    """

    async def find_valid_for_actor(
        self,
        actor_id: UUID,
        elder_id: UUID,
        relationship_type: str,
        current_time: datetime,
    ) -> CareRelationship | None:
        """Find a valid CareRelationship matching all authorization criteria.

        A relationship is valid when ALL conditions are true:
        - cr.actor_id == actor_id
        - cr.elder_id == elder_id
        - cr.tenant_id == self._tenant_id
        - cr.relationship_type == relationship_type
        - cr.status == 'ACTIVE'
        - cr.effective_from <= current_time
        - cr.effective_to IS NULL OR current_time < cr.effective_to (strict <)

        Args:
            actor_id: The actor requesting access.
            elder_id: The target elder.
            relationship_type: Expected relationship type (e.g. DAYCARE_ASSIGNMENT).
            current_time: The current UTC time for temporal validation.

        Returns:
            The first matching CareRelationship, or None if no valid
            relationship exists.
        """
        stmt = (
            select(CareRelationship)
            .where(
                CareRelationship.actor_id == actor_id,
                CareRelationship.elder_id == elder_id,
                CareRelationship.tenant_id == self._tenant_id,
                CareRelationship.relationship_type == relationship_type,
                CareRelationship.status == "ACTIVE",
                CareRelationship.effective_from <= current_time,
                or_(
                    CareRelationship.effective_to.is_(None),
                    current_time < CareRelationship.effective_to,
                ),
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_authorized_elders_by_actor(
        self,
        actor_id: UUID,
        relationship_types: list[str],
        current_time: datetime,
        *,
        care_unit_ids: list[UUID] | None = None,
    ) -> list[AuthorizedElderRow]:
        """Find all elders the actor is authorized to access via relationships.

        Performs a JOIN with elders and an optional LEFT JOIN with care_units
        to return display information in a single query (avoids N+1).

        Uses DISTINCT ON (Elder.id) to deduplicate when an actor has
        multiple relationships to the same elder.

        If care_unit_ids is provided, restricts results to relationships
        associated with those care units (DAYCARE mode filtering).

        Args:
            actor_id: The actor requesting the listing.
            relationship_types: Allowed relationship types to match.
            current_time: The current UTC time for temporal validation.
            care_unit_ids: Optional list of care unit IDs to filter by
                          (used in DAYCARE mode).

        Returns:
            A list of AuthorizedElderRow tuples with elder_id,
            display_name, and care_unit_name.
        """
        deduplicated = (
            select(
                Elder.id.label("elder_id"),
                Elder.display_name.label("display_name"),
                CareUnit.name.label("care_unit_name"),
            )
            .distinct(Elder.id)
            .join(
                CareRelationship,
                (CareRelationship.elder_id == Elder.id)
                & (CareRelationship.tenant_id == Elder.tenant_id),
            )
            .outerjoin(
                CareUnit,
                CareUnit.id == CareRelationship.care_unit_id,
            )
            .where(
                CareRelationship.actor_id == actor_id,
                CareRelationship.tenant_id == self._tenant_id,
                CareRelationship.relationship_type.in_(relationship_types),
                CareRelationship.status == "ACTIVE",
                CareRelationship.effective_from <= current_time,
                or_(
                    CareRelationship.effective_to.is_(None),
                    current_time < CareRelationship.effective_to,
                ),
            )
            # PostgreSQL requires DISTINCT ON expressions to lead ORDER BY.
            # Care-unit name makes the selected row deterministic when more
            # than one valid relationship grants access to the same elder.
            .order_by(Elder.id, CareUnit.name)
        )

        if care_unit_ids is not None:
            deduplicated = deduplicated.where(CareRelationship.care_unit_id.in_(care_unit_ids))

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

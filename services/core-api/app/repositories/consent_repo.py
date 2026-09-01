"""Tenant-safe consent queries."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consent import ConsentGrant
from app.models.elder import Elder


class ConsentRepository:
    """Scope consent rows through the owning Elder's tenant."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id

    def _tenant_clause(self):
        return ConsentGrant.elder_id.in_(select(Elder.id).where(Elder.tenant_id == self._tenant_id))

    async def list_for_elder(self, elder_id: UUID) -> list[ConsentGrant]:
        result = await self._session.execute(
            select(ConsentGrant)
            .where(
                ConsentGrant.elder_id == elder_id,
                self._tenant_clause(),
            )
            .order_by(ConsentGrant.purpose_code, ConsentGrant.version.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, elder_id: UUID, consent_id: UUID) -> ConsentGrant | None:
        result = await self._session.execute(
            select(ConsentGrant).where(
                ConsentGrant.id == consent_id,
                ConsentGrant.elder_id == elder_id,
                self._tenant_clause(),
            )
        )
        return result.scalar_one_or_none()

    async def get_active(
        self,
        *,
        elder_id: UUID,
        purpose_code: str,
        current_time: datetime,
    ) -> ConsentGrant | None:
        result = await self._session.execute(
            select(ConsentGrant)
            .where(
                ConsentGrant.elder_id == elder_id,
                ConsentGrant.purpose_code == purpose_code,
                ConsentGrant.status == "GRANTED",
                ConsentGrant.effective_at <= current_time,
                or_(
                    ConsentGrant.expires_at.is_(None),
                    current_time < ConsentGrant.expires_at,
                ),
                self._tenant_clause(),
            )
            .order_by(ConsentGrant.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_for_purpose(
        self,
        *,
        elder_id: UUID,
        purpose_code: str,
    ) -> ConsentGrant | None:
        result = await self._session.execute(
            select(ConsentGrant)
            .where(
                ConsentGrant.elder_id == elder_id,
                ConsentGrant.purpose_code == purpose_code,
                self._tenant_clause(),
            )
            .order_by(ConsentGrant.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def next_version(self, elder_id: UUID, purpose_code: str) -> int:
        result = await self._session.execute(
            select(func.coalesce(func.max(ConsentGrant.version), 0)).where(
                ConsentGrant.elder_id == elder_id,
                ConsentGrant.purpose_code == purpose_code,
                self._tenant_clause(),
            )
        )
        return int(result.scalar_one()) + 1

    def add(self, consent: ConsentGrant) -> None:
        self._session.add(consent)

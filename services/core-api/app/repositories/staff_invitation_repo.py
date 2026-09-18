"""Tenant-scoped workforce invitation persistence."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cursor import decode_cursor
from app.models.actor import Actor
from app.models.care_unit import CareUnit
from app.models.staff_invitation import StaffInvitation


class StaffInvitationRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def actor(self, actor_id: UUID) -> Actor | None:
        return await self.session.scalar(select(Actor).where(Actor.id == actor_id))

    async def unit(self, unit_id: UUID) -> CareUnit | None:
        return await self.session.scalar(
            select(CareUnit).where(
                CareUnit.id == unit_id,
                CareUnit.tenant_id == self.tenant_id,
                CareUnit.status == "ACTIVE",
            )
        )

    async def get(self, invitation_id: UUID) -> StaffInvitation | None:
        return await self.session.scalar(
            select(StaffInvitation)
            .where(
                StaffInvitation.id == invitation_id,
                StaffInvitation.tenant_id == self.tenant_id,
            )
            .with_for_update()
        )

    async def list(self, cursor: str | None, limit: int) -> list[StaffInvitation]:
        query = select(StaffInvitation).where(StaffInvitation.tenant_id == self.tenant_id)
        if cursor:
            created, resource = decode_cursor(cursor)
            query = query.where(
                tuple_(StaffInvitation.created_at, StaffInvitation.id) < tuple_(created, resource)
            )
        return list(
            (
                await self.session.scalars(
                    query.order_by(
                        StaffInvitation.created_at.desc(), StaffInvitation.id.desc()
                    ).limit(limit + 1)
                )
            ).all()
        )

    async def units(self, cursor: str | None, limit: int) -> list[CareUnit]:
        query = select(CareUnit).where(
            CareUnit.tenant_id == self.tenant_id,
            CareUnit.status == "ACTIVE",
            CareUnit.unit_type.in_(("DAYCARE_CENTER", "COMMUNITY_SITE", "HOME_CARE_AGENCY")),
        )
        if cursor:
            created, resource = decode_cursor(cursor)
            query = query.where(
                tuple_(CareUnit.created_at, CareUnit.id) < tuple_(created, resource)
            )
        return list(
            (
                await self.session.scalars(
                    query.order_by(CareUnit.created_at.desc(), CareUnit.id.desc()).limit(limit + 1)
                )
            ).all()
        )

    @staticmethod
    async def resolve_credential(session: AsyncSession, digest: str) -> StaffInvitation | None:
        # The unguessable credential is the only pre-authentication lookup authority.
        return await session.scalar(
            select(StaffInvitation).where(StaffInvitation.token_digest == digest).with_for_update()
        )

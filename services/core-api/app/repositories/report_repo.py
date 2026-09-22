"""Tenant-safe family relationship and report persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select

from app.models.actor import Actor
from app.models.elder import Elder
from app.models.report import FamilyRelationship, FamilyReport, ReportVersion
from app.repositories.base import BaseRepository


class ReportRepository(BaseRepository):
    def add_report(self, report: FamilyReport) -> None:
        self._session.add(report)

    def add_version(self, version: ReportVersion) -> None:
        self._session.add(version)

    async def get(self, report_id: UUID) -> FamilyReport | None:
        result = await self._session.execute(
            select(FamilyReport).where(
                FamilyReport.id == report_id,
                FamilyReport.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_elder(self, elder_id: UUID, report_id: UUID) -> FamilyReport | None:
        result = await self._session.execute(
            select(FamilyReport).where(
                FamilyReport.id == report_id,
                FamilyReport.elder_id == elder_id,
                FamilyReport.tenant_id == self._tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_current_version(self, report: FamilyReport) -> ReportVersion:
        result = await self._session.execute(
            select(ReportVersion).where(
                ReportVersion.report_id == report.id,
                ReportVersion.version == report.current_version,
            )
        )
        return result.scalar_one()

    async def get_family_relationship(
        self,
        *,
        relationship_id: UUID,
        elder_id: UUID,
        actor_id: UUID | None,
        current_time: datetime,
    ) -> FamilyRelationship | None:
        stmt = (
            select(FamilyRelationship)
            .join(Elder, FamilyRelationship.elder_id == Elder.id)
            .where(
                FamilyRelationship.id == relationship_id,
                FamilyRelationship.elder_id == elder_id,
                Elder.tenant_id == self._tenant_id,
                FamilyRelationship.status == "ACTIVE",
                FamilyRelationship.effective_from <= current_time,
                or_(
                    FamilyRelationship.effective_to.is_(None),
                    current_time < FamilyRelationship.effective_to,
                ),
            )
        )
        if actor_id is not None:
            stmt = stmt.where(FamilyRelationship.family_actor_id == actor_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_published(
        self,
        *,
        elder_id: UUID,
        report_type: str | None,
    ) -> list[FamilyReport]:
        stmt = select(FamilyReport).where(
            FamilyReport.elder_id == elder_id,
            FamilyReport.tenant_id == self._tenant_id,
            FamilyReport.status == "PUBLISHED",
        )
        if report_type:
            stmt = stmt.where(FamilyReport.report_type == report_type)
        result = await self._session.execute(
            stmt.order_by(FamilyReport.period_end.desc(), FamilyReport.id.desc()).limit(100)
        )
        return list(result.scalars().all())

    async def get_for_update(self, elder_id: UUID, report_id: UUID) -> FamilyReport | None:
        result = await self._session.execute(
            select(FamilyReport)
            .where(
                FamilyReport.id == report_id,
                FamilyReport.elder_id == elder_id,
                FamilyReport.tenant_id == self._tenant_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_for_staff(self, elder_id: UUID) -> list[FamilyReport]:
        result = await self._session.execute(
            select(FamilyReport)
            .where(
                FamilyReport.elder_id == elder_id,
                FamilyReport.tenant_id == self._tenant_id,
            )
            .order_by(FamilyReport.created_at.desc(), FamilyReport.id.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    async def list_daily_recipients(self, elder_id: UUID, consent_id: UUID, now: datetime):
        result = await self._session.execute(
            select(FamilyRelationship, Actor.display_name)
            .join(Elder, FamilyRelationship.elder_id == Elder.id)
            .join(Actor, FamilyRelationship.family_actor_id == Actor.id)
            .where(
                Elder.tenant_id == self._tenant_id,
                FamilyRelationship.elder_id == elder_id,
                FamilyRelationship.consent_id == consent_id,
                FamilyRelationship.status == "ACTIVE",
                Actor.status == "ACTIVE",
                FamilyRelationship.effective_from <= now,
                or_(
                    FamilyRelationship.effective_to.is_(None), now < FamilyRelationship.effective_to
                ),
                or_(
                    FamilyRelationship.share_scope.any("REPORT_DAILY"),
                    FamilyRelationship.share_scope.any("REPORT_ALL"),
                ),
            )
            .order_by(Actor.display_name, FamilyRelationship.id)
            .limit(33)
        )
        return result.all()

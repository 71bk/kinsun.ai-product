"""Tenant-safe family relationship and report persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select

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

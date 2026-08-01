"""Tenant-scoped daily-summary persistence."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select

from app.models.care_event import ReviewDecision
from app.models.summary import DailySummary, SummaryVersion
from app.repositories.base import BaseRepository


class SummaryRepository(BaseRepository):
    def add_summary(self, summary: DailySummary) -> None:
        self._session.add(summary)

    def add_version(self, version: SummaryVersion) -> None:
        self._session.add(version)

    def add_review(self, review: ReviewDecision) -> None:
        self._session.add(review)

    async def get(
        self,
        elder_id: UUID,
        summary_id: UUID,
        statuses: list[str] | None = None,
    ) -> DailySummary | None:
        stmt = select(DailySummary).where(
            DailySummary.id == summary_id,
            DailySummary.elder_id == elder_id,
            DailySummary.tenant_id == self._tenant_id,
        )
        if statuses is not None:
            stmt = stmt.where(DailySummary.status.in_(statuses))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_key(
        self,
        *,
        elder_id: UUID,
        summary_date: date,
        summary_type: str,
    ) -> DailySummary | None:
        result = await self._session.execute(
            select(DailySummary).where(
                DailySummary.elder_id == elder_id,
                DailySummary.tenant_id == self._tenant_id,
                DailySummary.summary_date == summary_date,
                DailySummary.summary_type == summary_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_current_version(self, summary: DailySummary) -> SummaryVersion:
        result = await self._session.execute(
            select(SummaryVersion).where(
                SummaryVersion.summary_id == summary.id,
                SummaryVersion.version == summary.current_version,
            )
        )
        return result.scalar_one()

    async def get_latest_review(self, summary_id: UUID) -> ReviewDecision | None:
        result = await self._session.execute(
            select(ReviewDecision)
            .where(
                ReviewDecision.target_type == "DAILY_SUMMARY",
                ReviewDecision.target_id == summary_id,
            )
            .order_by(ReviewDecision.reviewed_at.desc(), ReviewDecision.review_id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_date(
        self,
        *,
        elder_id: UUID,
        summary_date: date | None,
        statuses: list[str] | None = None,
    ) -> list[DailySummary]:
        stmt = select(DailySummary).where(
            DailySummary.elder_id == elder_id,
            DailySummary.tenant_id == self._tenant_id,
        )
        if statuses is None:
            stmt = stmt.where(DailySummary.status != "WITHDRAWN")
        else:
            stmt = stmt.where(DailySummary.status.in_(statuses))
        if summary_date:
            stmt = stmt.where(DailySummary.summary_date == summary_date)
        result = await self._session.execute(
            stmt.order_by(DailySummary.summary_date.desc(), DailySummary.id.desc()).limit(100)
        )
        return list(result.scalars().all())

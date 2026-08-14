"""Tenant-scoped care-event persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from app.models.care_event import CareEvent, CareEventVersion, ReviewDecision
from app.models.graph_projection import GraphProjectionRecord
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class VerifiedCareEventContextRecord:
    event_id: UUID
    version: int
    event_type: str
    structured_payload: dict
    consent_version: int


class CareEventRepository(BaseRepository):
    def add_event(self, event: CareEvent) -> None:
        self._session.add(event)

    def add_version(self, version: CareEventVersion) -> None:
        self._session.add(version)

    def add_review(self, review: ReviewDecision) -> None:
        self._session.add(review)

    async def get(
        self,
        elder_id: UUID,
        event_id: UUID,
        statuses: list[str] | None = None,
    ) -> CareEvent | None:
        stmt = select(CareEvent).where(
            CareEvent.id == event_id,
            CareEvent.elder_id == elder_id,
            CareEvent.tenant_id == self._tenant_id,
        )
        if statuses is not None:
            stmt = stmt.where(CareEvent.status.in_(statuses))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_current_version(self, event: CareEvent) -> CareEventVersion:
        result = await self._session.execute(
            select(CareEventVersion).where(
                CareEventVersion.event_id == event.id,
                CareEventVersion.version == event.current_version,
            )
        )
        return result.scalar_one()

    async def get_latest_review(self, event_id: UUID) -> ReviewDecision | None:
        result = await self._session.execute(
            select(ReviewDecision)
            .join(CareEvent, ReviewDecision.event_id == CareEvent.id)
            .where(
                ReviewDecision.event_id == event_id,
                CareEvent.tenant_id == self._tenant_id,
            )
            .order_by(ReviewDecision.reviewed_at.desc(), ReviewDecision.review_id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_for_elder(
        self,
        *,
        elder_id: UUID,
        statuses: list[str] | None,
        event_type: str | None,
        event_time_from: datetime | None,
        event_time_to: datetime | None,
        limit: int,
        cursor: tuple[datetime, UUID] | None,
    ) -> list[CareEvent]:
        stmt = select(CareEvent).where(
            CareEvent.elder_id == elder_id,
            CareEvent.tenant_id == self._tenant_id,
        )
        if statuses:
            stmt = stmt.where(CareEvent.status.in_(statuses))
        if event_type is not None:
            stmt = stmt.where(CareEvent.event_type == event_type)
        effective_event_time = func.coalesce(CareEvent.event_time, CareEvent.created_at)
        if event_time_from is not None:
            stmt = stmt.where(effective_event_time >= event_time_from)
        if event_time_to is not None:
            stmt = stmt.where(effective_event_time <= event_time_to)
        if cursor:
            created_at, event_id = cursor
            stmt = stmt.where(
                or_(
                    CareEvent.created_at < created_at,
                    and_(
                        CareEvent.created_at == created_at,
                        CareEvent.id < event_id,
                    ),
                )
            )
        result = await self._session.execute(
            stmt.order_by(CareEvent.created_at.desc(), CareEvent.id.desc()).limit(limit + 1)
        )
        return list(result.scalars().all())

    async def list_projected_verified_context_for_elder(
        self,
        *,
        elder_id: UUID,
        max_consent_version: int,
        limit: int,
    ) -> list[VerifiedCareEventContextRecord]:
        result = await self._session.execute(
            select(
                CareEvent.id,
                CareEvent.current_version,
                CareEvent.event_type,
                CareEventVersion.structured_payload,
                CareEvent.consent_version,
            )
            .join(
                CareEventVersion,
                and_(
                    CareEventVersion.event_id == CareEvent.id,
                    CareEventVersion.version == CareEvent.current_version,
                ),
            )
            .join(
                GraphProjectionRecord,
                and_(
                    GraphProjectionRecord.source_type == "care_event",
                    GraphProjectionRecord.source_id == CareEvent.id,
                    GraphProjectionRecord.source_version == CareEvent.current_version,
                    GraphProjectionRecord.projection_status == "SYNCED",
                    GraphProjectionRecord.graph_key.is_not(None),
                ),
            )
            .where(
                CareEvent.elder_id == elder_id,
                CareEvent.tenant_id == self._tenant_id,
                CareEvent.status.in_(["VERIFIED", "CORRECTED"]),
                CareEvent.consent_version > 0,
                CareEvent.consent_version <= max_consent_version,
            )
            .order_by(CareEvent.updated_at.desc(), CareEvent.id.desc())
            .limit(limit)
        )
        return [
            VerifiedCareEventContextRecord(
                event_id=row[0],
                version=row[1],
                event_type=row[2],
                structured_payload=row[3],
                consent_version=row[4],
            )
            for row in result.all()
        ]

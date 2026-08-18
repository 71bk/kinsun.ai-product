"""Source-backed daily-summary draft and rebuild service."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ValidationError
from app.domain.consent import ConsentPurpose
from app.domain.state_machine import require_summary_transition
from app.events.outbox_writer import write_outbox_entry
from app.models.care_event import CareEvent, CareEventVersion, ReviewDecision
from app.models.summary import DailySummary, SummaryVersion
from app.repositories.summary_repo import SummaryRepository
from app.schemas.summary import CreateSummaryDraftRequest, ReviewSummaryRequest, SummaryItem
from app.services.care_event_rendering import (
    SUMMARY_CATEGORY_BY_EVENT_TYPE,
    render_reviewed_event,
)
from app.services.consent_service import ConsentService


class SummaryService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._summaries = SummaryRepository(session, tenant_id)

    async def get(
        self,
        elder_id: UUID,
        summary_id: UUID,
        statuses: list[str] | None = None,
    ) -> DailySummary | None:
        return await self._summaries.get(elder_id, summary_id, statuses)

    async def get_version(self, summary: DailySummary) -> SummaryVersion:
        return await self._summaries.get_current_version(summary)

    async def get_latest_review(self, summary_id: UUID) -> ReviewDecision | None:
        return await self._summaries.get_latest_review(summary_id)

    async def list_for_date(self, **kwargs) -> list[DailySummary]:
        return await self._summaries.list_for_date(**kwargs)

    async def generate_from_verified_events(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        summary_date: date,
        trace_id: str,
        idempotency_key: str,
    ) -> DailySummary:
        """Create a non-inferential draft from current reviewed event versions."""

        taipei = ZoneInfo("Asia/Taipei")
        starts_at = datetime.combine(summary_date, time.min, taipei).astimezone(UTC)
        ends_at = datetime.combine(summary_date, time.max, taipei).astimezone(UTC)
        effective_time = func.coalesce(CareEvent.event_time, CareEvent.created_at)
        rows = (
            await self._session.execute(
                select(CareEvent, CareEventVersion)
                .join(
                    CareEventVersion,
                    (CareEventVersion.event_id == CareEvent.id)
                    & (CareEventVersion.version == CareEvent.current_version),
                )
                .where(
                    CareEvent.elder_id == elder_id,
                    CareEvent.tenant_id == self._tenant_id,
                    CareEvent.status.in_(["VERIFIED", "CORRECTED"]),
                    effective_time >= starts_at,
                    effective_time <= ends_at,
                )
                .order_by(effective_time, CareEvent.id)
                .limit(32)
            )
        ).all()
        items = [
            SummaryItem(
                category=SUMMARY_CATEGORY_BY_EVENT_TYPE.get(
                    event.event_type,
                    "IMPORTANT_EVENT",
                ),
                text=render_reviewed_event(event.event_type, version.structured_payload),
                source_event_ids=[event.id],
                data_status="PRESENT",
            )
            for event, version in rows
        ]
        present_categories = {item.category for item in items}
        expected_categories = {
            "MEAL",
            "ACTIVITY",
            "SLEEP",
            "MEDICATION_STATEMENT",
            "SOCIAL",
        }
        request = CreateSummaryDraftRequest(
            summary_date=summary_date,
            items=items,
            missing_fields=sorted(expected_categories - present_categories),
            conflict_flags=[],
            model_version="deterministic-summary-v1",
            prompt_version=None,
        )
        return await self.create_draft(
            elder_id=elder_id,
            actor_id=actor_id,
            request=request,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
        )

    async def create_draft(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateSummaryDraftRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> DailySummary:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
        )
        source_ids = {event_id for item in request.items for event_id in item.source_event_ids}
        if source_ids:
            count = await self._session.scalar(
                select(func.count())
                .select_from(CareEvent)
                .where(
                    CareEvent.id.in_(source_ids),
                    CareEvent.elder_id == elder_id,
                    CareEvent.tenant_id == self._tenant_id,
                    CareEvent.status.in_(["VERIFIED", "CORRECTED"]),
                )
            )
            if count != len(source_ids):
                raise ValidationError(
                    details=[
                        {
                            "field": "items.source_event_ids",
                            "reason": "summaries can use only verified events for this elder",
                        }
                    ]
                )

        summary = await self._summaries.find_by_key(
            elder_id=elder_id,
            summary_date=request.summary_date,
            summary_type=request.summary_type,
        )
        now = datetime.now(UTC)
        if summary is None:
            summary = DailySummary(
                elder_id=elder_id,
                tenant_id=self._tenant_id,
                summary_date=request.summary_date,
                summary_type=request.summary_type,
                status="NEEDS_REVIEW",
                current_version=1,
                generated_at=now,
            )
            self._summaries.add_summary(summary)
            await self._session.flush()
        else:
            if summary.status != "STALE":
                require_summary_transition(summary.status, "STALE")
            require_summary_transition("STALE", "NEEDS_REVIEW")
            summary.current_version += 1
            summary.status = "NEEDS_REVIEW"
            summary.generated_at = now

        self._summaries.add_version(
            SummaryVersion(
                summary_id=summary.id,
                version=summary.current_version,
                content={
                    "items": [item.model_dump(mode="json") for item in request.items],
                    "missing_fields": request.missing_fields,
                    "conflict_flags": request.conflict_flags,
                },
                source_event_ids=list(source_ids),
                model_version=request.model_version,
                prompt_version=request.prompt_version,
                created_by_actor_id=actor_id,
            )
        )
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="daily.summary.generated.v1",
            aggregate_type="daily_summary",
            aggregate_id=summary.id,
            aggregate_version=summary.current_version,
            tenant_id=self._tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION.value,
            consent_version=consent.version,
            payload={
                "summary_id": str(summary.id),
                "summary_date": str(summary.summary_date),
                "status": summary.status,
                "version": summary.current_version,
                "source_event_ids": [str(item) for item in source_ids],
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return summary

    async def review(
        self,
        *,
        summary: DailySummary,
        actor_id: UUID,
        request: ReviewSummaryRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> ReviewDecision:
        if summary.current_version != request.expected_version:
            raise ConflictError("Daily summary version conflict")
        await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=summary.elder_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
        )
        target_status = "READY" if request.decision == "VERIFY" else "WITHDRAWN"
        require_summary_transition(summary.status, target_status)
        summary.status = target_status
        review = ReviewDecision(
            target_type="DAILY_SUMMARY",
            target_id=summary.id,
            reviewer_actor_id=actor_id,
            decision=request.decision,
            reason_code=request.reason_code,
            before_version=summary.current_version,
            after_version=summary.current_version,
        )
        self._summaries.add_review(review)
        await self._session.flush()
        event_status = "ready" if target_status == "READY" else "withdrawn"
        await write_outbox_entry(
            self._session,
            event_type=f"daily.summary.{event_status}.v1",
            aggregate_type="daily_summary",
            aggregate_id=summary.id,
            aggregate_version=summary.current_version,
            tenant_id=self._tenant_id,
            elder_id=summary.elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION.value,
            payload={
                "summary_id": str(summary.id),
                "status": summary.status,
                "version": summary.current_version,
                "review_id": str(review.review_id),
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return review

    async def request_rebuild(
        self,
        *,
        summary: DailySummary,
        actor_id: UUID,
        expected_version: int,
        reason_code: str,
        trace_id: str,
        idempotency_key: str,
    ) -> DailySummary:
        if summary.current_version != expected_version:
            raise ConflictError("Daily summary version conflict")
        require_summary_transition(summary.status, "STALE")
        summary.status = "STALE"
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="daily.summary.rebuild-requested.v1",
            aggregate_type="daily_summary",
            aggregate_id=summary.id,
            aggregate_version=summary.current_version,
            tenant_id=self._tenant_id,
            elder_id=summary.elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION.value,
            payload={
                "summary_id": str(summary.id),
                "status": "STALE",
                "reason_code": reason_code,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return summary

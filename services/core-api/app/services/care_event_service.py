"""Care-event candidate and human-review lifecycle."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.domain.state_machine import CARE_EVENT_REVIEW_STATES
from app.events.outbox_writer import write_outbox_entry
from app.models.care_event import CareEvent, CareEventVersion, ReviewDecision
from app.models.summary import DailySummary, SummaryVersion
from app.repositories.care_event_repo import CareEventRepository
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.care_event import (
    ConfidenceBand,
    CreateCareEventCandidateRequest,
    ReviewCareEventRequest,
)
from app.schemas.consent import ConsentPurpose
from app.services.consent_service import ConsentService

CONFIDENCE_VALUES = {
    ConfidenceBand.LOW: Decimal("0.3000"),
    ConfidenceBand.MEDIUM: Decimal("0.6000"),
    ConfidenceBand.HIGH: Decimal("0.9000"),
}


class CareEventService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = tenant_id
        self._events = CareEventRepository(session, tenant_id)

    async def get(
        self,
        elder_id: UUID,
        event_id: UUID,
        statuses: list[str] | None = None,
    ) -> CareEvent | None:
        return await self._events.get(elder_id, event_id, statuses)

    async def get_version(self, event: CareEvent) -> CareEventVersion:
        return await self._events.get_current_version(event)

    async def get_latest_review(self, event_id: UUID) -> ReviewDecision | None:
        return await self._events.get_latest_review(event_id)

    async def list_for_elder(self, **kwargs) -> list[CareEvent]:
        return await self._events.list_for_elder(**kwargs)

    async def create_candidate(
        self,
        *,
        elder_id: UUID,
        actor_id: UUID,
        request: CreateCareEventCandidateRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> CareEvent:
        consent = await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=elder_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
        )
        if request.source_type == "CONVERSATION_SESSION":
            conversation = await ConversationRepository(
                self._session,
                self._tenant_id,
            ).get_for_elder(request.source_id, elder_id)
            if conversation is None:
                raise NotFoundError("Source session not found")
            if conversation.state != "COMPLETED":
                raise ConflictError("Care-event extraction requires a completed session")

        event = CareEvent(
            elder_id=elder_id,
            tenant_id=self._tenant_id,
            source_session_id=request.source_id
            if request.source_type == "CONVERSATION_SESSION"
            else None,
            event_type=request.event_type.value,
            event_time=request.event_time,
            status="NEEDS_REVIEW",
            current_version=1,
            consent_version=consent.version,
        )
        self._events.add_event(event)
        await self._session.flush()
        self._events.add_version(
            CareEventVersion(
                event_id=event.id,
                version=1,
                structured_payload=request.structured_payload,
                evidence_text_ref=json.dumps(request.evidence_refs),
                confidence=CONFIDENCE_VALUES[request.confidence_band],
                created_by_actor_id=actor_id,
            )
        )
        await self._session.flush()
        await write_outbox_entry(
            self._session,
            event_type="care.event.candidate-created.v1",
            aggregate_type="care_event",
            aggregate_id=event.id,
            aggregate_version=1,
            tenant_id=self._tenant_id,
            elder_id=elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION.value,
            consent_version=consent.version,
            payload={
                "event_id": str(event.id),
                "event_type": event.event_type,
                "status": event.status,
                "source_session_id": str(event.source_session_id)
                if event.source_session_id
                else None,
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return event

    async def review(
        self,
        *,
        event: CareEvent,
        actor_id: UUID,
        request: ReviewCareEventRequest,
        trace_id: str,
        idempotency_key: str,
    ) -> tuple[ReviewDecision, list[str]]:
        if event.status not in {"CANDIDATE", "NEEDS_REVIEW"}:
            raise ConflictError("Only candidate events can be reviewed")
        if event.current_version != request.expected_version:
            raise ConflictError("Care event version conflict")
        await ConsentService(self._session, self._tenant_id).require_active(
            elder_id=event.elder_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION,
        )

        before_version = event.current_version
        if request.decision == "CORRECT":
            current = await self._events.get_current_version(event)
            event.current_version += 1
            self._events.add_version(
                CareEventVersion(
                    event_id=event.id,
                    version=event.current_version,
                    structured_payload=request.corrected_payload,
                    evidence_text_ref=current.evidence_text_ref,
                    confidence=current.confidence,
                    created_by_actor_id=actor_id,
                    supersedes_version_id=current.event_version_id,
                )
            )
        event.status = CARE_EVENT_REVIEW_STATES[request.decision]
        review = ReviewDecision(
            target_type="CARE_EVENT",
            target_id=event.id,
            event_id=event.id,
            reviewer_actor_id=actor_id,
            decision=request.decision,
            reason_code=request.reason_code,
            before_version=before_version,
            after_version=event.current_version,
        )
        self._events.add_review(review)

        rebuild_required: list[str] = []
        if request.decision in {"CORRECT", "REJECT", "EXCLUDE"}:
            affected = select(SummaryVersion.summary_id).where(
                SummaryVersion.source_event_ids.contains([event.id])
            )
            await self._session.execute(
                update(DailySummary)
                .where(
                    DailySummary.tenant_id == self._tenant_id,
                    DailySummary.id.in_(affected),
                )
                .values(status="STALE")
            )
            rebuild_required = ["DAILY_SUMMARY"]

        await self._session.flush()
        event_name = {
            "VERIFY": "verified",
            "CORRECT": "corrected",
            "REJECT": "rejected",
            "EXCLUDE": "rejected",
        }[request.decision]
        await write_outbox_entry(
            self._session,
            event_type=f"care.event.{event_name}.v1",
            aggregate_type="care_event",
            aggregate_id=event.id,
            aggregate_version=event.current_version,
            tenant_id=self._tenant_id,
            elder_id=event.elder_id,
            actor_id=actor_id,
            purpose=ConsentPurpose.CARE_EVENT_EXTRACTION.value,
            consent_version=event.consent_version,
            payload={
                "event_id": str(event.id),
                "status": event.status,
                "version": event.current_version,
                "review_id": str(review.review_id),
            },
            trace_id=trace_id,
            correlation_id=trace_id,
            idempotency_key=idempotency_key,
        )
        return review, rebuild_required

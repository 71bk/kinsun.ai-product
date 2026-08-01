"""Replay-safe transactional-outbox relay."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.failures import EventDeliveryFailure, EventPublishError
from app.events.publisher import EventPublisher
from app.models.care_event import CareEvent
from app.models.consent import ConsentGrant
from app.models.memory import Memory
from app.models.outbox import OutboxEvent
from app.models.report import FamilyReport
from app.repositories.deletion_repo import DeletionRepository

REVOCATION_SAFE_EVENTS = {
    "consent.revoked.v1",
    "deletion.requested.v1",
    "deletion.completed.v1",
    "deletion.partial-failed.v1",
    "memory.deleted.v1",
    "family.report.withdrawn.v1",
}


class OutboxRelay:
    """Publish a bounded batch while rechecking consent and tombstones."""

    def __init__(
        self,
        session: AsyncSession,
        publisher: EventPublisher,
    ) -> None:
        self._session = session
        self._publisher = publisher

    async def relay_once(
        self,
        *,
        batch_size: int = 50,
        max_attempts: int = 10,
    ) -> tuple[int, int, int]:
        if batch_size < 1 or batch_size > 500:
            raise ValueError("batch_size must be between 1 and 500")
        if max_attempts < 1 or max_attempts > 100:
            raise ValueError("max_attempts must be between 1 and 100")
        events = list(
            (
                await self._session.execute(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.delivery_status.in_(["PENDING", "FAILED"]),
                    )
                    .order_by(OutboxEvent.created_at, OutboxEvent.outbox_event_id)
                    .limit(batch_size)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        published = 0
        suppressed = 0
        failed = 0
        for event in events:
            if event.delivery_status == "FAILED" and event.attempt_count >= max_attempts:
                event.delivery_status = "DEAD_LETTER"
                event.last_error = "PUBLISHER_ATTEMPT_LIMIT_REACHED"
                failed += 1
                continue
            event.delivery_status = "PUBLISHING"
            event.attempt_count += 1
            await self._session.flush()
            suppression_reason = await self._suppression_reason(event)
            if suppression_reason is not None:
                event.delivery_status = "SUPPRESSED"
                event.last_error = suppression_reason
                suppressed += 1
                continue
            try:
                await self._publisher.publish(
                    event_type=event.event_type,
                    aggregate_id=event.aggregate_id,
                    tenant_id=event.tenant_id,
                    payload=self._envelope(event),
                )
            except Exception as exc:
                if isinstance(exc, EventPublishError):
                    reason_code = exc.reason_code
                    retryable = exc.retryable
                else:
                    reason_code = "PUBLISHER_UNEXPECTED_ERROR"
                    retryable = True
                failure = EventDeliveryFailure.for_attempt(
                    event_id=event.event_id,
                    stage="PUBLISHER",
                    reason_code=reason_code,
                    retryable=retryable,
                    attempt_count=event.attempt_count,
                    max_attempts=max_attempts,
                )
                event.delivery_status = (
                    "FAILED" if failure.disposition == "RETRY" else "DEAD_LETTER"
                )
                event.last_error = failure.reason_code
                failed += 1
            else:
                event.delivery_status = "PUBLISHED"
                event.published_at = datetime.now(UTC)
                event.last_error = None
                published += 1
        await self._session.flush()
        return published, suppressed, failed

    async def _suppression_reason(self, event: OutboxEvent) -> str | None:
        if event.tenant_id is None:
            return "SUPPRESSED_MISSING_TENANT"
        if event.event_type in REVOCATION_SAFE_EVENTS:
            return None
        if event.elder_id is not None and event.purpose is not None:
            now = datetime.now(UTC)
            active_consent = await self._session.scalar(
                select(ConsentGrant.id).where(
                    ConsentGrant.elder_id == event.elder_id,
                    ConsentGrant.purpose_code == event.purpose,
                    ConsentGrant.status == "GRANTED",
                    ConsentGrant.version == event.consent_version,
                    ConsentGrant.effective_at <= now,
                    or_(
                        ConsentGrant.expires_at.is_(None),
                        now < ConsentGrant.expires_at,
                    ),
                    or_(
                        ConsentGrant.revoked_at.is_(None),
                        now < ConsentGrant.revoked_at,
                    ),
                )
            )
            if active_consent is None:
                return "SUPPRESSED_CONSENT_INACTIVE"

        if await DeletionRepository(
            self._session,
            event.tenant_id,
        ).has_tombstone(
            resource_type=event.aggregate_type,
            resource_id=event.aggregate_id,
        ):
            return "SUPPRESSED_DELETION_TOMBSTONE"

        if event.aggregate_type == "memory":
            status = await self._session.scalar(
                select(Memory.status).where(
                    Memory.id == event.aggregate_id,
                    Memory.tenant_id == event.tenant_id,
                )
            )
            if status == "DELETED":
                return "SUPPRESSED_TOMBSTONED_MEMORY"
        elif event.aggregate_type == "care_event":
            status = await self._session.scalar(
                select(CareEvent.status).where(
                    CareEvent.id == event.aggregate_id,
                    CareEvent.tenant_id == event.tenant_id,
                )
            )
            if status == "DELETED":
                return "SUPPRESSED_TOMBSTONED_EVENT"
        elif event.aggregate_type == "family_report":
            status = await self._session.scalar(
                select(FamilyReport.status).where(
                    FamilyReport.id == event.aggregate_id,
                    FamilyReport.tenant_id == event.tenant_id,
                )
            )
            if status == "WITHDRAWN":
                return "SUPPRESSED_WITHDRAWN_REPORT"
        return None

    @staticmethod
    def _envelope(event: OutboxEvent) -> dict:
        return {
            "event_id": str(event.event_id),
            "event_type": event.event_type,
            "event_version": 1,
            "occurred_at": event.occurred_at.isoformat(),
            "tenant_id": str(event.tenant_id),
            "elder_id": str(event.elder_id) if event.elder_id else None,
            "actor_id": str(event.actor_id) if event.actor_id else None,
            "purpose": event.purpose,
            "consent_version": event.consent_version,
            "trace_id": event.trace_id,
            "correlation_id": event.correlation_id,
            "causation_id": event.causation_id,
            "idempotency_key": event.idempotency_key,
            "classification": event.classification,
            "aggregate": {
                "type": event.aggregate_type,
                "id": str(event.aggregate_id),
                "version": event.aggregate_version,
            },
            "payload": event.payload,
        }

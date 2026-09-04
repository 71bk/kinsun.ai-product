"""Leased, replay-safe transactional-outbox relay."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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


class OutboxLeaseLostError(RuntimeError):
    """Raised when a worker can no longer settle the lease it claimed."""


@dataclass(frozen=True)
class ClaimedOutboxEvent:
    """Immutable event snapshot used after the claim transaction commits."""

    outbox_event_id: UUID
    event_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    tenant_id: UUID | None
    elder_id: UUID | None
    actor_id: UUID | None
    purpose: str | None
    consent_version: int | None
    trace_id: str
    correlation_id: str | None
    causation_id: str | None
    idempotency_key: str | None
    classification: str
    payload: dict[str, Any]
    occurred_at: datetime
    attempt_count: int
    lease_token: UUID


@dataclass(frozen=True)
class RelayBatchResult:
    """Safe counters for one bounded relay pass."""

    claimed: int = 0
    published: int = 0
    suppressed: int = 0
    retry_scheduled: int = 0
    dead_lettered: int = 0
    leases_recovered: int = 0

    @property
    def made_progress(self) -> bool:
        return self.claimed > 0 or self.dead_lettered > 0 or self.leases_recovered > 0


class OutboxRelay:
    """Claim short leases and publish committed events outside DB transactions.

    A publish may succeed immediately before this process loses connectivity or
    crashes. The lease then expires and the same event is published again. This
    is intentional at-least-once delivery; consumers must deduplicate event_id.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        publisher: EventPublisher,
        *,
        worker_id: str,
        lease_duration: timedelta = timedelta(seconds=30),
        retry_base: timedelta = timedelta(seconds=2),
        retry_max: timedelta = timedelta(minutes=5),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}", worker_id):
            raise ValueError("worker_id must be a stable 1-64 character identifier")
        if lease_duration <= timedelta(0) or lease_duration > timedelta(hours=1):
            raise ValueError("lease_duration must be between 0 and 1 hour")
        if retry_base <= timedelta(0) or retry_max < retry_base:
            raise ValueError("retry delays must be positive and retry_max >= retry_base")
        self._session_factory = session_factory
        self._publisher = publisher
        self._worker_id = worker_id
        self._lease_duration = lease_duration
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._clock = clock or (lambda: datetime.now(UTC))

    async def relay_once(
        self,
        *,
        batch_size: int = 50,
        max_attempts: int = 10,
    ) -> RelayBatchResult:
        """Recover stale work and publish at most ``batch_size`` due events."""
        if batch_size < 1 or batch_size > 500:
            raise ValueError("batch_size must be between 1 and 500")
        if max_attempts < 1 or max_attempts > 100:
            raise ValueError("max_attempts must be between 1 and 100")

        now = self._clock()
        recovered, recovery_dead_letters = await self._recover_stale_leases(
            now=now,
            limit=batch_size,
            max_attempts=max_attempts,
        )
        exhausted = await self._terminalize_exhausted(
            now=now,
            limit=batch_size,
            max_attempts=max_attempts,
        )
        published = 0
        suppressed = 0
        retry_scheduled = 0
        dead_lettered = recovery_dead_letters + exhausted
        claimed = 0

        for _ in range(batch_size):
            event = await self._claim_one(now=self._clock(), max_attempts=max_attempts)
            if event is None:
                break
            claimed += 1

            try:
                suppression_reason = await self._suppression_reason_for(event)
            except Exception:
                disposition = await self._record_failure(
                    event,
                    reason_code="PUBLISHER_UNEXPECTED_ERROR",
                    retryable=True,
                    now=self._clock(),
                    max_attempts=max_attempts,
                )
                if disposition == "RETRY":
                    retry_scheduled += 1
                else:
                    dead_lettered += 1
                continue

            if suppression_reason is not None:
                await self._settle(
                    event,
                    delivery_status="SUPPRESSED",
                    now=self._clock(),
                    last_error=suppression_reason,
                )
                suppressed += 1
                continue

            # Missing tenant events are suppressed above, so the adapter's
            # provider-neutral contract can keep tenant_id non-null.
            assert event.tenant_id is not None
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
                disposition = await self._record_failure(
                    event,
                    reason_code=reason_code,
                    retryable=retryable,
                    now=self._clock(),
                    max_attempts=max_attempts,
                )
                if disposition == "RETRY":
                    retry_scheduled += 1
                else:
                    dead_lettered += 1
            else:
                published_at = self._clock()
                await self._settle(
                    event,
                    delivery_status="PUBLISHED",
                    now=published_at,
                    published_at=published_at,
                    last_error=None,
                )
                published += 1

        return RelayBatchResult(
            claimed=claimed,
            published=published,
            suppressed=suppressed,
            retry_scheduled=retry_scheduled,
            dead_lettered=dead_lettered,
            leases_recovered=recovered,
        )

    async def _recover_stale_leases(
        self,
        *,
        now: datetime,
        limit: int,
        max_attempts: int,
    ) -> tuple[int, int]:
        recovered = 0
        dead_lettered = 0
        async with self._session_factory() as session, session.begin():
            events = list(
                (
                    await session.execute(
                        select(OutboxEvent)
                        .where(
                            OutboxEvent.delivery_status == "PUBLISHING",
                            OutboxEvent.lease_expires_at <= now,
                        )
                        .order_by(OutboxEvent.lease_expires_at, OutboxEvent.outbox_event_id)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for event in events:
                recovered += 1
                event.lease_token = None
                event.lease_owner = None
                event.lease_expires_at = None
                event.last_error = "PUBLISHER_LEASE_EXPIRED"
                if event.attempt_count >= max_attempts:
                    event.delivery_status = "DEAD_LETTER"
                    event.last_dead_lettered_at = now
                    event.last_dead_letter_reason = "PUBLISHER_LEASE_EXPIRED"
                    dead_lettered += 1
                else:
                    event.delivery_status = "FAILED"
                    event.next_attempt_at = now
        return recovered, dead_lettered

    async def _terminalize_exhausted(
        self,
        *,
        now: datetime,
        limit: int,
        max_attempts: int,
    ) -> int:
        async with self._session_factory() as session, session.begin():
            events = list(
                (
                    await session.execute(
                        select(OutboxEvent)
                        .where(
                            OutboxEvent.delivery_status == "FAILED",
                            OutboxEvent.attempt_count >= max_attempts,
                        )
                        .order_by(OutboxEvent.created_at, OutboxEvent.outbox_event_id)
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for event in events:
                event.delivery_status = "DEAD_LETTER"
                event.last_error = "PUBLISHER_ATTEMPT_LIMIT_REACHED"
                event.last_dead_lettered_at = now
                event.last_dead_letter_reason = "PUBLISHER_ATTEMPT_LIMIT_REACHED"
            return len(events)

    async def _claim_one(
        self,
        *,
        now: datetime,
        max_attempts: int,
    ) -> ClaimedOutboxEvent | None:
        async with self._session_factory() as session, session.begin():
            event = await session.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.delivery_status.in_(["PENDING", "FAILED"]),
                    OutboxEvent.next_attempt_at <= now,
                    OutboxEvent.attempt_count < max_attempts,
                )
                .order_by(
                    OutboxEvent.next_attempt_at,
                    OutboxEvent.created_at,
                    OutboxEvent.outbox_event_id,
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                return None
            lease_token = uuid4()
            event.delivery_status = "PUBLISHING"
            event.attempt_count += 1
            event.last_attempt_at = now
            event.lease_token = lease_token
            event.lease_owner = self._worker_id
            event.lease_expires_at = now + self._lease_duration
            event.last_error = None
            await session.flush()
            return ClaimedOutboxEvent(
                outbox_event_id=event.outbox_event_id,
                event_id=event.event_id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                aggregate_version=event.aggregate_version,
                tenant_id=event.tenant_id,
                elder_id=event.elder_id,
                actor_id=event.actor_id,
                purpose=event.purpose,
                consent_version=event.consent_version,
                trace_id=event.trace_id,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                idempotency_key=event.idempotency_key,
                classification=event.classification,
                payload=event.payload,
                occurred_at=event.occurred_at,
                attempt_count=event.attempt_count,
                lease_token=lease_token,
            )

    async def _record_failure(
        self,
        event: ClaimedOutboxEvent,
        *,
        reason_code: str,
        retryable: bool,
        now: datetime,
        max_attempts: int,
    ) -> str:
        failure = EventDeliveryFailure.for_attempt(
            event_id=event.event_id,
            stage="PUBLISHER",
            reason_code=reason_code,
            retryable=retryable,
            attempt_count=event.attempt_count,
            max_attempts=max_attempts,
        )
        if failure.disposition == "RETRY":
            await self._settle(
                event,
                delivery_status="FAILED",
                now=now,
                next_attempt_at=now + self._retry_delay(event.attempt_count),
                last_error=failure.reason_code,
            )
        else:
            await self._settle(
                event,
                delivery_status="DEAD_LETTER",
                now=now,
                last_error=failure.reason_code,
                last_dead_lettered_at=now,
                last_dead_letter_reason=failure.reason_code,
            )
        return failure.disposition

    async def _settle(
        self,
        event: ClaimedOutboxEvent,
        *,
        delivery_status: str,
        now: datetime,
        **values: Any,
    ) -> None:
        values.update(
            delivery_status=delivery_status,
            lease_token=None,
            lease_owner=None,
            lease_expires_at=None,
            updated_at=now,
        )
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(OutboxEvent)
                .where(
                    OutboxEvent.outbox_event_id == event.outbox_event_id,
                    OutboxEvent.delivery_status == "PUBLISHING",
                    OutboxEvent.lease_token == event.lease_token,
                    OutboxEvent.lease_owner == self._worker_id,
                )
                .values(**values)
            )
            if result.rowcount != 1:
                raise OutboxLeaseLostError(
                    f"outbox lease lost for event {event.event_id}; settlement refused"
                )

    def _retry_delay(self, attempt_count: int) -> timedelta:
        multiplier = 2 ** min(attempt_count - 1, 30)
        return min(self._retry_base * multiplier, self._retry_max)

    async def _suppression_reason_for(self, event: ClaimedOutboxEvent) -> str | None:
        async with self._session_factory() as session, session.begin():
            return await self._suppression_reason(session, event)

    @staticmethod
    async def _suppression_reason(
        session: AsyncSession,
        event: ClaimedOutboxEvent,
    ) -> str | None:
        if event.tenant_id is None:
            return "SUPPRESSED_MISSING_TENANT"
        if event.event_type in REVOCATION_SAFE_EVENTS:
            return None
        if event.elder_id is not None and event.purpose is not None:
            now = datetime.now(UTC)
            active_consent = await session.scalar(
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

        if await DeletionRepository(session, event.tenant_id).has_tombstone(
            resource_type=event.aggregate_type,
            resource_id=event.aggregate_id,
        ):
            return "SUPPRESSED_DELETION_TOMBSTONE"

        if event.aggregate_type == "memory":
            status = await session.scalar(
                select(Memory.status).where(
                    Memory.id == event.aggregate_id,
                    Memory.tenant_id == event.tenant_id,
                )
            )
            if status == "DELETED":
                return "SUPPRESSED_TOMBSTONED_MEMORY"
        elif event.aggregate_type == "care_event":
            status = await session.scalar(
                select(CareEvent.status).where(
                    CareEvent.id == event.aggregate_id,
                    CareEvent.tenant_id == event.tenant_id,
                )
            )
            if status == "DELETED":
                return "SUPPRESSED_TOMBSTONED_EVENT"
        elif event.aggregate_type == "family_report":
            status = await session.scalar(
                select(FamilyReport.status).where(
                    FamilyReport.id == event.aggregate_id,
                    FamilyReport.tenant_id == event.tenant_id,
                )
            )
            if status == "WITHDRAWN":
                return "SUPPRESSED_WITHDRAWN_REPORT"
        return None

    @staticmethod
    def _envelope(event: ClaimedOutboxEvent) -> dict[str, Any]:
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


async def redrive_dead_letter(
    session_factory: async_sessionmaker[AsyncSession],
    event_id: UUID,
    *,
    now: datetime | None = None,
) -> bool:
    """Requeue one dead-lettered event while retaining its DLQ history."""
    redriven_at = now or datetime.now(UTC)
    async with session_factory() as session, session.begin():
        event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_id == event_id).with_for_update()
        )
        if event is None or event.delivery_status != "DEAD_LETTER":
            return False
        event.delivery_status = "PENDING"
        event.attempt_count = 0
        event.next_attempt_at = redriven_at
        event.last_attempt_at = None
        event.lease_token = None
        event.lease_owner = None
        event.lease_expires_at = None
        event.last_error = None
        event.redrive_count += 1
        event.last_redriven_at = redriven_at
        return True

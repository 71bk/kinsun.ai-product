"""Gate 1 synthetic graph projection built from immutable domain events.

Aurora remains authoritative. The projection stores only a stable reference;
every read joins back to current formal state, so lag, replay, revocation, and
deletion can never grant access or resurrect content.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.consumer import ConsumerResult, DomainEvent, IdempotentEventConsumer
from app.models.care_event import CareEvent
from app.models.graph_projection import GraphProjectionRecord
from app.models.memory import Memory


class SyntheticGraphProjectionConsumer:
    """Idempotent local/test projection adapter approved by ADR 0009."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._consumer = IdempotentEventConsumer(session, "synthetic_graph_projection")

    async def consume(
        self,
        event: DomainEvent,
        *,
        attempt_count: int = 1,
        max_attempts: int = 5,
    ) -> ConsumerResult:
        return await self._consumer.process(
            event,
            self._project,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
        )

    async def _project(self, event: DomainEvent) -> None:
        model_and_formal_statuses = {
            "memory": (Memory, {"ACTIVE"}),
            "care_event": (CareEvent, {"VERIFIED", "CORRECTED"}),
        }
        selected = model_and_formal_statuses.get(event.aggregate.type)
        if selected is None:
            return
        aggregate_model, formal_statuses = selected
        aggregate = await self._session.scalar(
            select(aggregate_model).where(
                aggregate_model.id == event.aggregate.id,
                aggregate_model.tenant_id == event.tenant_id,
            )
        )
        latest = await self._session.scalar(
            select(GraphProjectionRecord)
            .where(
                GraphProjectionRecord.source_type == event.aggregate.type,
                GraphProjectionRecord.source_id == event.aggregate.id,
            )
            .order_by(GraphProjectionRecord.source_version.desc())
            .limit(1)
            .with_for_update()
        )
        if latest is not None and latest.source_version > event.aggregate.version:
            return

        current_version = (
            aggregate.current_version if aggregate is not None else event.aggregate.version
        )
        # A delayed older event must never overwrite a newer formal version.
        if aggregate is not None and current_version > event.aggregate.version:
            return
        status = getattr(aggregate, "status", None)
        should_exist = aggregate is not None and status in formal_statuses
        record = (
            latest
            if latest is not None and latest.source_version == event.aggregate.version
            else GraphProjectionRecord(
                source_type=event.aggregate.type,
                source_id=event.aggregate.id,
                source_version=event.aggregate.version,
                attempt_count=0,
            )
        )
        if record is not latest:
            self._session.add(record)
        record.attempt_count += 1
        record.outbox_event_id = event.event_id
        record.projection_status = "SYNCED" if should_exist else "REMOVED"
        record.graph_key = (
            "synthetic://"
            f"tenant/{event.tenant_id}/elder/{event.elder_id}/"
            f"{event.aggregate.type}/{event.aggregate.id}/v/{event.aggregate.version}"
            if should_exist
            else None
        )
        record.last_error = None
        record.synced_at = datetime.now(UTC)
        await self._session.flush()

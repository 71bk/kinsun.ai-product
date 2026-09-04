"""PostgreSQL proofs for leased outbox delivery, recovery, and redrive."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.events.failures import EventPublishError
from app.events.outbox_writer import write_outbox_entry
from app.events.publisher import EventPublisher, FakePublisher
from app.events.relay import OutboxRelay, redrive_dead_letter
from app.models.outbox import OutboxEvent
from app.models.tenant import Tenant


class _FailingPublisher(EventPublisher):
    async def publish(
        self,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: UUID,
        payload: dict,
    ) -> None:
        raise EventPublishError("PUBLISHER_DEPENDENCY_TIMEOUT", retryable=True)


async def _seed_event(session, *, event_id: UUID) -> None:
    tenant_id = uuid4()
    session.add(Tenant(id=tenant_id, tenant_type="DEMO", name=f"Outbox {event_id}"))
    await session.flush()
    await write_outbox_entry(
        session,
        event_type="test.delivered.v1",
        aggregate_type="delivery_probe",
        aggregate_id=uuid4(),
        tenant_id=tenant_id,
        payload={"status": "READY"},
        trace_id=f"trace-{event_id}",
        event_id=event_id,
    )
    await session.commit()


async def test_concurrent_relays_claim_each_event_once(committed_session, test_engine) -> None:
    event_ids = [uuid4(), uuid4()]
    for event_id in event_ids:
        await _seed_event(committed_session, event_id=event_id)

    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    publisher = FakePublisher()
    # Keep the worker clock after PostgreSQL's server_default now(); a fixed
    # wall-clock earlier than the CI database clock would correctly make the
    # freshly inserted rows not due yet.
    fixed_now = datetime.now(UTC) + timedelta(minutes=1)
    relays = [
        OutboxRelay(
            session_factory,
            publisher,
            worker_id=f"concurrent-{index}",
            clock=lambda: fixed_now,
        )
        for index in range(2)
    ]

    results = await asyncio.gather(
        relays[0].relay_once(batch_size=2),
        relays[1].relay_once(batch_size=2),
    )

    assert sum(result.published for result in results) == 2
    published_ids = [event["payload"]["event_id"] for event in publisher.events]
    assert sorted(published_ids) == sorted(str(event_id) for event_id in event_ids)
    async with session_factory() as session:
        statuses = list(
            (
                await session.execute(
                    select(OutboxEvent.delivery_status).where(OutboxEvent.event_id.in_(event_ids))
                )
            )
            .scalars()
            .all()
        )
    assert statuses == ["PUBLISHED", "PUBLISHED"]


async def test_stale_publishing_lease_is_recovered_and_republished(
    committed_session,
    test_engine,
) -> None:
    event_id = uuid4()
    await _seed_event(committed_session, event_id=event_id)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    fixed_now = datetime(2026, 9, 4, 3, 0, tzinfo=UTC)
    async with session_factory() as session, session.begin():
        event = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_id == event_id).with_for_update()
        )
        assert event is not None
        event.delivery_status = "PUBLISHING"
        event.attempt_count = 1
        event.last_attempt_at = fixed_now - timedelta(minutes=2)
        event.lease_token = uuid4()
        event.lease_owner = "crashed-worker"
        event.lease_expires_at = fixed_now - timedelta(minutes=1)

    publisher = FakePublisher()
    result = await OutboxRelay(
        session_factory,
        publisher,
        worker_id="recovery-worker",
        clock=lambda: fixed_now,
    ).relay_once(batch_size=1, max_attempts=3)

    assert result.leases_recovered == 1
    assert result.published == 1
    async with session_factory() as session:
        event = await session.scalar(select(OutboxEvent).where(OutboxEvent.event_id == event_id))
    assert event is not None
    assert event.delivery_status == "PUBLISHED"
    assert event.attempt_count == 2
    assert event.lease_token is None


async def test_retry_exhaustion_enters_durable_dlq_and_can_be_redriven(
    committed_session,
    test_engine,
) -> None:
    event_id = uuid4()
    await _seed_event(committed_session, event_id=event_id)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    first_attempt = datetime(2026, 9, 4, 4, 0, tzinfo=UTC)

    first = await OutboxRelay(
        session_factory,
        _FailingPublisher(),
        worker_id="failing-worker-1",
        retry_base=timedelta(seconds=2),
        clock=lambda: first_attempt,
    ).relay_once(batch_size=1, max_attempts=2)
    assert first.retry_scheduled == 1

    second_attempt = first_attempt + timedelta(seconds=2)
    second = await OutboxRelay(
        session_factory,
        _FailingPublisher(),
        worker_id="failing-worker-2",
        retry_base=timedelta(seconds=2),
        clock=lambda: second_attempt,
    ).relay_once(batch_size=1, max_attempts=2)
    assert second.dead_lettered == 1

    async with session_factory() as session:
        dead_letter = await session.scalar(
            select(OutboxEvent).where(OutboxEvent.event_id == event_id)
        )
    assert dead_letter is not None
    assert dead_letter.delivery_status == "DEAD_LETTER"
    assert dead_letter.last_dead_letter_reason == "PUBLISHER_DEPENDENCY_TIMEOUT"
    assert dead_letter.last_dead_lettered_at == second_attempt

    redrive_time = second_attempt + timedelta(minutes=1)
    assert await redrive_dead_letter(session_factory, event_id, now=redrive_time) is True
    success = await OutboxRelay(
        session_factory,
        FakePublisher(),
        worker_id="redrive-worker",
        clock=lambda: redrive_time,
    ).relay_once(batch_size=1, max_attempts=2)
    assert success.published == 1

    async with session_factory() as session:
        redriven = await session.scalar(select(OutboxEvent).where(OutboxEvent.event_id == event_id))
    assert redriven is not None
    assert redriven.delivery_status == "PUBLISHED"
    assert redriven.attempt_count == 1
    assert redriven.redrive_count == 1
    assert redriven.last_redriven_at == redrive_time
    assert redriven.last_dead_letter_reason == "PUBLISHER_DEPENDENCY_TIMEOUT"

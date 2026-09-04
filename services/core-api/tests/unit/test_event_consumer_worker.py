"""Queue settlement tests for the provider-neutral event consumer worker."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from app.events.consumer import ConsumerResult, DomainEvent
from app.events.consumer_worker import EventConsumerWorker
from app.events.failures import EventConsumerFailure, EventDeliveryFailure


class _Transaction:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, _exc, _traceback) -> None:
        self._calls.append("commit" if exc_type is None else "rollback")


class _Session:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback) -> None:
        return None

    def begin(self) -> _Transaction:
        return _Transaction(self._calls)


class _SessionFactory:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    def __call__(self) -> _Session:
        return _Session(self._calls)


def _event() -> DomainEvent:
    tenant_id = uuid4()
    return DomainEvent(
        event_id=uuid4(),
        event_type="memory.confirmed.v1",
        event_version=1,
        occurred_at=datetime.now(UTC),
        tenant_id=tenant_id,
        elder_id=None,
        actor_id=None,
        purpose=None,
        consent_version=None,
        trace_id="trace-1",
        correlation_id=None,
        causation_id=None,
        idempotency_key=None,
        classification="RESTRICTED",
        aggregate={"type": "memory", "id": uuid4(), "version": 1},
        payload={"status": "ACTIVE"},
    )


async def test_commits_before_acknowledging(monkeypatch) -> None:
    calls: list[str] = []
    consumer = AsyncMock()
    consumer.process.return_value = ConsumerResult(status="PROCESSED")
    monkeypatch.setattr(
        "app.events.consumer_worker.IdempotentEventConsumer",
        lambda *_args, **_kwargs: consumer,
    )
    settlement = AsyncMock()
    settlement.acknowledge.side_effect = lambda: calls.append("acknowledge")
    worker = EventConsumerWorker(
        _SessionFactory(calls),
        consumer_name="graph_projection",
    )

    outcome = await worker.process(_event(), AsyncMock(), settlement, attempt_count=1)

    assert outcome.status == "ACKNOWLEDGED"
    assert calls == ["commit", "acknowledge"]
    settlement.retry.assert_not_awaited()
    settlement.dead_letter.assert_not_awaited()


async def test_rolls_back_and_schedules_retry_without_acknowledging(monkeypatch) -> None:
    calls: list[str] = []
    event = _event()
    failure = EventDeliveryFailure.for_attempt(
        event_id=event.event_id,
        stage="CONSUMER",
        reason_code="CONSUMER_PROCESSING_FAILED",
        retryable=True,
        attempt_count=1,
        max_attempts=3,
        consumer_name="graph_projection",
    )
    consumer = AsyncMock()
    consumer.process.side_effect = EventConsumerFailure(failure)
    monkeypatch.setattr(
        "app.events.consumer_worker.IdempotentEventConsumer",
        lambda *_args, **_kwargs: consumer,
    )
    settlement = AsyncMock()
    worker = EventConsumerWorker(
        _SessionFactory(calls),
        consumer_name="graph_projection",
        max_attempts=3,
    )

    outcome = await worker.process(event, AsyncMock(), settlement, attempt_count=1)

    assert outcome.status == "RETRY_SCHEDULED"
    assert calls == ["rollback"]
    settlement.retry.assert_awaited_once_with(failure, 2.0)
    settlement.acknowledge.assert_not_awaited()
    settlement.dead_letter.assert_not_awaited()


async def test_dead_letters_durably_before_acknowledging(monkeypatch) -> None:
    calls: list[str] = []
    event = _event()
    failure = EventDeliveryFailure.for_attempt(
        event_id=event.event_id,
        stage="CONSUMER",
        reason_code="CONSUMER_SCHEMA_UNSUPPORTED",
        retryable=False,
        attempt_count=1,
        max_attempts=3,
        consumer_name="graph_projection",
    )
    consumer = AsyncMock()
    consumer.process.side_effect = EventConsumerFailure(failure)
    monkeypatch.setattr(
        "app.events.consumer_worker.IdempotentEventConsumer",
        lambda *_args, **_kwargs: consumer,
    )
    settlement = AsyncMock()
    settlement.dead_letter.side_effect = lambda _failure: calls.append("dead_letter")
    settlement.acknowledge.side_effect = lambda: calls.append("acknowledge")
    worker = EventConsumerWorker(
        _SessionFactory(calls),
        consumer_name="graph_projection",
        max_attempts=3,
    )

    outcome = await worker.process(event, AsyncMock(), settlement, attempt_count=1)

    assert outcome.status == "DEAD_LETTERED"
    assert calls == ["rollback", "dead_letter", "acknowledge"]

"""Unit tests for outbox suppression and bounded retry policy."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from app.events.relay import OutboxRelay, RelayBatchResult


async def test_relay_suppresses_resource_with_deletion_tombstone() -> None:
    session = AsyncMock()
    session.scalar.return_value = uuid4()
    event = SimpleNamespace(
        event_type="memory.confirmed.v1",
        tenant_id=uuid4(),
        elder_id=uuid4(),
        purpose=None,
        consent_version=None,
        aggregate_type="memory",
        aggregate_id=uuid4(),
    )

    reason = await OutboxRelay._suppression_reason(session, event)

    assert reason == "SUPPRESSED_DELETION_TOMBSTONE"


async def test_relay_allows_deletion_completion_without_tombstone_lookup() -> None:
    session = AsyncMock()
    event = SimpleNamespace(
        event_type="deletion.completed.v1",
        tenant_id=uuid4(),
        elder_id=uuid4(),
        purpose=None,
        consent_version=None,
        aggregate_type="deletion_request",
        aggregate_id=uuid4(),
    )

    reason = await OutboxRelay._suppression_reason(session, event)

    assert reason is None
    session.scalar.assert_not_awaited()


def test_retry_delay_is_exponential_and_capped() -> None:
    relay = OutboxRelay(
        AsyncMock(),
        AsyncMock(),
        worker_id="test-worker",
        retry_base=timedelta(seconds=2),
        retry_max=timedelta(seconds=5),
    )

    assert relay._retry_delay(1) == timedelta(seconds=2)
    assert relay._retry_delay(2) == timedelta(seconds=4)
    assert relay._retry_delay(3) == timedelta(seconds=5)


def test_relay_result_reports_recovery_only_as_progress() -> None:
    assert RelayBatchResult(leases_recovered=1).made_progress is True
    assert RelayBatchResult().made_progress is False

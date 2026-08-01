"""Deletion tombstone gates for the provider-neutral outbox relay."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.events.relay import OutboxRelay


async def test_relay_suppresses_resource_with_deletion_tombstone() -> None:
    session = AsyncMock()
    session.scalar.return_value = uuid4()
    relay = OutboxRelay(session, AsyncMock())
    event = SimpleNamespace(
        event_type="memory.confirmed.v1",
        tenant_id=uuid4(),
        elder_id=uuid4(),
        purpose=None,
        consent_version=None,
        aggregate_type="memory",
        aggregate_id=uuid4(),
    )

    reason = await relay._suppression_reason(event)

    assert reason == "SUPPRESSED_DELETION_TOMBSTONE"


async def test_relay_allows_deletion_completion_without_tombstone_lookup() -> None:
    session = AsyncMock()
    relay = OutboxRelay(session, AsyncMock())
    event = SimpleNamespace(
        event_type="deletion.completed.v1",
        tenant_id=uuid4(),
        elder_id=uuid4(),
        purpose=None,
        consent_version=None,
        aggregate_type="deletion_request",
        aggregate_id=uuid4(),
    )

    reason = await relay._suppression_reason(event)

    assert reason is None
    session.scalar.assert_not_awaited()


async def test_relay_terminalizes_failed_event_already_at_attempt_limit() -> None:
    result = MagicMock()
    event = SimpleNamespace(
        delivery_status="FAILED",
        attempt_count=3,
        last_error="PUBLISHER_DEPENDENCY_TIMEOUT",
    )
    result.scalars.return_value.all.return_value = [event]
    session = AsyncMock()
    session.execute.return_value = result
    publisher = AsyncMock()
    relay = OutboxRelay(session, publisher)

    published, suppressed, failed = await relay.relay_once(max_attempts=3)

    assert (published, suppressed, failed) == (0, 0, 1)
    assert event.delivery_status == "DEAD_LETTER"
    assert event.last_error == "PUBLISHER_ATTEMPT_LIMIT_REACHED"
    publisher.publish.assert_not_awaited()

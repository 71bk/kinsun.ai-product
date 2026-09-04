"""Development synthetic projection relay boundary tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.events.synthetic_projection import SyntheticProjectionPublisher


def envelope() -> dict:
    tenant_id = uuid4()
    aggregate_id = uuid4()
    return {
        "event_id": str(uuid4()),
        "event_type": "memory.confirmed.v1",
        "event_version": 1,
        "occurred_at": datetime.now(UTC).isoformat(),
        "tenant_id": str(tenant_id),
        "elder_id": str(uuid4()),
        "actor_id": str(uuid4()),
        "purpose": "LONG_TERM_MEMORY",
        "consent_version": 1,
        "trace_id": "trace-synthetic-projection",
        "correlation_id": "correlation-synthetic-projection",
        "causation_id": None,
        "idempotency_key": "synthetic-projection",
        "classification": "CONFIDENTIAL",
        "aggregate": {
            "type": "memory",
            "id": str(aggregate_id),
            "version": 1,
        },
        "payload": {"status": "ACTIVE", "version": 1},
    }


@pytest.mark.asyncio
async def test_synthetic_publisher_validates_and_consumes_envelope() -> None:
    payload = envelope()
    session_factory = MagicMock()
    session_context = AsyncMock()
    session = MagicMock()
    transaction = AsyncMock()
    session_context.__aenter__.return_value = session
    session.begin.return_value = transaction
    session_factory.return_value = session_context
    consumer = AsyncMock()

    with patch("app.events.synthetic_projection.SyntheticGraphProjectionConsumer") as consumer_type:
        consumer_type.return_value.consume = consumer
        await SyntheticProjectionPublisher(session_factory).publish(
            payload["event_type"],
            UUID(payload["aggregate"]["id"]),
            UUID(payload["tenant_id"]),
            payload,
        )

    consumer.assert_awaited_once()
    session.begin.assert_called_once_with()


@pytest.mark.asyncio
async def test_synthetic_publisher_rejects_mismatched_metadata() -> None:
    payload = envelope()
    session_factory = MagicMock()

    with pytest.raises(ValueError, match="metadata does not match"):
        await SyntheticProjectionPublisher(session_factory).publish(
            payload["event_type"],
            uuid4(),
            UUID(payload["tenant_id"]),
            payload,
        )

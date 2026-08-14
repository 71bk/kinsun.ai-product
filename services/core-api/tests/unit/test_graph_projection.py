"""Synthetic projection never outranks current formal Core state."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.events.consumer import DomainEvent, EventAggregate
from app.events.graph_projection import SyntheticGraphProjectionConsumer


def event(*, aggregate_type: str = "memory", version: int = 2) -> DomainEvent:
    return DomainEvent(
        event_id=uuid4(),
        event_type="memory.confirmed.v1",
        event_version=1,
        occurred_at=datetime.now(UTC),
        tenant_id=uuid4(),
        elder_id=uuid4(),
        actor_id=uuid4(),
        purpose="LONG_TERM_MEMORY",
        consent_version=2,
        trace_id="trace-projection-001",
        correlation_id="correlation-projection-001",
        causation_id=None,
        idempotency_key="projection-001",
        classification="CONFIDENTIAL",
        aggregate=EventAggregate(type=aggregate_type, id=uuid4(), version=version),
        payload={"status": "ACTIVE", "version": version},
    )


@pytest.mark.asyncio
async def test_active_current_memory_projects_only_a_stable_reference() -> None:
    domain_event = event()
    session = MagicMock()
    session.scalar = AsyncMock(
        side_effect=[
            SimpleNamespace(status="ACTIVE", current_version=2),
            None,
        ]
    )
    session.flush = AsyncMock()

    await SyntheticGraphProjectionConsumer(session)._project(domain_event)

    record = session.add.call_args.args[0]
    assert record.projection_status == "SYNCED"
    assert str(domain_event.tenant_id) in record.graph_key
    assert str(domain_event.elder_id) in record.graph_key
    assert record.source_id == domain_event.aggregate.id
    assert not hasattr(record, "content")
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_deleted_formal_memory_removes_projection_reference() -> None:
    domain_event = event()
    existing = SimpleNamespace(
        source_version=2,
        attempt_count=1,
        graph_key="synthetic://old-reference",
        projection_status="SYNCED",
        outbox_event_id=None,
        last_error=None,
        synced_at=None,
    )
    session = MagicMock()
    session.scalar = AsyncMock(
        side_effect=[
            SimpleNamespace(status="DELETED", current_version=2),
            existing,
        ]
    )
    session.flush = AsyncMock()

    await SyntheticGraphProjectionConsumer(session)._project(domain_event)

    assert existing.projection_status == "REMOVED"
    assert existing.graph_key is None
    assert existing.attempt_count == 2


@pytest.mark.asyncio
async def test_out_of_order_event_cannot_regress_projection() -> None:
    domain_event = event(version=1)
    session = MagicMock()
    session.scalar = AsyncMock(
        side_effect=[
            SimpleNamespace(status="ACTIVE", current_version=2),
            SimpleNamespace(source_version=2),
        ]
    )
    session.flush = AsyncMock()

    await SyntheticGraphProjectionConsumer(session)._project(domain_event)

    session.add.assert_not_called()
    session.flush.assert_not_awaited()

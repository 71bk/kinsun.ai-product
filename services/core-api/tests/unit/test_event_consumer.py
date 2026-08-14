"""Replay, consent, restricted-data, and failure gates for consumer input."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.events.consumer import DomainEvent, IdempotentEventConsumer
from app.events.failures import EventConsumerFailure, EventHandlerError


def _event(**overrides) -> DomainEvent:
    values = {
        "event_id": uuid4(),
        "event_type": "memory.confirmed.v1",
        "event_version": 1,
        "occurred_at": datetime.now(UTC),
        "tenant_id": uuid4(),
        "elder_id": uuid4(),
        "actor_id": uuid4(),
        "purpose": "LONG_TERM_MEMORY",
        "consent_version": 2,
        "trace_id": "trace-1",
        "correlation_id": "trace-1",
        "causation_id": None,
        "idempotency_key": None,
        "classification": "CONFIDENTIAL",
        "aggregate": {"type": "memory", "id": uuid4(), "version": 1},
        "payload": {"memory_id": str(uuid4())},
    }
    values.update(overrides)
    return DomainEvent.model_validate(values)


def test_domain_event_rejects_nested_restricted_data() -> None:
    with pytest.raises(ValidationError):
        _event(payload={"context": {"transcript": "restricted"}})


def test_domain_event_accepts_immutable_legacy_family_invitation_name() -> None:
    legacy = _event(event_type="family_invitation.issued.v1")

    assert legacy.event_type == "family_invitation.issued.v1"


def test_consumer_name_is_stable_and_bounded() -> None:
    with pytest.raises(ValueError):
        IdempotentEventConsumer(AsyncMock(), "Projection Consumer!")


async def test_consumer_suppresses_missing_consent_version() -> None:
    consumer = IdempotentEventConsumer(AsyncMock(), "graph_projection")
    event = _event(consent_version=None)

    reason = await consumer._suppression_reason(event)

    assert reason == "SUPPRESSED_MISSING_CONSENT_VERSION"


async def test_consumer_allows_revocation_event_without_active_consent() -> None:
    session = AsyncMock()
    consumer = IdempotentEventConsumer(session, "graph_projection")
    event = _event(
        event_type="consent.revoked.v1",
        purpose=None,
        consent_version=None,
        aggregate={"type": "consent", "id": uuid4(), "version": 1},
    )

    reason = await consumer._suppression_reason(event)

    assert reason is None
    session.scalar.assert_not_awaited()


async def test_consumer_suppresses_resource_with_deletion_tombstone() -> None:
    session = AsyncMock()
    session.scalar.side_effect = [uuid4()]
    consumer = IdempotentEventConsumer(session, "graph_projection")
    event = _event(purpose=None, consent_version=None)

    reason = await consumer._suppression_reason(event)

    assert reason == "SUPPRESSED_DELETION_TOMBSTONE"


async def test_unexpected_consumer_failure_is_safe_and_retryable() -> None:
    session = AsyncMock()
    consumer = IdempotentEventConsumer(session, "graph_projection")
    event = _event(
        event_type="consent.revoked.v1",
        purpose=None,
        consent_version=None,
        aggregate={"type": "consent", "id": uuid4(), "version": 1},
    )
    handler = AsyncMock(side_effect=RuntimeError("token=secret-value"))

    with patch("app.events.consumer.IdempotencyRepository") as repository_class:
        repository = repository_class.return_value
        repository.begin = AsyncMock(return_value=SimpleNamespace(replayed=False))
        repository.complete = AsyncMock()

        with pytest.raises(EventConsumerFailure) as exc_info:
            await consumer.process(event, handler, attempt_count=1, max_attempts=3)

    failure = exc_info.value.failure
    assert failure.reason_code == "CONSUMER_PROCESSING_FAILED"
    assert failure.retryable is True
    assert failure.disposition == "RETRY"
    assert "secret-value" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__context__ is None
    repository.complete.assert_not_awaited()


async def test_declared_non_retryable_handler_failure_dead_letters() -> None:
    session = AsyncMock()
    consumer = IdempotentEventConsumer(session, "graph_projection")
    event = _event(
        event_type="consent.revoked.v1",
        purpose=None,
        consent_version=None,
        aggregate={"type": "consent", "id": uuid4(), "version": 1},
    )
    handler = AsyncMock(
        side_effect=EventHandlerError("CONSUMER_SCHEMA_UNSUPPORTED", retryable=False)
    )

    with patch("app.events.consumer.IdempotencyRepository") as repository_class:
        repository = repository_class.return_value
        repository.begin = AsyncMock(return_value=SimpleNamespace(replayed=False))
        repository.complete = AsyncMock()

        with pytest.raises(EventConsumerFailure) as exc_info:
            await consumer.process(event, handler, attempt_count=1, max_attempts=5)

    failure = exc_info.value.failure
    assert failure.reason_code == "CONSUMER_SCHEMA_UNSUPPORTED"
    assert failure.retryable is False
    assert failure.disposition == "DEAD_LETTER"
    repository.complete.assert_not_awaited()

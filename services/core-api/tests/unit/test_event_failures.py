"""Publisher and consumer failure-contract invariants."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.events.failures import (
    EventConsumerFailure,
    EventDeliveryFailure,
    EventPublishError,
)


def test_retryable_failure_retries_before_attempt_limit() -> None:
    failure = EventDeliveryFailure.for_attempt(
        event_id=uuid4(),
        stage="PUBLISHER",
        reason_code="PUBLISHER_DEPENDENCY_TIMEOUT",
        retryable=True,
        attempt_count=2,
        max_attempts=3,
    )

    assert failure.disposition == "RETRY"
    assert failure.consumer_name is None


def test_retryable_failure_dead_letters_at_attempt_limit() -> None:
    failure = EventDeliveryFailure.for_attempt(
        event_id=uuid4(),
        stage="CONSUMER",
        reason_code="CONSUMER_PROCESSING_FAILED",
        retryable=True,
        attempt_count=3,
        max_attempts=3,
        consumer_name="graph_projection",
    )

    assert failure.disposition == "DEAD_LETTER"


def test_non_retryable_failure_dead_letters_immediately() -> None:
    failure = EventDeliveryFailure.for_attempt(
        event_id=uuid4(),
        stage="PUBLISHER",
        reason_code="PUBLISHER_SCHEMA_REJECTED",
        retryable=False,
        attempt_count=1,
        max_attempts=10,
    )

    assert failure.disposition == "DEAD_LETTER"


def test_consumer_failure_requires_consumer_name() -> None:
    with pytest.raises(ValidationError):
        EventDeliveryFailure.for_attempt(
            event_id=uuid4(),
            stage="CONSUMER",
            reason_code="CONSUMER_PROCESSING_FAILED",
            retryable=True,
            attempt_count=1,
            max_attempts=3,
        )


def test_declared_failure_rejects_unstable_reason_code() -> None:
    for reason_code in ("dependency timed out", "TOKEN_SECRET_VALUE"):
        with pytest.raises(ValueError):
            EventPublishError(reason_code, retryable=True)


def test_consumer_exception_exposes_only_safe_contract() -> None:
    failure = EventDeliveryFailure.for_attempt(
        event_id=uuid4(),
        stage="CONSUMER",
        reason_code="CONSUMER_PROCESSING_FAILED",
        retryable=True,
        attempt_count=1,
        max_attempts=3,
        consumer_name="graph_projection",
    )

    error = EventConsumerFailure(failure)

    assert error.failure == failure
    assert str(error) == "CONSUMER:CONSUMER_PROCESSING_FAILED:RETRY"

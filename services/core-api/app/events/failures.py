"""Provider-neutral failure contract for event publication and consumption."""

from __future__ import annotations

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EVENT_FAILURE_REASON_CODES = frozenset(
    {
        "CONSUMER_PROCESSING_FAILED",
        "CONSUMER_SCHEMA_UNSUPPORTED",
        "PUBLISHER_ATTEMPT_LIMIT_REACHED",
        "PUBLISHER_DEPENDENCY_TIMEOUT",
        "PUBLISHER_LEASE_EXPIRED",
        "PUBLISHER_SCHEMA_REJECTED",
        "PUBLISHER_UNEXPECTED_ERROR",
    }
)


class EventDeliveryFailure(BaseModel):
    """Safe failure outcome consumed by transport adapters.

    Raw exception messages are deliberately excluded because they can contain
    credentials, payload fragments, or other restricted data.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    stage: Literal["PUBLISHER", "CONSUMER"]
    reason_code: str
    retryable: bool
    attempt_count: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    disposition: Literal["RETRY", "DEAD_LETTER"]
    consumer_name: str | None = Field(
        pattern=r"^[a-z0-9][a-z0-9_-]{0,47}$",
    )

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, value: str) -> str:
        if value not in EVENT_FAILURE_REASON_CODES:
            raise ValueError("reason_code must come from the event failure registry")
        return value

    @model_validator(mode="after")
    def validate_failure_semantics(self) -> Self:
        if self.stage == "PUBLISHER" and self.consumer_name is not None:
            raise ValueError("publisher failures must not name a consumer")
        if self.stage == "CONSUMER" and self.consumer_name is None:
            raise ValueError("consumer failures must name the consumer")

        should_retry = self.retryable and self.attempt_count < self.max_attempts
        expected_disposition = "RETRY" if should_retry else "DEAD_LETTER"
        if self.disposition != expected_disposition:
            raise ValueError(
                "disposition must be RETRY only for retryable failures before max_attempts"
            )
        return self

    @classmethod
    def for_attempt(
        cls,
        *,
        event_id: UUID,
        stage: Literal["PUBLISHER", "CONSUMER"],
        reason_code: str,
        retryable: bool,
        attempt_count: int,
        max_attempts: int,
        consumer_name: str | None = None,
    ) -> EventDeliveryFailure:
        """Build a failure and derive its disposition deterministically."""
        disposition: Literal["RETRY", "DEAD_LETTER"] = (
            "RETRY" if retryable and attempt_count < max_attempts else "DEAD_LETTER"
        )
        return cls(
            event_id=event_id,
            stage=stage,
            reason_code=reason_code,
            retryable=retryable,
            attempt_count=attempt_count,
            max_attempts=max_attempts,
            disposition=disposition,
            consumer_name=consumer_name,
        )


class EventDeliveryError(Exception):
    """Base for declared adapter/handler failures with safe metadata only."""

    def __init__(self, reason_code: str, *, retryable: bool) -> None:
        if reason_code not in EVENT_FAILURE_REASON_CODES:
            raise ValueError("reason_code must come from the event failure registry")
        self.reason_code = reason_code
        self.retryable = retryable
        super().__init__(reason_code)


class EventPublishError(EventDeliveryError):
    """Failure explicitly classified by an EventPublisher adapter."""


class EventHandlerError(EventDeliveryError):
    """Failure explicitly classified by a domain-event handler."""


class EventConsumerFailure(Exception):
    """Safe failure raised to a queue adapter after consumer work aborts."""

    def __init__(self, failure: EventDeliveryFailure) -> None:
        if failure.stage != "CONSUMER":
            raise ValueError("EventConsumerFailure requires a CONSUMER failure")
        self.failure = failure
        super().__init__(f"CONSUMER:{failure.reason_code}:{failure.disposition}")

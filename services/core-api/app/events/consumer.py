"""Provider-neutral, replay-safe domain-event consumer foundation."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.failures import (
    EventConsumerFailure,
    EventDeliveryFailure,
    EventHandlerError,
)
from app.events.relay import REVOCATION_SAFE_EVENTS
from app.models.care_event import CareEvent
from app.models.consent import ConsentGrant
from app.models.memory import Memory
from app.models.report import FamilyReport
from app.repositories.deletion_repo import DeletionRepository
from app.repositories.idempotency_repo import IdempotencyRepository

RESTRICTED_EVENT_KEYS = {
    "audio",
    "audio_uri",
    "full_prompt",
    "prompt",
    "secret",
    "token",
    "transcript",
    "transcript_text",
}


def _contains_restricted_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in RESTRICTED_EVENT_KEYS or _contains_restricted_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_restricted_key(item) for item in value)
    return False


class EventAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(min_length=1, max_length=80)
    id: UUID
    version: int = Field(ge=1)


class DomainEvent(BaseModel):
    """Strict subset required by every B-owned consumer."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    event_type: str = Field(
        # Underscore remains accepted for immutable legacy
        # ``family_invitation.*`` events. New producers use dot-separated
        # names, but consumers must be able to replay the historical alias.
        pattern=r"^[a-z][a-z0-9._-]+\.v[1-9][0-9]*$",
        max_length=160,
    )
    event_version: Literal[1]
    occurred_at: datetime
    tenant_id: UUID
    elder_id: UUID | None
    actor_id: UUID | None
    purpose: str | None = Field(max_length=64)
    consent_version: int | None = Field(ge=1)
    trace_id: str = Field(min_length=1, max_length=80)
    correlation_id: str | None = Field(min_length=1, max_length=80)
    causation_id: str | None = Field(max_length=80)
    idempotency_key: str | None = Field(max_length=160)
    classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"]
    aggregate: EventAggregate
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def reject_restricted_payload(cls, value: dict[str, Any]) -> dict[str, Any]:
        if _contains_restricted_key(value):
            raise ValueError("payload contains a restricted field")
        return value


@dataclass(frozen=True)
class ConsumerResult:
    status: Literal["PROCESSED", "REPLAYED", "SUPPRESSED"]
    reason_code: str | None = None


class IdempotentEventConsumer:
    """Runs one handler exactly once per consumer and event ID.

    The caller owns transaction commit and queue settlement. On
    EventConsumerFailure it must roll back first. RETRY means do not
    acknowledge the source message; DEAD_LETTER means hand off to a durable
    quarantine/DLQ and acknowledge only after that handoff succeeds. No queue
    or DLQ adapter is implemented by this foundation.
    """

    def __init__(self, session: AsyncSession, consumer_name: str) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", consumer_name):
            raise ValueError("consumer_name must be a stable lowercase identifier")
        self._session = session
        self._consumer_name = consumer_name

    async def process(
        self,
        event: DomainEvent,
        handler: Callable[[DomainEvent], Awaitable[None]],
        *,
        attempt_count: int = 1,
        max_attempts: int = 5,
    ) -> ConsumerResult:
        if attempt_count < 1:
            raise ValueError("attempt_count must be at least 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

        try:
            return await self._process_once(event, handler)
        except EventHandlerError as exc:
            failure = EventDeliveryFailure.for_attempt(
                event_id=event.event_id,
                stage="CONSUMER",
                reason_code=exc.reason_code,
                retryable=exc.retryable,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
                consumer_name=self._consumer_name,
            )
        except EventConsumerFailure:
            raise
        except Exception:
            failure = EventDeliveryFailure.for_attempt(
                event_id=event.event_id,
                stage="CONSUMER",
                reason_code="CONSUMER_PROCESSING_FAILED",
                retryable=True,
                attempt_count=attempt_count,
                max_attempts=max_attempts,
                consumer_name=self._consumer_name,
            )
        raise EventConsumerFailure(failure) from None

    async def _process_once(
        self,
        event: DomainEvent,
        handler: Callable[[DomainEvent], Awaitable[None]],
    ) -> ConsumerResult:
        idempotency_key = f"consumer:{self._consumer_name}:{event.event_id}"
        idempotency = IdempotencyRepository(
            self._session,
            event.tenant_id,
            actor_id=None,
        )
        replay = await idempotency.begin(
            key=idempotency_key,
            operation=f"consume:{self._consumer_name}:{event.event_type}",
            payload={
                "event_id": event.event_id,
                "event_version": event.event_version,
                "aggregate_id": event.aggregate.id,
                "aggregate_version": event.aggregate.version,
                "payload": event.payload,
            },
        )
        if replay.replayed:
            return ConsumerResult(status="REPLAYED")

        suppression_reason = await self._suppression_reason(event)
        if suppression_reason is None:
            await handler(event)
            status: Literal["PROCESSED", "SUPPRESSED"] = "PROCESSED"
        else:
            status = "SUPPRESSED"

        await idempotency.complete(
            key=idempotency_key,
            resource_type="consumer_event",
            resource_id=event.event_id,
            response_status=204,
            response_body={
                "status": status,
                "reason_code": suppression_reason,
            },
        )
        return ConsumerResult(status=status, reason_code=suppression_reason)

    async def _suppression_reason(self, event: DomainEvent) -> str | None:
        if event.event_type in REVOCATION_SAFE_EVENTS:
            return None
        if event.elder_id is not None and event.purpose is not None:
            if event.consent_version is None:
                return "SUPPRESSED_MISSING_CONSENT_VERSION"
            now = datetime.now(UTC)
            consent_id = await self._session.scalar(
                select(ConsentGrant.id).where(
                    ConsentGrant.elder_id == event.elder_id,
                    ConsentGrant.purpose_code == event.purpose,
                    ConsentGrant.status == "GRANTED",
                    ConsentGrant.version == event.consent_version,
                    ConsentGrant.effective_at <= now,
                    or_(ConsentGrant.expires_at.is_(None), now < ConsentGrant.expires_at),
                    or_(ConsentGrant.revoked_at.is_(None), now < ConsentGrant.revoked_at),
                )
            )
            if consent_id is None:
                return "SUPPRESSED_CONSENT_INACTIVE"

        if await DeletionRepository(
            self._session,
            event.tenant_id,
        ).has_tombstone(
            resource_type=event.aggregate.type,
            resource_id=event.aggregate.id,
        ):
            return "SUPPRESSED_DELETION_TOMBSTONE"

        aggregate_model = {
            "memory": Memory,
            "care_event": CareEvent,
            "family_report": FamilyReport,
        }.get(event.aggregate.type)
        if aggregate_model is None:
            return None
        aggregate_status = await self._session.scalar(
            select(aggregate_model.status).where(
                aggregate_model.id == event.aggregate.id,
                aggregate_model.tenant_id == event.tenant_id,
            )
        )
        if aggregate_status is None:
            return "SUPPRESSED_AGGREGATE_MISSING"
        if event.aggregate.type == "memory" and aggregate_status == "DELETED":
            return "SUPPRESSED_TOMBSTONED_MEMORY"
        if event.aggregate.type == "care_event" and aggregate_status == "DELETED":
            return "SUPPRESSED_TOMBSTONED_EVENT"
        if event.aggregate.type == "family_report" and aggregate_status == "WITHDRAWN":
            return "SUPPRESSED_WITHDRAWN_REPORT"
        return None

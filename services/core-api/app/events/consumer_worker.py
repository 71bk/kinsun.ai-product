"""Provider-neutral queue settlement for replay-safe event consumers."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.consumer import ConsumerResult, DomainEvent, IdempotentEventConsumer
from app.events.failures import EventConsumerFailure, EventDeliveryFailure


class QueueSettlement(Protocol):
    """Durable operations supplied by a deployment-specific queue adapter.

    ``dead_letter`` must be idempotent by event ID. The worker acknowledges the
    source only after that durable handoff succeeds.
    """

    async def acknowledge(self) -> None: ...

    async def retry(self, failure: EventDeliveryFailure, delay_seconds: float) -> None: ...

    async def dead_letter(self, failure: EventDeliveryFailure) -> None: ...


@dataclass(frozen=True)
class ConsumerDeliveryOutcome:
    status: Literal["ACKNOWLEDGED", "RETRY_SCHEDULED", "DEAD_LETTERED"]
    consumer_result: ConsumerResult | None = None
    failure: EventDeliveryFailure | None = None


class EventConsumerWorker:
    """Commit consumer effects before settling the source queue message.

    A crash between database commit and acknowledgement causes redelivery. The
    underlying IdempotentEventConsumer replays the committed event ID without
    invoking the domain handler twice.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        consumer_name: str,
        max_attempts: int = 5,
        retry_base: timedelta = timedelta(seconds=2),
        retry_max: timedelta = timedelta(minutes=5),
    ) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,47}", consumer_name):
            raise ValueError("consumer_name must be a stable lowercase identifier")
        if max_attempts < 1 or max_attempts > 100:
            raise ValueError("max_attempts must be between 1 and 100")
        if retry_base <= timedelta(0) or retry_max < retry_base:
            raise ValueError("retry delays must be positive and retry_max >= retry_base")
        self._session_factory = session_factory
        self._consumer_name = consumer_name
        self._max_attempts = max_attempts
        self._retry_base = retry_base
        self._retry_max = retry_max

    async def process(
        self,
        event: DomainEvent,
        handler: Callable[[DomainEvent], Awaitable[None]],
        settlement: QueueSettlement,
        *,
        attempt_count: int,
    ) -> ConsumerDeliveryOutcome:
        if attempt_count < 1:
            raise ValueError("attempt_count must be at least 1")

        try:
            async with self._session_factory() as session, session.begin():
                result = await IdempotentEventConsumer(
                    session,
                    self._consumer_name,
                ).process(
                    event,
                    handler,
                    attempt_count=attempt_count,
                    max_attempts=self._max_attempts,
                )
        except EventConsumerFailure as exc:
            failure = exc.failure
            if failure.disposition == "RETRY":
                await settlement.retry(
                    failure,
                    self._retry_delay(attempt_count).total_seconds(),
                )
                return ConsumerDeliveryOutcome(
                    status="RETRY_SCHEDULED",
                    failure=failure,
                )
            await settlement.dead_letter(failure)
            await settlement.acknowledge()
            return ConsumerDeliveryOutcome(
                status="DEAD_LETTERED",
                failure=failure,
            )

        await settlement.acknowledge()
        return ConsumerDeliveryOutcome(
            status="ACKNOWLEDGED",
            consumer_result=result,
        )

    def _retry_delay(self, attempt_count: int) -> timedelta:
        multiplier = 2 ** min(attempt_count - 1, 30)
        return min(self._retry_base * multiplier, self._retry_max)

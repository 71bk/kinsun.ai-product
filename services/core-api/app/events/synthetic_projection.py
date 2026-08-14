"""Development-only outbox relay for the Gate 1 synthetic projection.

This module is deliberately not a production worker.  It lets local QA drain
committed outbox records through the same publisher/consumer boundaries while
Aurora/PostgreSQL remains authoritative.  Production exits fail closed.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from uuid import UUID

from app.core.config import AppEnv, Settings, get_settings
from app.db.engine import DatabaseEngine
from app.events.consumer import DomainEvent
from app.events.graph_projection import SyntheticGraphProjectionConsumer
from app.events.publisher import EventPublisher
from app.events.relay import OutboxRelay


@dataclass(frozen=True)
class ProjectionDrainResult:
    published: int = 0
    suppressed: int = 0
    failed: int = 0
    batches: int = 0


class SyntheticProjectionPublisher(EventPublisher):
    """In-process synthetic event bus binding for local Gate 1 QA."""

    def __init__(self, session) -> None:
        self._session = session

    async def publish(
        self,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: UUID,
        payload: dict,
    ) -> None:
        event = DomainEvent.model_validate(payload)
        if (
            event.event_type != event_type
            or event.aggregate.id != aggregate_id
            or event.tenant_id != tenant_id
        ):
            raise ValueError("publisher metadata does not match the event envelope")

        # Consumer failures must not leave a partial projection/idempotency row
        # in the relay transaction.  A real queue provides this settlement
        # boundary; the in-process development adapter uses a savepoint.
        async with self._session.begin_nested():
            await SyntheticGraphProjectionConsumer(self._session).consume(event)


async def drain_synthetic_projection(
    *,
    settings: Settings | None = None,
    batch_size: int = 50,
    max_batches: int = 20,
) -> ProjectionDrainResult:
    """Drain committed outbox events into the local synthetic projection."""

    active_settings = settings or get_settings()
    if active_settings.app_env == AppEnv.PRODUCTION:
        raise RuntimeError("synthetic projection is disabled in production")
    if max_batches < 1 or max_batches > 100:
        raise ValueError("max_batches must be between 1 and 100")

    engine = DatabaseEngine(active_settings)
    try:
        if not await engine.check_connectivity():
            raise RuntimeError("database is unavailable")

        totals = ProjectionDrainResult()
        for batch_number in range(1, max_batches + 1):
            async with engine.session_factory() as session, session.begin():
                published, suppressed, failed = await OutboxRelay(
                    session,
                    SyntheticProjectionPublisher(session),
                ).relay_once(batch_size=batch_size)
            processed = published + suppressed + failed
            if processed == 0:
                return totals
            totals = ProjectionDrainResult(
                published=totals.published + published,
                suppressed=totals.suppressed + suppressed,
                failed=totals.failed + failed,
                batches=batch_number,
            )
        return totals
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drain the development outbox into the Gate 1 synthetic projection."
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--max-batches", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = asyncio.run(
        drain_synthetic_projection(
            batch_size=args.batch_size,
            max_batches=args.max_batches,
        )
    )
    print(
        "synthetic_projection "
        f"published={result.published} suppressed={result.suppressed} "
        f"failed={result.failed} batches={result.batches}"
    )


if __name__ == "__main__":
    main()

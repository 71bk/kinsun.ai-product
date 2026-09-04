"""Executable provider-neutral transactional-outbox worker."""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import timedelta
from uuid import UUID, uuid4

from app.core.config import Settings, get_settings
from app.db.engine import DatabaseEngine
from app.events.publisher import HttpsEventPublisher
from app.events.relay import OutboxRelay, RelayBatchResult, redrive_dead_letter

logger = logging.getLogger(__name__)


def _build_publisher(settings: Settings) -> HttpsEventPublisher:
    if settings.outbox_publisher_mode != "https":
        raise RuntimeError("outbox worker requires OUTBOX_PUBLISHER_MODE=https")
    return HttpsEventPublisher(
        settings.outbox_publish_url,
        settings.outbox_publish_bearer_token,
        timeout_seconds=settings.outbox_publish_timeout_seconds,
    )


async def run_outbox_worker(
    *,
    settings: Settings | None = None,
    once: bool = False,
    worker_id: str | None = None,
) -> RelayBatchResult | None:
    """Run one pass or continuously poll until the process is cancelled."""
    active_settings = settings or get_settings()
    if not active_settings.outbox_worker_enabled:
        raise RuntimeError("outbox worker is disabled; set OUTBOX_WORKER_ENABLED=true")

    engine = DatabaseEngine(active_settings)
    publisher = _build_publisher(active_settings)
    try:
        if not await engine.check_connectivity():
            raise RuntimeError("database is unavailable")
        relay = OutboxRelay(
            engine.session_factory,
            publisher,
            worker_id=worker_id or f"outbox-{uuid4().hex[:12]}",
            lease_duration=timedelta(seconds=active_settings.outbox_lease_seconds),
            retry_base=timedelta(seconds=active_settings.outbox_retry_base_seconds),
            retry_max=timedelta(seconds=active_settings.outbox_retry_max_seconds),
        )
        while True:
            result = await relay.relay_once(
                batch_size=active_settings.outbox_batch_size,
                max_attempts=active_settings.outbox_max_attempts,
            )
            if result.made_progress:
                logger.info(
                    "Outbox relay pass complete",
                    extra={
                        "claimed": result.claimed,
                        "published": result.published,
                        "suppressed": result.suppressed,
                        "retry_scheduled": result.retry_scheduled,
                        "dead_lettered": result.dead_lettered,
                        "leases_recovered": result.leases_recovered,
                    },
                )
            if once:
                return result
            if not result.made_progress:
                await asyncio.sleep(active_settings.outbox_poll_interval_seconds)
    finally:
        await publisher.aclose()
        await engine.dispose()


async def redrive_event(
    event_id: UUID,
    *,
    settings: Settings | None = None,
) -> bool:
    """Requeue one explicitly selected dead-letter event."""
    engine = DatabaseEngine(settings or get_settings())
    try:
        if not await engine.check_connectivity():
            raise RuntimeError("database is unavailable")
        return await redrive_dead_letter(engine.session_factory, event_id)
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Relay committed transactional-outbox events.")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--once", action="store_true", help="Run one bounded relay pass.")
    action.add_argument(
        "--redrive-event-id",
        type=UUID,
        help="Requeue one explicit event from the durable dead-letter state.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.redrive_event_id is not None:
        redriven = asyncio.run(redrive_event(args.redrive_event_id))
        print(f"outbox_redrive event_id={args.redrive_event_id} redriven={str(redriven).lower()}")
        return
    result = asyncio.run(run_outbox_worker(once=args.once))
    if result is not None:
        print(
            "outbox_relay "
            f"claimed={result.claimed} published={result.published} "
            f"suppressed={result.suppressed} retry_scheduled={result.retry_scheduled} "
            f"dead_lettered={result.dead_lettered} "
            f"leases_recovered={result.leases_recovered}"
        )


if __name__ == "__main__":
    main()

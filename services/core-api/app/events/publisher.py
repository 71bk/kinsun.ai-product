"""Event publisher interface and in-memory test implementation.

EventPublisher is the abstract interface for the relay's publishing contract.
FakePublisher is an in-memory implementation for testing.
"""

from abc import ABC, abstractmethod
from uuid import UUID

from app.events.failures import EventPublishError

__all__ = ["EventPublishError", "EventPublisher", "FakePublisher"]


class EventPublisher(ABC):
    """Abstract interface for the relay's publishing contract.

    The implemented relay reads committed outbox records through this
    provider-neutral port. A concrete EventBridge transport remains an
    environment binding, pending the repository's AWS/IaC owner decisions.
    """

    @abstractmethod
    async def publish(
        self,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: UUID,
        payload: dict,
    ) -> None:
        """Publish a domain event.

        Concrete adapters should raise EventPublishError with a stable
        reason_code and retryable flag for expected transport failures.
        Unexpected exceptions are classified as retryable by OutboxRelay
        without persisting their potentially sensitive messages.

        Args:
            event_type: The type/name of the domain event.
            aggregate_id: The ID of the aggregate that produced the event.
            tenant_id: The tenant context for the event.
            payload: The event payload as a dictionary.
        """
        ...


class FakePublisher(EventPublisher):
    """In-memory publisher for testing the outbox_writer behavior.

    Simulates what a relay would do — collects events for test assertions.
    Does NOT represent the API write-path (that's outbox_writer).
    """

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def publish(
        self,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: UUID,
        payload: dict,
    ) -> None:
        """Collect event in memory for test assertions."""
        self.events.append(
            {
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "tenant_id": tenant_id,
                "payload": payload,
            }
        )

    def clear(self) -> None:
        """Clear all collected events. Convenience method for tests."""
        self.events.clear()

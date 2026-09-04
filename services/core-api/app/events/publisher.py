"""Provider-neutral event publisher ports and adapters.

EventPublisher is the abstract interface for the relay's publishing contract.
FakePublisher is an in-memory implementation for testing.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.events.failures import EventPublishError

__all__ = [
    "EventPublishError",
    "EventPublisher",
    "FakePublisher",
    "HttpsEventPublisher",
]


class EventPublisher(ABC):
    """Abstract interface for the relay's publishing contract.

    The relay reads committed outbox records through this provider-neutral
    port. Hosting-specific queue bindings remain deployment decisions.
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


class HttpsEventPublisher(EventPublisher):
    """Publish strict event envelopes to a fixed authenticated HTTPS ingress.

    The event ID is also sent as ``Idempotency-Key``. Redirects are not
    followed, so a configured endpoint cannot move credentials to another
    authority at runtime.
    """

    def __init__(
        self,
        endpoint: str,
        bearer_token: str,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._endpoint = self.validate_endpoint(endpoint)
        if len(bearer_token.encode("utf-8")) < 32:
            raise ValueError("publisher bearer token must contain at least 32 bytes")
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("publisher timeout must be between 0 and 60 seconds")
        self._bearer_token = bearer_token
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    @staticmethod
    def validate_endpoint(endpoint: str) -> str:
        value = endpoint.strip()
        parsed = urlsplit(value)
        try:
            parsed_port = parsed.port
        except ValueError as exc:
            raise ValueError("publisher endpoint has an invalid port") from exc
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in value)
            or parsed_port == 0
        ):
            raise ValueError(
                "publisher endpoint must be a fixed HTTPS URL without credentials, "
                "query, or fragment"
            )
        return value

    async def publish(
        self,
        event_type: str,
        aggregate_id: UUID,
        tenant_id: UUID,
        payload: dict,
    ) -> None:
        event_id = payload.get("event_id")
        aggregate = payload.get("aggregate")
        if (
            not isinstance(event_id, str)
            or payload.get("event_type") != event_type
            or payload.get("tenant_id") != str(tenant_id)
            or not isinstance(aggregate, dict)
            or aggregate.get("id") != str(aggregate_id)
        ):
            raise EventPublishError("PUBLISHER_SCHEMA_REJECTED", retryable=False)

        try:
            response = await self._client.post(
                self._endpoint,
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._bearer_token}",
                    "Content-Type": "application/json",
                    "Idempotency-Key": event_id,
                },
            )
        except httpx.HTTPError:
            raise EventPublishError("PUBLISHER_DEPENDENCY_TIMEOUT", retryable=True) from None

        if 200 <= response.status_code < 300:
            return
        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            raise EventPublishError("PUBLISHER_DEPENDENCY_TIMEOUT", retryable=True)
        raise EventPublishError("PUBLISHER_SCHEMA_REJECTED", retryable=False)

    async def aclose(self) -> None:
        """Close the internally-created HTTP connection pool."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> HttpsEventPublisher:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()


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

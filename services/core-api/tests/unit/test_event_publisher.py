"""Unit tests for EventPublisher ABC and FakePublisher."""

import uuid

import httpx
import pytest

from app.events.failures import EventPublishError
from app.events.publisher import EventPublisher, FakePublisher, HttpsEventPublisher


class TestEventPublisherABC:
    """Tests for the EventPublisher abstract base class."""

    def test_cannot_instantiate_abc(self):
        """EventPublisher cannot be instantiated directly."""
        with pytest.raises(TypeError):
            EventPublisher()

    def test_subclass_must_implement_publish(self):
        """Subclass without publish implementation cannot be instantiated."""

        class IncompletePublisher(EventPublisher):
            pass

        with pytest.raises(TypeError):
            IncompletePublisher()

    def test_subclass_with_publish_can_be_instantiated(self):
        """Subclass that implements publish can be instantiated."""

        class ConcretePublisher(EventPublisher):
            async def publish(self, event_type, aggregate_id, tenant_id, payload):
                pass

        publisher = ConcretePublisher()
        assert isinstance(publisher, EventPublisher)


class TestFakePublisher:
    """Tests for FakePublisher in-memory implementation."""

    def test_is_event_publisher(self):
        """FakePublisher is an instance of EventPublisher."""
        publisher = FakePublisher()
        assert isinstance(publisher, EventPublisher)

    def test_starts_with_empty_events(self):
        """FakePublisher starts with no collected events."""
        publisher = FakePublisher()
        assert publisher.events == []

    @pytest.mark.asyncio
    async def test_publish_collects_event(self):
        """publish() appends event dict to events list."""
        publisher = FakePublisher()
        aggregate_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        payload = {"key": "value"}

        await publisher.publish(
            event_type="elder.created",
            aggregate_id=aggregate_id,
            tenant_id=tenant_id,
            payload=payload,
        )

        assert len(publisher.events) == 1
        event = publisher.events[0]
        assert event["event_type"] == "elder.created"
        assert event["aggregate_id"] == aggregate_id
        assert event["tenant_id"] == tenant_id
        assert event["payload"] == payload

    @pytest.mark.asyncio
    async def test_publish_multiple_events(self):
        """Multiple publish calls accumulate events in order."""
        publisher = FakePublisher()
        tenant_id = uuid.uuid4()

        for i in range(3):
            await publisher.publish(
                event_type=f"event.{i}",
                aggregate_id=uuid.uuid4(),
                tenant_id=tenant_id,
                payload={"index": i},
            )

        assert len(publisher.events) == 3
        for i, event in enumerate(publisher.events):
            assert event["event_type"] == f"event.{i}"
            assert event["payload"] == {"index": i}

    def test_clear_removes_all_events(self):
        """clear() empties the events list."""
        publisher = FakePublisher()
        publisher.events.append(
            {
                "event_type": "test",
                "aggregate_id": uuid.uuid4(),
                "tenant_id": uuid.uuid4(),
                "payload": {},
            }
        )
        assert len(publisher.events) == 1

        publisher.clear()
        assert publisher.events == []

    @pytest.mark.asyncio
    async def test_clear_after_publish(self):
        """clear() after publish resets to empty state."""
        publisher = FakePublisher()
        await publisher.publish(
            event_type="test.event",
            aggregate_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            payload={"data": True},
        )
        assert len(publisher.events) == 1

        publisher.clear()
        assert publisher.events == []

    @pytest.mark.asyncio
    async def test_publish_after_clear(self):
        """Publishing after clear starts fresh."""
        publisher = FakePublisher()
        await publisher.publish(
            event_type="first",
            aggregate_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            payload={},
        )
        publisher.clear()

        aggregate_id = uuid.uuid4()
        await publisher.publish(
            event_type="second",
            aggregate_id=aggregate_id,
            tenant_id=uuid.uuid4(),
            payload={"after_clear": True},
        )

        assert len(publisher.events) == 1
        assert publisher.events[0]["event_type"] == "second"
        assert publisher.events[0]["aggregate_id"] == aggregate_id


def _envelope(*, event_id: uuid.UUID, aggregate_id: uuid.UUID, tenant_id: uuid.UUID) -> dict:
    return {
        "event_id": str(event_id),
        "event_type": "memory.confirmed.v1",
        "tenant_id": str(tenant_id),
        "aggregate": {"id": str(aggregate_id)},
    }


class TestHttpsEventPublisher:
    @pytest.mark.asyncio
    async def test_posts_envelope_with_event_idempotency_key(self) -> None:
        event_id = uuid.uuid4()
        aggregate_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        seen_request: httpx.Request | None = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_request
            seen_request = request
            return httpx.Response(202)

        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        publisher = HttpsEventPublisher(
            "https://events.example.test/ingress",
            "a" * 32,
            client=client,
        )

        await publisher.publish(
            "memory.confirmed.v1",
            aggregate_id,
            tenant_id,
            _envelope(event_id=event_id, aggregate_id=aggregate_id, tenant_id=tenant_id),
        )

        assert seen_request is not None
        assert seen_request.headers["Idempotency-Key"] == str(event_id)
        assert seen_request.headers["Authorization"] == f"Bearer {'a' * 32}"
        await client.aclose()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [408, 425, 429, 500, 503])
    async def test_retryable_status_is_classified_without_response_body(
        self,
        status_code: int,
    ) -> None:
        aggregate_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        event_id = uuid.uuid4()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(status_code))
        )
        publisher = HttpsEventPublisher(
            "https://events.example.test/ingress",
            "b" * 32,
            client=client,
        )

        with pytest.raises(EventPublishError) as exc_info:
            await publisher.publish(
                "memory.confirmed.v1",
                aggregate_id,
                tenant_id,
                _envelope(event_id=event_id, aggregate_id=aggregate_id, tenant_id=tenant_id),
            )

        assert exc_info.value.reason_code == "PUBLISHER_DEPENDENCY_TIMEOUT"
        assert exc_info.value.retryable is True
        await client.aclose()

    @pytest.mark.asyncio
    async def test_schema_rejection_is_not_retryable(self) -> None:
        aggregate_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        event_id = uuid.uuid4()
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(422))
        )
        publisher = HttpsEventPublisher(
            "https://events.example.test/ingress",
            "c" * 32,
            client=client,
        )

        with pytest.raises(EventPublishError) as exc_info:
            await publisher.publish(
                "memory.confirmed.v1",
                aggregate_id,
                tenant_id,
                _envelope(event_id=event_id, aggregate_id=aggregate_id, tenant_id=tenant_id),
            )

        assert exc_info.value.reason_code == "PUBLISHER_SCHEMA_REJECTED"
        assert exc_info.value.retryable is False
        await client.aclose()

    @pytest.mark.parametrize(
        "endpoint",
        [
            "http://events.example.test/ingress",
            "https://user:pass@events.example.test/ingress",
            "https://events.example.test/ingress?target=other",
            "https://events.example.test/ingress#fragment",
        ],
    )
    def test_rejects_unsafe_endpoint(self, endpoint: str) -> None:
        with pytest.raises(ValueError):
            HttpsEventPublisher(endpoint, "d" * 32)

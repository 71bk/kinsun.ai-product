"""Unit tests for EventPublisher ABC and FakePublisher."""

import uuid

import pytest

from app.events.publisher import EventPublisher, FakePublisher


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

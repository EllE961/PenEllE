"""Tests for event bus implementation."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import redis.asyncio as redis

from src.core.events.bus import (
    Event,
    EventBus,
    EventHandler,
    HandlerError,
    event_handler,
    get_event_bus,
)


class TestEvent:
    """Test Event class."""

    def test_event_creation(self):
        """Test creating an event."""
        payload = {"key": "value"}
        event = Event("test.event", payload)

        assert event.type == "test.event"
        assert event.payload == payload
        assert event.id is not None
        assert isinstance(event.timestamp, datetime)

    def test_event_with_custom_id(self):
        """Test creating event with custom ID."""
        event_id = "custom-123"
        event = Event("test.event", {}, event_id=event_id)

        assert event.id == event_id

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        payload = {"data": "test"}
        event = Event("test.event", payload)

        event_dict = event.to_dict()

        assert event_dict["id"] == event.id
        assert event_dict["type"] == "test.event"
        assert event_dict["payload"] == payload
        assert "timestamp" in event_dict

    def test_event_from_dict(self):
        """Test creating event from dictionary."""
        event_dict = {
            "id": "test-123",
            "type": "test.event",
            "timestamp": datetime.utcnow().isoformat(),
            "payload": {"key": "value"},
        }

        event = Event.from_dict(event_dict)

        assert event.id == "test-123"
        assert event.type == "test.event"
        assert event.payload == {"key": "value"}


class TestEventHandler:
    """Test EventHandler class."""

    @pytest.mark.asyncio()
    async def test_handler_creation(self):
        """Test creating an event handler."""

        async def test_handler(event):
            return "handled"

        handler = EventHandler(
            handler_id="test-handler",
            handler=test_handler,
            event_types={"test.event"},
            max_retries=3,
        )

        assert handler.id == "test-handler"
        assert handler.event_types == {"test.event"}
        assert handler.max_retries == 3
        assert handler.is_active is True

    @pytest.mark.asyncio()
    async def test_handler_execution(self):
        """Test handler execution."""
        result = None

        async def test_handler(event):
            nonlocal result
            result = event.payload["value"]
            return result

        handler = EventHandler(handler_id="test", handler=test_handler, event_types={"test.event"})

        event = Event("test.event", {"value": "test-data"})
        await handler.handle(event)

        assert result == "test-data"

    @pytest.mark.asyncio()
    async def test_handler_retry_logic(self):
        """Test handler retry on failure."""
        attempt_count = 0

        async def failing_handler(event):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Test error")
            return "success"

        handler = EventHandler(
            handler_id="test",
            handler=failing_handler,
            event_types={"test.event"},
            max_retries=3,
            retry_delay=0.01,
        )

        event = Event("test.event", {})
        result = await handler.handle(event)

        assert attempt_count == 3
        assert result == "success"

    @pytest.mark.asyncio()
    async def test_handler_max_retries_exceeded(self):
        """Test handler fails after max retries."""

        async def always_failing_handler(event):
            raise ValueError("Always fails")

        handler = EventHandler(
            handler_id="test",
            handler=always_failing_handler,
            event_types={"test.event"},
            max_retries=2,
            retry_delay=0.01,
        )

        event = Event("test.event", {})

        with pytest.raises(HandlerError):
            await handler.handle(event)


class TestEventBus:
    """Test EventBus class."""

    @pytest.fixture()
    def mock_redis(self):
        """Create mock Redis client."""
        mock = AsyncMock(spec=redis.Redis)
        mock.xadd = AsyncMock(return_value="123-0")
        mock.xgroup_create = AsyncMock()
        mock.xreadgroup = AsyncMock(return_value=[])
        mock.xack = AsyncMock()
        mock.xrange = AsyncMock(return_value=[])
        mock.xinfo_stream = AsyncMock(
            return_value={
                "length": 100,
                "first-entry": ("123-0", {"event": "{}"}),
                "last-entry": ("456-0", {"event": "{}"}),
                "groups": 1,
            }
        )
        return mock

    @pytest.fixture()
    def event_bus(self, mock_redis):
        """Create EventBus instance with mock Redis."""
        return EventBus(redis_client=mock_redis)

    @pytest.mark.asyncio()
    async def test_event_bus_connect(self, mock_redis):
        """Test connecting to Redis."""
        bus = EventBus(redis_client=mock_redis)
        await bus.connect()

        # Should create consumer group
        mock_redis.xgroup_create.assert_called_once()

    @pytest.mark.asyncio()
    async def test_event_bus_publish(self, event_bus, mock_redis):
        """Test publishing an event."""
        event = Event("test.event", {"data": "test"})

        stream_id = await event_bus.publish(event)

        assert stream_id == "123-0"
        mock_redis.xadd.assert_called_once()

        # Check the call arguments
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == event_bus.stream_key
        assert "event" in call_args[0][1]

    def test_event_bus_subscribe(self, event_bus):
        """Test subscribing a handler."""

        async def test_handler(event):
            pass

        handler_id = event_bus.subscribe(event_types=["test.event"], handler=test_handler)

        assert handler_id in event_bus._handlers
        assert "test.event" in event_bus._handlers[handler_id].event_types

    def test_event_bus_unsubscribe(self, event_bus):
        """Test unsubscribing a handler."""

        async def test_handler(event):
            pass

        handler_id = event_bus.subscribe("test.event", test_handler)

        # Unsubscribe
        result = event_bus.unsubscribe(handler_id)
        assert result is True
        assert handler_id not in event_bus._handlers

        # Unsubscribe non-existent handler
        result = event_bus.unsubscribe("non-existent")
        assert result is False

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Redis not available in test environment")
    async def test_event_bus_start_stop(self, event_bus):
        """Test starting and stopping the event bus."""
        await event_bus.start()
        assert event_bus._running is True
        assert len(event_bus._tasks) > 0

        await event_bus.stop()
        assert event_bus._running is False
        assert len(event_bus._tasks) == 0

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Redis not available in test environment")
    async def test_event_bus_consume_and_process(self, event_bus, mock_redis):
        """Test consuming and processing events."""
        # Set up handler
        processed_events = []

        async def test_handler(event):
            processed_events.append(event.payload)

        event_bus.subscribe("test.event", test_handler)

        # Mock Redis response
        event_data = json.dumps(
            {
                "id": "test-123",
                "type": "test.event",
                "timestamp": datetime.utcnow().isoformat(),
                "payload": {"data": "test"},
            }
        )

        mock_redis.xreadgroup.return_value = [("stream", [("123-0", {"event": event_data})])]

        # Process one iteration
        await event_bus._consume_events()

        # Give handlers time to process
        await asyncio.sleep(0.1)

        # Check handler was called
        assert len(processed_events) == 1
        assert processed_events[0]["data"] == "test"

        # Check message was acknowledged
        mock_redis.xack.assert_called_once()

    @pytest.mark.asyncio()
    async def test_event_bus_replay_events(self, event_bus, mock_redis):
        """Test replaying events from timestamp."""
        replayed_events = []

        def replay_handler(event):
            replayed_events.append(event)

        # Mock Redis response
        event_data1 = json.dumps(
            {
                "id": "test-1",
                "type": "test.event",
                "timestamp": datetime.utcnow().isoformat(),
                "payload": {"num": 1},
            }
        )

        event_data2 = json.dumps(
            {
                "id": "test-2",
                "type": "other.event",
                "timestamp": datetime.utcnow().isoformat(),
                "payload": {"num": 2},
            }
        )

        mock_redis.xrange.return_value = [
            ("123-0", {"event": event_data1}),
            ("124-0", {"event": event_data2}),
        ]

        # Replay only test.event type
        from_time = datetime.utcnow() - timedelta(hours=1)
        count = await event_bus.replay_events(
            from_timestamp=from_time, event_types=["test.event"], handler=replay_handler
        )

        assert count == 1
        assert len(replayed_events) == 1
        assert replayed_events[0].payload["num"] == 1

    @pytest.mark.asyncio()
    async def test_event_bus_get_stats(self, event_bus, mock_redis):
        """Test getting event stream statistics."""
        stats = await event_bus.get_event_stats()

        assert stats["length"] == 100
        assert stats["consumer_groups"] == 1
        assert stats["max_length"] == event_bus.max_stream_length

        mock_redis.xinfo_stream.assert_called_once_with(event_bus.stream_key)


class TestEventHandlerDecorator:
    """Test event_handler decorator."""

    def test_event_handler_decorator(self):
        """Test using event_handler decorator."""
        handled_events = []

        @event_handler("test.event", handler_id="test-decorated")
        async def my_handler(event):
            handled_events.append(event)

        # First call should register the handler
        asyncio.run(my_handler(Event("test", {})))

        # Check handler was registered
        bus = get_event_bus()
        assert "test-decorated" in bus._handlers


class TestGlobalInstance:
    """Test global event bus instance."""

    def test_get_event_bus_singleton(self):
        """Test get_event_bus returns singleton."""
        bus1 = get_event_bus()
        bus2 = get_event_bus()

        assert bus1 is bus2

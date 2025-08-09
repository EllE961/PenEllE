"""Tests for base event handler."""

from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from src.core.events import BaseEvent, EventType
from src.core.events.handlers.base import BaseEventHandler


class ConcreteEventHandler(BaseEventHandler):
    """Concrete implementation for testing."""

    def __init__(self, event_types):
        super().__init__(event_types)
        self.initialize_called = False
        self.shutdown_called = False
        self.handle_called = False
        self.handled_events = []

    async def _initialize(self):
        self.initialize_called = True

    async def _shutdown(self):
        self.shutdown_called = True

    async def handle(self, event):
        self.handle_called = True
        self.handled_events.append(event)
        return {"handled": event.type}


class TestBaseEventHandler:
    """Test cases for BaseEventHandler."""

    @pytest.fixture()
    def handler(self):
        """Create a concrete handler instance."""
        return ConcreteEventHandler({EventType.RUN_STARTED, EventType.RUN_COMPLETED})

    @pytest.fixture()
    def run_started_event(self):
        """Create a run started event."""
        return BaseEvent(
            id=str(uuid4()),
            type=EventType.RUN_STARTED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            metadata={"status": "starting"},
        )

    @pytest.fixture()
    def run_failed_event(self):
        """Create a run failed event."""
        return BaseEvent(
            id=str(uuid4()),
            type=EventType.RUN_FAILED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            metadata={"error": "test error"},
        )

    @pytest.mark.asyncio()
    async def test_initialization(self, handler):
        """Test handler initialization."""
        assert not handler._initialized
        assert not handler.initialize_called

        await handler.initialize()

        assert handler._initialized
        assert handler.initialize_called

        # Test idempotency
        handler.initialize_called = False
        await handler.initialize()
        assert not handler.initialize_called  # Should not be called again

    @pytest.mark.asyncio()
    async def test_shutdown(self, handler):
        """Test handler shutdown."""
        # Initialize first
        await handler.initialize()
        assert handler._initialized

        await handler.shutdown()

        assert not handler._initialized
        assert handler.shutdown_called

        # Test idempotency
        handler.shutdown_called = False
        await handler.shutdown()
        assert not handler.shutdown_called  # Should not be called again

    def test_should_handle(self, handler, run_started_event, run_failed_event):
        """Test event type filtering."""
        # Should handle registered event types
        assert handler.should_handle(run_started_event)

        # Should not handle unregistered event types
        assert not handler.should_handle(run_failed_event)

    @pytest.mark.asyncio()
    async def test_handle(self, handler, run_started_event):
        """Test event handling."""
        result = await handler.handle(run_started_event)

        assert handler.handle_called
        assert len(handler.handled_events) == 1
        assert handler.handled_events[0] == run_started_event
        assert result == {"handled": "run.started"}

    def test_event_types_property(self, handler):
        """Test event types property."""
        assert EventType.RUN_STARTED in handler.event_types
        assert EventType.RUN_COMPLETED in handler.event_types
        assert EventType.RUN_FAILED not in handler.event_types

    @pytest.mark.asyncio()
    async def test_multiple_handlers(self):
        """Test multiple handler instances."""
        handler1 = ConcreteEventHandler({EventType.RUN_STARTED})
        handler2 = ConcreteEventHandler({EventType.RUN_COMPLETED})

        event1 = BaseEvent(
            id=str(uuid4()),
            type=EventType.RUN_STARTED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            metadata={},
        )

        event2 = BaseEvent(
            id=str(uuid4()),
            type=EventType.RUN_COMPLETED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            metadata={},
        )

        # Handler 1 should only handle RUN_STARTED
        assert handler1.should_handle(event1)
        assert not handler1.should_handle(event2)

        # Handler 2 should only handle RUN_COMPLETED
        assert not handler2.should_handle(event1)
        assert handler2.should_handle(event2)

    @pytest.mark.asyncio()
    async def test_error_handling_in_subclass(self):
        """Test error handling in subclass implementation."""

        class ErrorHandler(BaseEventHandler):
            async def _initialize(self):
                raise RuntimeError("Init error")

            async def _shutdown(self):
                raise RuntimeError("Shutdown error")

            async def handle(self, event):
                raise RuntimeError("Handle error")

        handler = ErrorHandler({EventType.ERROR_OCCURRED})

        # Errors should propagate
        with pytest.raises(RuntimeError, match="Init error"):
            await handler.initialize()

        # Force initialization for shutdown test
        handler._initialized = True
        with pytest.raises(RuntimeError, match="Shutdown error"):
            await handler.shutdown()

        with pytest.raises(RuntimeError, match="Handle error"):
            await handler.handle(Mock())

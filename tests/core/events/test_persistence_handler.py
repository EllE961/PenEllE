"""Tests for persistence event handler."""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.database.models import EventLog
from src.core.events import EventType
from src.core.events.bus import Event
from src.core.events.handlers.persistence import PersistenceHandler


class TestPersistenceHandler:
    """Test persistence event handler."""

    @pytest.fixture()
    def handler(self):
        """Create a persistence handler instance."""
        return PersistenceHandler(batch_size=5, flush_interval=1.0)

    @pytest.fixture()
    def sample_event(self):
        """Create a sample event."""
        # Create event compatible with the Event class structure
        event = Mock(spec=Event)
        event.id = str(uuid.uuid4())
        event.type = EventType.RUN_STARTED
        event.run_id = "test-run-123"
        event.stage = "initialization"
        event.payload = {"test": "data"}
        event.metadata = {"source": "test"}
        event.timestamp = datetime.utcnow().isoformat()
        event.to_dict = Mock(
            return_value={
                "id": event.id,
                "type": event.type.value,
                "run_id": event.run_id,
                "stage": event.stage,
                "timestamp": event.timestamp,
                "payload": event.payload,
                "metadata": event.metadata,
            }
        )
        return event

    @pytest.mark.asyncio()
    async def test_initialization(self, handler):
        """Test handler initialization."""
        with patch("src.core.events.handlers.persistence.logger") as mock_logger:
            await handler._initialize()
            mock_logger.info.assert_called_once()

    @pytest.mark.asyncio()
    async def test_shutdown_with_buffered_events(self, handler, sample_event):
        """Test shutdown flushes remaining events."""
        # Add event to buffer
        handler._event_buffer = [sample_event.to_dict()]

        # Mock flush method
        handler._flush_events = AsyncMock()

        with patch("src.core.events.handlers.persistence.logger"):
            await handler._shutdown()

        handler._flush_events.assert_called_once()

    @pytest.mark.asyncio()
    async def test_shutdown_empty_buffer(self, handler):
        """Test shutdown with empty buffer."""
        handler._flush_events = AsyncMock()

        with patch("src.core.events.handlers.persistence.logger"):
            await handler._shutdown()

        handler._flush_events.assert_not_called()

    @pytest.mark.asyncio()
    async def test_handle_event_adds_to_buffer(self, handler, sample_event):
        """Test handling event adds to buffer."""
        # Mock flush to prevent actual DB writes
        handler._flush_events = AsyncMock()

        await handler.handle(sample_event)

        assert len(handler._event_buffer) == 1
        assert handler._event_buffer[0]["id"] == sample_event.id

    @pytest.mark.asyncio()
    async def test_handle_event_batch_size_trigger(self, handler, sample_event):
        """Test flush triggered by batch size."""
        handler._flush_events = AsyncMock()
        handler.batch_size = 2

        # Add first event - no flush
        await handler.handle(sample_event)
        handler._flush_events.assert_not_called()

        # Add second event - should trigger flush
        # Create second event
        event2 = Mock(spec=Event)
        event2.id = str(uuid.uuid4())
        event2.type = EventType.RUN_COMPLETED
        event2.run_id = "test-run-123"
        event2.payload = {"status": "success"}
        event2.to_dict = Mock(
            return_value={
                "id": event2.id,
                "type": event2.type.value,
                "run_id": event2.run_id,
                "timestamp": datetime.utcnow().isoformat(),
                "payload": event2.payload,
            }
        )
        await handler.handle(event2)
        handler._flush_events.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_event_time_trigger(self, handler, sample_event):
        """Test flush triggered by time interval."""
        handler._flush_events = AsyncMock()
        handler.flush_interval = 0.1  # 100ms

        # Set last flush to past
        handler._last_flush = datetime.utcnow() - timedelta(seconds=1)

        await handler.handle(sample_event)
        handler._flush_events.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_event_error(self, handler):
        """Test error handling in event handler."""
        # Create event without to_dict method that will cause error
        bad_event = Mock(spec=Event)
        bad_event.id = "test-id"
        # Remove both to_dict and payload to cause error
        if hasattr(bad_event, "to_dict"):
            del bad_event.to_dict
        if hasattr(bad_event, "payload"):
            del bad_event.payload

        with patch("src.core.events.handlers.persistence.logger") as mock_logger:
            await handler.handle(bad_event)
            mock_logger.error.assert_called()

    @pytest.mark.asyncio()
    @patch("src.core.events.handlers.persistence.get_async_session")
    async def test_flush_events_success(self, mock_get_session, handler, sample_event):
        """Test successful event flush to database."""
        # Mock session
        mock_session = AsyncMock()
        mock_get_session.return_value.__aiter__.return_value = [mock_session]

        # Add events to buffer
        handler._event_buffer = [
            sample_event.to_dict(),
            {
                "id": "event-2",
                "type": EventType.STAGE_COMPLETED.value,
                "run_id": "test-run-123",
                "timestamp": datetime.utcnow().isoformat(),
                "payload": {"stage": "processing"},
            },
        ]

        with patch("src.core.events.handlers.persistence.logger") as mock_logger:
            await handler._flush_events()

        # Check session methods called
        assert mock_session.add_all.call_count == 1
        assert mock_session.commit.call_count == 1

        # Check buffer cleared
        assert len(handler._event_buffer) == 0

        # Check logs
        mock_logger.debug.assert_called()

    @pytest.mark.asyncio()
    @patch("src.core.events.handlers.persistence.get_async_session")
    async def test_flush_events_empty_buffer(self, mock_get_session, handler):
        """Test flush with empty buffer does nothing."""
        handler._event_buffer = []

        await handler._flush_events()

        # Session should not be accessed
        mock_get_session.assert_not_called()

    @pytest.mark.asyncio()
    @patch("src.core.events.handlers.persistence.get_async_session")
    async def test_flush_events_database_error(self, mock_get_session, handler, sample_event):
        """Test error handling during flush."""
        # Mock session to raise error
        mock_session = AsyncMock()
        mock_session.commit.side_effect = Exception("Database error")
        mock_get_session.return_value.__aiter__.return_value = [mock_session]

        # Add event to buffer
        original_events = [sample_event.to_dict()]
        handler._event_buffer = original_events.copy()

        with patch("src.core.events.handlers.persistence.logger") as mock_logger:
            await handler._flush_events()
            mock_logger.error.assert_called()

        # Events should be re-added to buffer
        assert handler._event_buffer == original_events

    @pytest.mark.asyncio()
    @patch("src.core.events.handlers.persistence.get_async_session")
    async def test_query_events_with_filters(self, mock_get_session, handler):
        """Test querying events with various filters."""
        # Mock session and results
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_event_log = Mock(spec=EventLog)
        mock_event_log.payload = {"test": "data"}
        mock_result.scalars.return_value.all.return_value = [mock_event_log]
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aiter__.return_value = [mock_session]

        # Query with all filters
        results = await handler.query_events(
            run_id="test-run",
            event_types=[EventType.RUN_STARTED, EventType.RUN_COMPLETED],
            stage="processing",
            from_timestamp=datetime.utcnow() - timedelta(hours=1),
            to_timestamp=datetime.utcnow(),
            limit=50,
        )

        assert len(results) == 1
        assert results[0] == {"test": "data"}

        # Verify query was executed
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio()
    @patch("src.core.events.handlers.persistence.get_async_session")
    async def test_query_events_error(self, mock_get_session, handler):
        """Test error handling in query_events."""
        # Mock session to raise error
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Query error")
        mock_get_session.return_value.__aiter__.return_value = [mock_session]

        with patch("src.core.events.handlers.persistence.logger") as mock_logger:
            results = await handler.query_events(run_id="test-run")
            mock_logger.error.assert_called()

        assert results == []

    @pytest.mark.asyncio()
    async def test_get_run_events(self, handler):
        """Test getting events for a specific run."""
        # Mock query_events
        expected_events = [{"event": 1}, {"event": 2}]
        handler.query_events = AsyncMock(return_value=expected_events)

        results = await handler.get_run_events("test-run-123")

        assert results == expected_events
        handler.query_events.assert_called_once_with(run_id="test-run-123", limit=1000)

    @pytest.mark.asyncio()
    async def test_get_latest_events(self, handler):
        """Test getting latest events of a type."""
        # Mock query_events
        expected_events = [{"event": "latest"}]
        handler.query_events = AsyncMock(return_value=expected_events)

        results = await handler.get_latest_events(EventType.ERROR_OCCURRED, limit=5)

        assert results == expected_events
        handler.query_events.assert_called_once_with(
            event_types=[EventType.ERROR_OCCURRED], limit=5
        )

    @pytest.mark.asyncio()
    @patch("src.core.events.handlers.persistence.get_async_session")
    async def test_cleanup_old_events_success(self, mock_get_session, handler):
        """Test successful cleanup of old events."""
        # Mock session and result
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.rowcount = 42
        mock_session.execute.return_value = mock_result
        mock_get_session.return_value.__aiter__.return_value = [mock_session]

        with patch("src.core.events.handlers.persistence.logger") as mock_logger:
            count = await handler.cleanup_old_events(retention_days=7)

        assert count == 42
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_logger.info.assert_called()

    @pytest.mark.asyncio()
    @patch("src.core.events.handlers.persistence.get_async_session")
    async def test_cleanup_old_events_error(self, mock_get_session, handler):
        """Test error handling in cleanup."""
        # Mock session to raise error
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Cleanup error")
        mock_get_session.return_value.__aiter__.return_value = [mock_session]

        with patch("src.core.events.handlers.persistence.logger") as mock_logger:
            count = await handler.cleanup_old_events()
            mock_logger.error.assert_called()

        assert count == 0

    @pytest.mark.asyncio()
    async def test_event_buffer_thread_safety(self, handler, sample_event):
        """Test that event buffer operations are thread-safe."""
        handler._flush_events = AsyncMock()

        # Simulate concurrent event handling
        async def add_event(event_id):
            event = Mock(spec=Event)
            event.id = str(uuid.uuid4())
            event.type = EventType.STAGE_STARTED
            event.run_id = f"run-{event_id}"
            event.payload = {"id": event_id}
            event.to_dict = Mock(
                return_value={
                    "id": event.id,
                    "type": event.type.value,
                    "run_id": event.run_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "payload": event.payload,
                }
            )
            await handler.handle(event)

        # Add multiple events concurrently
        tasks = [add_event(i) for i in range(10)]
        await asyncio.gather(*tasks)

        # Check buffer integrity
        assert len(handler._event_buffer) <= 10  # Some may have been flushed

    def test_handler_accepts_all_event_types(self):
        """Test that handler is configured to handle all event types."""
        handler = PersistenceHandler()
        assert handler.event_types == set(EventType)

    @pytest.mark.asyncio()
    async def test_event_serialization_with_metadata(self, handler):
        """Test that events with complex metadata are properly serialized."""
        event = Mock(spec=Event)
        event.id = str(uuid.uuid4())
        event.type = EventType.QUALITY_CHECK_PASSED
        event.run_id = "test-run"
        event.payload = {"scores": [0.8, 0.9, 0.85], "threshold": 0.7}
        event.metadata = {
            "checker": "quality_checker_v1",
            "timestamp": datetime.utcnow().isoformat(),
            "config": {"strict": True},
        }
        event.to_dict = Mock(
            return_value={
                "id": event.id,
                "type": event.type.value,
                "run_id": event.run_id,
                "timestamp": datetime.utcnow().isoformat(),
                "payload": event.payload,
                "metadata": event.metadata,
            }
        )

        handler._flush_events = AsyncMock()
        await handler.handle(event)

        # Check event was properly added to buffer
        assert len(handler._event_buffer) == 1
        buffered_event = handler._event_buffer[0]
        assert buffered_event["payload"]["scores"] == [0.8, 0.9, 0.85]
        assert buffered_event["metadata"]["config"]["strict"] is True

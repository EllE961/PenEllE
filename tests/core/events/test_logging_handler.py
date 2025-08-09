"""Tests for logging event handler."""

import logging
from datetime import datetime
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from src.core.events import (
    ErrorEvent,
    EventType,
    RunCompletedEvent,
    RunStartedEvent,
)
from src.core.events.handlers.logging import LoggingHandler


class TestLoggingHandler:
    """Test cases for LoggingHandler."""

    @pytest.fixture()
    def handler(self):
        """Create a logging handler instance."""
        return LoggingHandler(log_level="INFO")

    @pytest.fixture()
    def run_started_event(self):
        """Create a run started event."""
        return RunStartedEvent(
            id=str(uuid4()),
            type=EventType.RUN_STARTED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            topic="Test Topic",
            user_id=str(uuid4()),
            request_id=str(uuid4()),
            config={"test": "param"},
        )

    @pytest.fixture()
    def run_completed_event(self):
        """Create a run completed event."""
        return RunCompletedEvent(
            id=str(uuid4()),
            type=EventType.RUN_COMPLETED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            duration_seconds=10.5,
            total_stages=5,
            output_formats=["pdf", "docx"],
            output_paths={"pdf": "/path/to/pdf"},
            metrics={"total_claims": 10},
        )

    @pytest.fixture()
    def error_event(self):
        """Create an error event."""
        return ErrorEvent(
            id=str(uuid4()),
            type=EventType.ERROR_OCCURRED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            error_message="Test error",
            error_type="TestError",
            severity="high",
            context={"component": "test"},
        )

    def test_initialization(self, handler):
        """Test handler initialization."""
        assert handler.log_level == "INFO"
        assert handler.event_types == set(EventType)  # Should handle all event types

    @pytest.mark.asyncio()
    async def test_initialize_logs(self, handler):
        """Test initialization logging."""
        with patch("src.core.events.handlers.logging.logger") as mock_logger:
            await handler.initialize()
            mock_logger.info.assert_called_once_with(
                "Logging handler initialized", extra={"log_level": "INFO"}
            )

    @pytest.mark.asyncio()
    async def test_shutdown_logs(self, handler):
        """Test shutdown logging."""
        await handler.initialize()
        with patch("src.core.events.handlers.logging.logger") as mock_logger:
            await handler.shutdown()
            mock_logger.info.assert_called_once_with("Logging handler shutdown")

    @pytest.mark.asyncio()
    async def test_handle_run_started(self, handler, run_started_event):
        """Test handling run started event."""
        with patch("src.core.events.handlers.logging.logger") as mock_logger:
            # Create a mock event with to_dict method
            mock_event = Mock()
            mock_event.id = run_started_event.id
            mock_event.to_dict.return_value = run_started_event.__dict__

            await handler.handle(mock_event)

            # Verify log was called with correct level and data
            mock_logger.log.assert_called_once()
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == logging.INFO
            assert "Event: run.started" in call_args[0][1]

            # Check extra data
            extra = call_args[1]["extra"]
            assert extra["event_id"] == run_started_event.id
            assert extra["event_type"] == EventType.RUN_STARTED
            assert extra["topic"] == "Test Topic"

    @pytest.mark.asyncio()
    async def test_handle_run_completed(self, handler, run_completed_event):
        """Test handling run completed event."""
        with patch("src.core.events.handlers.logging.logger") as mock_logger:
            mock_event = Mock()
            mock_event.id = run_completed_event.id
            mock_event.to_dict.return_value = run_completed_event.__dict__

            await handler.handle(mock_event)

            call_args = mock_logger.log.call_args
            extra = call_args[1]["extra"]
            assert extra["duration_seconds"] == 10.5
            assert extra["total_stages"] == 5
            assert extra["output_formats"] == ["pdf", "docx"]
            assert extra["metrics"] == {"total_claims": 10}

    @pytest.mark.asyncio()
    async def test_handle_error_event(self, handler, error_event):
        """Test handling error event."""
        with patch("src.core.events.handlers.logging.logger") as mock_logger:
            mock_event = Mock()
            mock_event.id = error_event.id
            mock_event.to_dict.return_value = error_event.__dict__

            await handler.handle(mock_event)

            # Error events should be logged at ERROR level
            call_args = mock_logger.log.call_args
            assert call_args[0][0] == logging.ERROR

            extra = call_args[1]["extra"]
            assert extra["error_message"] == "Test error"
            assert extra["error_type"] == "TestError"
            assert extra["severity"] == "high"

    @pytest.mark.asyncio()
    async def test_handle_exception(self, handler):
        """Test exception handling during event processing."""
        with patch("src.core.events.handlers.logging.logger") as mock_logger:
            # Create event that will cause exception
            bad_event = Mock()
            bad_event.id = "bad-id"
            bad_event.to_dict.side_effect = Exception("Processing error")

            await handler.handle(bad_event)

            # Should log the error
            mock_logger.error.assert_called_once()
            error_msg = mock_logger.error.call_args[0][0]
            assert "Failed to log event bad-id" in error_msg
            assert "Processing error" in error_msg

    def test_get_log_level(self, handler):
        """Test log level determination."""
        # Create mock events with different types
        error_event = Mock(type=EventType.RUN_FAILED)
        warning_event = Mock(type=EventType.QUALITY_CHECK_FAILED)
        debug_event = Mock(type=EventType.CACHE_HIT)
        info_event = Mock(type=EventType.RUN_STARTED)

        assert handler._get_log_level(error_event) == logging.ERROR
        assert handler._get_log_level(warning_event) == logging.WARNING
        assert handler._get_log_level(debug_event) == logging.DEBUG
        assert handler._get_log_level(info_event) == logging.INFO

    def test_build_log_entry_with_metadata(self, handler):
        """Test building log entry with metadata."""
        event = Mock(
            id="test-id",
            type=EventType.RUN_STARTED,
            timestamp=datetime.utcnow(),
            run_id="run-123",
            topic="Test",
            user_id="user-123",
            request_id="req-123",
            metadata={"custom": "data"},
        )

        log_entry = handler._build_log_entry(event)

        assert log_entry["event_id"] == "test-id"
        assert log_entry["metadata"] == {"custom": "data"}

    def test_build_log_entry_stage_event(self, handler):
        """Test building log entry for stage event."""
        event = Mock(
            id="test-id",
            type=EventType.STAGE_COMPLETED,
            timestamp=datetime.utcnow(),
            run_id="run-123",
            stage="drafting",
            duration_seconds=5.0,
            outputs=["output1"],
            metrics={"items": 10},
        )

        log_entry = handler._build_log_entry(event)

        assert log_entry["stage"] == "drafting"
        assert log_entry["duration_seconds"] == 5.0
        assert log_entry["outputs"] == ["output1"]

    def test_build_log_entry_cache_events(self, handler):
        """Test building log entry for cache events."""
        # Cache hit with TTL
        cache_hit = Mock(
            id="test-id",
            type=EventType.CACHE_HIT,
            timestamp=datetime.utcnow(),
            run_id="run-123",
            cache_key="key-123",
            cache_type="redis",
            ttl_remaining=300,
        )

        log_entry = handler._build_log_entry(cache_hit)
        assert log_entry["cache_key"] == "key-123"
        assert log_entry["cache_type"] == "redis"
        assert log_entry["ttl_remaining"] == 300

        # Cache miss without TTL
        cache_miss = Mock(
            id="test-id",
            type=EventType.CACHE_MISS,
            timestamp=datetime.utcnow(),
            run_id="run-123",
            cache_key="key-456",
            cache_type="redis",
        )

        log_entry = handler._build_log_entry(cache_miss)
        assert log_entry["cache_key"] == "key-456"
        assert "ttl_remaining" not in log_entry

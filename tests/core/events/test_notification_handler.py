"""Tests for notification event handler."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from src.core.events import EventType
from src.core.events.handlers.notification import (
    NotificationChannel,
    NotificationHandler,
    NotificationLevel,
)
from src.core.events.models import (
    ErrorEvent,
    QualityCheckFailedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    StageType,
)


class TestNotificationHandler:
    """Test cases for NotificationHandler."""

    @pytest.fixture()
    def handler(self):
        """Create a notification handler instance."""
        return NotificationHandler(channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK])

    @pytest.fixture()
    def run_id(self):
        """Generate a run ID."""
        return str(uuid4())

    @pytest.fixture()
    def timestamp(self):
        """Generate a timestamp."""
        return datetime.utcnow()

    def test_initialization(self, handler):
        """Test handler initialization."""
        assert handler.channels == [NotificationChannel.EMAIL, NotificationChannel.SLACK]
        assert handler.event_types == NotificationHandler.NOTIFICATION_EVENTS
        assert handler._config is None

    def test_default_channels(self):
        """Test default channel is email."""
        handler = NotificationHandler()
        assert handler.channels == [NotificationChannel.EMAIL]

    @pytest.mark.asyncio()
    async def test_initialize_loads_config(self, handler):
        """Test initialization loads configuration."""
        mock_config = {"notifications": {"email": {"smtp": "localhost"}}}

        with patch("src.core.events.handlers.notification.get_config_loader") as mock_loader:
            mock_loader.return_value.load_config.return_value = mock_config

            await handler.initialize()

            assert handler._config == {"email": {"smtp": "localhost"}}
            mock_loader.return_value.load_config.assert_called_once_with("deployment")

    @pytest.mark.asyncio()
    async def test_initialize_handles_config_error(self, handler):
        """Test initialization handles configuration errors gracefully."""
        with patch("src.core.events.handlers.notification.get_config_loader") as mock_loader:
            mock_loader.return_value.load_config.side_effect = Exception("Config error")

            await handler.initialize()

            assert handler._config == {}

    def test_get_notification_level(self, handler):
        """Test notification level determination."""
        # Run completed - INFO
        run_completed = Mock(type=EventType.RUN_COMPLETED)
        assert handler._get_notification_level(run_completed) == NotificationLevel.INFO

        # Quality check failed - WARNING
        quality_failed = Mock(type=EventType.QUALITY_CHECK_FAILED)
        assert handler._get_notification_level(quality_failed) == NotificationLevel.WARNING

        # Run/Stage failed - ERROR
        run_failed = Mock(type=EventType.RUN_FAILED)
        assert handler._get_notification_level(run_failed) == NotificationLevel.ERROR

        stage_failed = Mock(type=EventType.STAGE_FAILED)
        assert handler._get_notification_level(stage_failed) == NotificationLevel.ERROR

        # Error with severity
        error_regular = Mock(type=EventType.ERROR_OCCURRED, severity="high")
        assert handler._get_notification_level(error_regular) == NotificationLevel.ERROR

        error_critical = Mock(type=EventType.ERROR_OCCURRED, severity="critical")
        assert handler._get_notification_level(error_critical) == NotificationLevel.CRITICAL

    def test_build_notification_run_completed(self, handler, run_id, timestamp):
        """Test building notification for run completed."""
        event = RunCompletedEvent(
            id=str(uuid4()),
            type=EventType.RUN_COMPLETED,
            timestamp=timestamp,
            run_id=run_id,
            duration_seconds=100.5,
            total_stages=5,
            output_formats=["pdf", "docx"],
            output_paths={},
            metrics={"total_claims": 10},
        )

        notification = handler._build_notification(event, NotificationLevel.INFO)

        assert notification["title"] == "Pipeline Run Completed"
        assert notification["level"] == "info"
        assert "100.5 seconds" in notification["message"]
        assert "pdf, docx" in notification["message"]
        assert notification["details"] == {"total_claims": 10}

    def test_build_notification_run_failed(self, handler, run_id, timestamp):
        """Test building notification for run failed."""
        event = RunFailedEvent(
            id=str(uuid4()),
            type=EventType.RUN_FAILED,
            timestamp=timestamp,
            run_id=run_id,
            error_message="Connection timeout",
            error_type="TimeoutError",
            failed_stage=StageType.RESEARCH,
        )

        notification = handler._build_notification(event, NotificationLevel.ERROR)

        assert notification["title"] == "Pipeline Run Failed"
        assert notification["level"] == "error"
        assert "research" in notification["message"]
        assert "Connection timeout" in notification["message"]
        assert notification["error_type"] == "TimeoutError"

    def test_build_notification_quality_check_failed(self, handler, run_id, timestamp):
        """Test building notification for quality check failed."""
        event = QualityCheckFailedEvent(
            id=str(uuid4()),
            type=EventType.QUALITY_CHECK_FAILED,
            timestamp=timestamp,
            run_id=run_id,
            check_name="citation_completeness",
            check_type="reference",
            target="draft_output",
            score=0.4,
            failures=[
                "Missing citation 1",
                "Missing citation 2",
                "Missing citation 3",
                "Missing citation 4",
                "Missing citation 5",
            ],
        )

        notification = handler._build_notification(event, NotificationLevel.WARNING)

        assert notification["title"] == "Quality Check Failed"
        assert "citation_completeness" in notification["message"]
        assert "0.40" in notification["message"]
        assert "and 2 more..." in notification["message"]

    def test_build_notification_with_stage(self, handler, run_id, timestamp):
        """Test building notification includes stage when present."""
        event = Mock(
            id=str(uuid4()),
            type=EventType.STAGE_FAILED,
            timestamp=timestamp,
            run_id=run_id,
            stage="validation",
            error_message="Schema validation failed",
            retry_count=2,
            will_retry=True,
        )

        notification = handler._build_notification(event, NotificationLevel.ERROR)

        assert notification["stage"] == "validation"
        assert notification["will_retry"] is True

    @pytest.mark.asyncio()
    async def test_handle_sends_notifications(self, handler, run_id, timestamp):
        """Test handle method sends notifications through all channels."""
        event = RunCompletedEvent(
            id=str(uuid4()),
            type=EventType.RUN_COMPLETED,
            timestamp=timestamp,
            run_id=run_id,
            duration_seconds=100.5,
            total_stages=5,
            output_formats=["pdf"],
            output_paths={},
            metrics={},
        )

        mock_event = Mock()
        mock_event.id = event.id
        mock_event.to_dict.return_value = event.__dict__

        # Mock the send methods
        handler._send_email = AsyncMock()
        handler._send_slack = AsyncMock()

        await handler.handle(mock_event)

        # Verify both channels were called
        handler._send_email.assert_called_once()
        handler._send_slack.assert_called_once()

        # Check notification content
        email_notification = handler._send_email.call_args[0][0]
        assert email_notification["title"] == "Pipeline Run Completed"
        assert email_notification["level"] == "info"

    @pytest.mark.asyncio()
    async def test_handle_with_webhook_channel(self, handler):
        """Test handling with webhook channel."""
        handler.channels = [NotificationChannel.WEBHOOK]
        handler._send_webhook = AsyncMock()

        event = ErrorEvent(
            id=str(uuid4()),
            type=EventType.ERROR_OCCURRED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            error_message="Test error",
            error_type="TestError",
            severity="high",
            context={},
        )

        mock_event = Mock()
        mock_event.id = event.id
        mock_event.to_dict.return_value = event.__dict__

        await handler.handle(mock_event)

        handler._send_webhook.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_channel_error(self, handler):
        """Test handling when a channel fails."""
        event = RunFailedEvent(
            id=str(uuid4()),
            type=EventType.RUN_FAILED,
            timestamp=datetime.utcnow(),
            run_id=str(uuid4()),
            error_message="Test error",
            error_type="TestError",
            failed_stage=StageType.RESEARCH,
        )

        mock_event = Mock()
        mock_event.id = event.id
        mock_event.to_dict.return_value = event.__dict__

        # Make email fail
        handler._send_email = AsyncMock(side_effect=Exception("Email failed"))
        handler._send_slack = AsyncMock()

        with patch("src.core.events.handlers.notification.logger") as mock_logger:
            await handler.handle(mock_event)

            # Should log the email failure
            mock_logger.error.assert_called()
            error_msg = mock_logger.error.call_args[0][0]
            assert "Failed to send notification via NotificationChannel.EMAIL" in error_msg

            # But slack should still be called
            handler._send_slack.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_event_processing_error(self, handler):
        """Test handling when event processing fails."""
        bad_event = Mock()
        bad_event.id = "bad-id"
        bad_event.to_dict.side_effect = Exception("Processing error")

        with patch("src.core.events.handlers.notification.logger") as mock_logger:
            await handler.handle(bad_event)

            mock_logger.error.assert_called_once()
            error_msg = mock_logger.error.call_args[0][0]
            assert "Failed to handle notification for event bad-id" in error_msg

    @pytest.mark.asyncio()
    async def test_send_methods_logging(self, handler):
        """Test that send methods log notifications."""
        notification = {"title": "Test Notification", "message": "Test message"}

        with patch("src.core.events.handlers.notification.logger") as mock_logger:
            await handler._send_email(notification)
            mock_logger.info.assert_called_with("Email notification: Test Notification")

            await handler._send_slack(notification)
            mock_logger.info.assert_called_with("Slack notification: Test Notification")

            await handler._send_webhook(notification)
            mock_logger.info.assert_called_with("Webhook notification: Test Notification")

    def test_should_handle_filters_events(self, handler):
        """Test that handler only processes notification events."""
        # Should handle
        assert handler.should_handle(Mock(type=EventType.RUN_COMPLETED))
        assert handler.should_handle(Mock(type=EventType.RUN_FAILED))
        assert handler.should_handle(Mock(type=EventType.ERROR_OCCURRED))

        # Should not handle
        assert not handler.should_handle(Mock(type=EventType.RUN_STARTED))
        assert not handler.should_handle(Mock(type=EventType.CACHE_HIT))
        assert not handler.should_handle(Mock(type=EventType.METRIC_RECORDED))

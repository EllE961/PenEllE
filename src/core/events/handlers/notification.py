"""Notification handler for sending alerts on key events."""

import asyncio
from enum import Enum
from typing import Any, Dict, List, Optional

from src.core.config import get_config_loader
from src.core.events import Event, EventType, deserialize_event
from src.core.logging import get_logger

from .base import BaseEventHandler

logger = get_logger(__name__)


class NotificationChannel(str, Enum):
    """Supported notification channels."""

    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class NotificationLevel(str, Enum):
    """Notification severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class NotificationHandler(BaseEventHandler):
    """Handler that sends notifications for important events."""

    # Events that trigger notifications
    NOTIFICATION_EVENTS = {
        EventType.RUN_COMPLETED,
        EventType.RUN_FAILED,
        EventType.STAGE_FAILED,
        EventType.QUALITY_CHECK_FAILED,
        EventType.ERROR_OCCURRED,
    }

    def __init__(self, channels: Optional[List[NotificationChannel]] = None):
        """Initialize the notification handler.

        Args:
            channels: List of notification channels to use
        """
        super().__init__(self.NOTIFICATION_EVENTS)
        self.channels = channels or [NotificationChannel.EMAIL]
        self._config: Optional[Dict[str, Any]] = None

    async def _initialize(self) -> None:
        """Initialize notification handler."""
        # Load notification configuration
        try:
            deployment_config = get_config_loader().load_config("deployment")
            self._config = deployment_config.get("notifications", {})
        except Exception as e:
            logger.warning(f"Failed to load notification config: {e}")
            self._config = {}

        logger.info(f"Notification handler initialized (channels={self.channels})")

    async def _shutdown(self) -> None:
        """Cleanup notification handler."""
        logger.info("Notification handler shutdown")

    async def handle(self, event: Event) -> None:
        """Send notifications for important events.

        Args:
            event: Event to process
        """
        try:
            # Deserialize to get typed event
            event_data = event.to_dict() if hasattr(event, "to_dict") else event.payload
            typed_event = deserialize_event(event_data)

            # Determine notification level
            level = self._get_notification_level(typed_event)

            # Build notification content
            notification = self._build_notification(typed_event, level)

            # Send through configured channels
            tasks = []
            for channel in self.channels:
                if channel == NotificationChannel.EMAIL:
                    tasks.append(self._send_email(notification))
                elif channel == NotificationChannel.SLACK:
                    tasks.append(self._send_slack(notification))
                elif channel == NotificationChannel.WEBHOOK:
                    tasks.append(self._send_webhook(notification))

            # Send notifications concurrently
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(
                            f"Failed to send notification via {self.channels[i]}: {result}"
                        )

        except Exception as e:
            logger.error(f"Failed to handle notification for event {event.id}: {e}")

    def _get_notification_level(self, event: Any) -> NotificationLevel:
        """Determine notification level for event.

        Args:
            event: Typed event instance

        Returns:
            Notification level
        """
        event_type = EventType(event.type)

        if event_type == EventType.RUN_COMPLETED:
            return NotificationLevel.INFO
        elif event_type == EventType.QUALITY_CHECK_FAILED:
            return NotificationLevel.WARNING
        elif event_type in [EventType.RUN_FAILED, EventType.STAGE_FAILED]:
            return NotificationLevel.ERROR
        elif event_type == EventType.ERROR_OCCURRED:
            # Check error severity
            if hasattr(event, "severity") and event.severity == "critical":
                return NotificationLevel.CRITICAL
            return NotificationLevel.ERROR
        else:
            return NotificationLevel.INFO

    def _build_notification(self, event: Any, level: NotificationLevel) -> Dict[str, Any]:
        """Build notification content from event.

        Args:
            event: Typed event instance
            level: Notification level

        Returns:
            Notification data
        """
        event_type = EventType(event.type)

        # Base notification structure
        notification = {
            "level": level.value,
            "timestamp": event.timestamp.isoformat(),
            "run_id": event.run_id,
            "event_type": event.type,
            "event_id": event.id,
        }

        # Build title and message based on event type
        if event_type == EventType.RUN_COMPLETED:
            notification["title"] = "Pipeline Run Completed"
            notification["message"] = (
                f"Pipeline run {event.run_id} completed successfully.\n"
                f"Duration: {event.duration_seconds:.1f} seconds\n"
                f"Outputs: {', '.join(event.output_formats)}"
            )
            notification["details"] = event.metrics

        elif event_type == EventType.RUN_FAILED:
            notification["title"] = "Pipeline Run Failed"
            notification["message"] = (
                f"Pipeline run {event.run_id} failed at stage {event.failed_stage}.\n"
                f"Error: {event.error_message}"
            )
            notification["error_type"] = event.error_type

        elif event_type == EventType.STAGE_FAILED:
            notification["title"] = f"Stage Failed: {event.stage}"
            notification["message"] = (
                f"Stage {event.stage} failed in run {event.run_id}.\n"
                f"Error: {event.error_message}\n"
                f"Retry count: {event.retry_count}"
            )
            notification["will_retry"] = event.will_retry

        elif event_type == EventType.QUALITY_CHECK_FAILED:
            notification["title"] = "Quality Check Failed"
            notification["message"] = (
                f"Quality check '{event.check_name}' failed in run {event.run_id}.\n"
                f"Score: {event.score:.2f}\n"
                f"Failures: {', '.join(event.failures[:3])}"
            )
            if len(event.failures) > 3:
                notification["message"] += f" and {len(event.failures) - 3} more..."

        elif event_type == EventType.ERROR_OCCURRED:
            notification["title"] = f"Error: {event.error_type}"
            notification["message"] = (
                f"An error occurred in run {event.run_id}.\n"
                f"Severity: {event.severity}\n"
                f"Message: {event.error_message}"
            )
            notification["context"] = event.context

        # Add stage if present
        if hasattr(event, "stage") and event.stage:
            notification["stage"] = event.stage

        return notification

    async def _send_email(self, notification: Dict[str, Any]) -> None:
        """Send email notification.

        Args:
            notification: Notification data
        """
        # This would integrate with an email service
        # For now, just log it
        logger.info(f"Email notification: {notification['title']}")

    async def _send_slack(self, notification: Dict[str, Any]) -> None:
        """Send Slack notification.

        Args:
            notification: Notification data
        """
        # This would integrate with Slack API
        # For now, just log it
        logger.info(f"Slack notification: {notification['title']}")

    async def _send_webhook(self, notification: Dict[str, Any]) -> None:
        """Send webhook notification.

        Args:
            notification: Notification data
        """
        # This would make HTTP POST to configured webhook
        # For now, just log it
        logger.info(f"Webhook notification: {notification['title']}")

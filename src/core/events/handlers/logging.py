"""Structured logging handler for events."""

from typing import Any, Dict

from src.core.events import Event, EventType, deserialize_event
from src.core.logging import get_logger

from .base import BaseEventHandler

logger = get_logger(__name__)


class LoggingHandler(BaseEventHandler):
    """Handler that logs events in structured format."""

    def __init__(self, log_level: str = "INFO"):
        """Initialize the logging handler.

        Args:
            log_level: Minimum log level for events
        """
        super().__init__(set(EventType))  # Handle all event types
        self.log_level = log_level

    async def _initialize(self) -> None:
        """Initialize logging handler."""
        logger.info("Logging handler initialized", extra={"log_level": self.log_level})

    async def _shutdown(self) -> None:
        """Cleanup logging handler."""
        logger.info("Logging handler shutdown")

    async def handle(self, event: Event) -> None:
        """Log event in structured format.

        Args:
            event: Event to log
        """
        try:
            # Deserialize to get typed event
            event_data = event.to_dict() if hasattr(event, "to_dict") else event.payload
            typed_event = deserialize_event(event_data)

            # Build structured log entry
            log_entry = self._build_log_entry(typed_event)

            # Determine log level based on event type
            log_level = self._get_log_level(typed_event)

            # Log with appropriate level
            logger.log(log_level, f"Event: {typed_event.type}", extra=log_entry)

        except Exception as e:
            logger.error(f"Failed to log event {event.id}: {e}")

    def _build_log_entry(self, event: Any) -> Dict[str, Any]:
        """Build structured log entry from event.

        Args:
            event: Typed event instance

        Returns:
            Structured log data
        """
        # Base fields present in all events
        log_entry = {
            "event_id": event.id,
            "event_type": event.type,
            "timestamp": event.timestamp.isoformat(),
            "run_id": event.run_id,
        }

        # Add stage if present
        if hasattr(event, "stage") and event.stage:
            log_entry["stage"] = event.stage

        # Add event-specific fields
        event_type = EventType(event.type)

        if event_type == EventType.RUN_STARTED:
            log_entry.update(
                {
                    "topic": event.topic,
                    "user_id": event.user_id,
                    "request_id": event.request_id,
                }
            )

        elif event_type == EventType.RUN_COMPLETED:
            log_entry.update(
                {
                    "duration_seconds": event.duration_seconds,
                    "total_stages": event.total_stages,
                    "output_formats": event.output_formats,
                    "metrics": event.metrics,
                }
            )

        elif event_type in [EventType.RUN_FAILED, EventType.STAGE_FAILED]:
            log_entry.update(
                {
                    "error_message": event.error_message,
                    "error_type": event.error_type,
                }
            )
            if hasattr(event, "failed_stage"):
                log_entry["failed_stage"] = event.failed_stage

        elif event_type == EventType.STAGE_COMPLETED:
            log_entry.update(
                {
                    "duration_seconds": event.duration_seconds,
                    "outputs": event.outputs,
                    "metrics": event.metrics,
                }
            )

        elif event_type == EventType.SOURCE_FOUND:
            log_entry.update(
                {
                    "source_id": event.source_id,
                    "title": event.title,
                    "quality_score": event.quality_score,
                    "connector": event.connector,
                }
            )

        elif event_type == EventType.EVIDENCE_EXTRACTED:
            log_entry.update(
                {
                    "source_id": event.source_id,
                    "evidence_id": event.evidence_id,
                    "confidence": event.confidence,
                }
            )

        elif event_type == EventType.CLAIM_GENERATED:
            log_entry.update(
                {
                    "claim_id": event.claim_id,
                    "confidence": event.confidence,
                    "supporting_evidence_count": len(event.supporting_evidence_ids),
                }
            )

        elif event_type in [EventType.QUALITY_CHECK_PASSED, EventType.QUALITY_CHECK_FAILED]:
            log_entry.update(
                {
                    "check_name": event.check_name,
                    "check_type": event.check_type,
                    "score": event.score,
                }
            )
            if event_type == EventType.QUALITY_CHECK_FAILED:
                log_entry["failures"] = event.failures

        elif event_type == EventType.ERROR_OCCURRED:
            log_entry.update(
                {
                    "error_message": event.error_message,
                    "error_type": event.error_type,
                    "severity": event.severity,
                    "context": event.context,
                }
            )

        elif event_type == EventType.METRIC_RECORDED:
            log_entry.update(
                {
                    "metric_name": event.metric_name,
                    "metric_value": event.metric_value,
                    "metric_unit": event.metric_unit,
                    "labels": event.labels,
                }
            )

        elif event_type in [EventType.CACHE_HIT, EventType.CACHE_MISS]:
            log_entry.update(
                {
                    "cache_key": event.cache_key,
                    "cache_type": event.cache_type,
                }
            )
            if event_type == EventType.CACHE_HIT and hasattr(event, "ttl_remaining"):
                log_entry["ttl_remaining"] = event.ttl_remaining

        # Add metadata if present
        if hasattr(event, "metadata") and event.metadata:
            log_entry["metadata"] = event.metadata

        return log_entry

    def _get_log_level(self, event: Any) -> int:
        """Determine appropriate log level for event.

        Args:
            event: Typed event instance

        Returns:
            Python logging level constant
        """
        import logging

        event_type = EventType(event.type)

        # Errors and failures are logged as ERROR
        if event_type in [
            EventType.RUN_FAILED,
            EventType.STAGE_FAILED,
            EventType.ERROR_OCCURRED,
            EventType.SOURCE_FAILED,
        ]:
            return logging.ERROR

        # Warnings for quality check failures
        elif event_type == EventType.QUALITY_CHECK_FAILED:
            return logging.WARNING

        # Debug for frequent events
        elif event_type in [
            EventType.CACHE_HIT,
            EventType.CACHE_MISS,
            EventType.METRIC_RECORDED,
        ]:
            return logging.DEBUG

        # Info for everything else
        else:
            return logging.INFO

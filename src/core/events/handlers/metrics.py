"""Prometheus metrics handler for events."""

from datetime import datetime
from typing import Dict

from prometheus_client import Counter, Gauge, Histogram, Info

from src.core.events import Event, EventType, deserialize_event
from src.core.events.models import (
    CacheHitEvent,
    CacheMissEvent,
    ErrorEvent,
    QualityCheckFailedEvent,
    QualityCheckPassedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    SourceFoundEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageStartedEvent,
)
from src.core.logging import get_logger

from .base import BaseEventHandler

logger = get_logger(__name__)


# Define Prometheus metrics
pipeline_runs_total = Counter(
    "penelle_pipeline_runs_total", "Total number of pipeline runs", ["status"]
)

pipeline_run_duration_seconds = Histogram(
    "penelle_pipeline_run_duration_seconds",
    "Pipeline run duration in seconds",
    buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600],
)

stage_executions_total = Counter(
    "penelle_stage_executions_total", "Total number of stage executions", ["stage", "status"]
)

stage_duration_seconds = Histogram(
    "penelle_stage_duration_seconds",
    "Stage execution duration in seconds",
    ["stage"],
    buckets=[10, 30, 60, 120, 300, 600],
)

sources_found_total = Counter(
    "penelle_sources_found_total", "Total number of sources found", ["connector", "source_type"]
)

quality_checks_total = Counter(
    "penelle_quality_checks_total", "Total number of quality checks", ["check_name", "status"]
)

errors_total = Counter("penelle_errors_total", "Total number of errors", ["severity", "stage"])

cache_operations_total = Counter(
    "penelle_cache_operations_total",
    "Total number of cache operations",
    ["operation", "cache_type"],
)

active_pipeline_runs = Gauge(
    "penelle_active_pipeline_runs", "Number of currently active pipeline runs"
)

pipeline_info = Info("penelle_pipeline", "Pipeline information")


class MetricsHandler(BaseEventHandler):
    """Handler that updates Prometheus metrics based on events."""

    def __init__(self) -> None:
        """Initialize the metrics handler."""
        super().__init__(set(EventType))  # Handle all event types
        self._run_start_times: Dict[str, datetime] = {}
        self._stage_start_times: Dict[tuple, datetime] = {}

    async def _initialize(self) -> None:
        """Initialize metrics handler."""
        # Set pipeline info
        pipeline_info.info({"version": "1.0.0", "name": "PenEllE"})
        logger.info("Metrics handler initialized")

    async def _shutdown(self) -> None:
        """Cleanup metrics handler."""
        self._run_start_times.clear()
        self._stage_start_times.clear()
        logger.info("Metrics handler shutdown")

    async def handle(self, event: Event) -> None:
        """Update metrics based on event.

        Args:
            event: Event to process
        """
        try:
            # Deserialize to specific event type
            event_data = event.to_dict() if hasattr(event, "to_dict") else event.payload
            typed_event = deserialize_event(event_data)

            # Route to specific handler
            if isinstance(typed_event, RunStartedEvent):
                await self._handle_run_started(typed_event)
            elif isinstance(typed_event, RunCompletedEvent):
                await self._handle_run_completed(typed_event)
            elif isinstance(typed_event, RunFailedEvent):
                await self._handle_run_failed(typed_event)
            elif isinstance(typed_event, StageStartedEvent):
                await self._handle_stage_started(typed_event)
            elif isinstance(typed_event, StageCompletedEvent):
                await self._handle_stage_completed(typed_event)
            elif isinstance(typed_event, StageFailedEvent):
                await self._handle_stage_failed(typed_event)
            elif isinstance(typed_event, SourceFoundEvent):
                await self._handle_source_found(typed_event)
            elif isinstance(typed_event, QualityCheckPassedEvent):
                await self._handle_quality_check_passed(typed_event)
            elif isinstance(typed_event, QualityCheckFailedEvent):
                await self._handle_quality_check_failed(typed_event)
            elif isinstance(typed_event, ErrorEvent):
                await self._handle_error(typed_event)
            elif isinstance(typed_event, CacheHitEvent):
                await self._handle_cache_hit(typed_event)
            elif isinstance(typed_event, CacheMissEvent):
                await self._handle_cache_miss(typed_event)

        except Exception as e:
            logger.error(f"Failed to update metrics for event {event.id}: {e}")

    async def _handle_run_started(self, event: RunStartedEvent) -> None:
        """Handle run started event."""
        self._run_start_times[event.run_id] = event.timestamp
        pipeline_runs_total.labels(status="started").inc()
        active_pipeline_runs.inc()

    async def _handle_run_completed(self, event: RunCompletedEvent) -> None:
        """Handle run completed event."""
        pipeline_runs_total.labels(status="completed").inc()
        active_pipeline_runs.dec()

        # Record duration if we have start time
        if event.run_id in self._run_start_times:
            start_time = self._run_start_times.pop(event.run_id)
            duration = (event.timestamp - start_time).total_seconds()
            pipeline_run_duration_seconds.observe(duration)

    async def _handle_run_failed(self, event: RunFailedEvent) -> None:
        """Handle run failed event."""
        pipeline_runs_total.labels(status="failed").inc()
        active_pipeline_runs.dec()

        # Remove start time if exists
        self._run_start_times.pop(event.run_id, None)

    async def _handle_stage_started(self, event: StageStartedEvent) -> None:
        """Handle stage started event."""
        key = (event.run_id, event.stage)
        self._stage_start_times[key] = event.timestamp
        stage_executions_total.labels(stage=event.stage, status="started").inc()

    async def _handle_stage_completed(self, event: StageCompletedEvent) -> None:
        """Handle stage completed event."""
        stage_executions_total.labels(stage=event.stage, status="completed").inc()

        # Record duration if we have start time
        key = (event.run_id, event.stage)
        if key in self._stage_start_times:
            start_time = self._stage_start_times.pop(key)
            duration = (event.timestamp - start_time).total_seconds()
            stage_duration_seconds.labels(stage=event.stage).observe(duration)

    async def _handle_stage_failed(self, event: StageFailedEvent) -> None:
        """Handle stage failed event."""
        stage_executions_total.labels(stage=event.stage, status="failed").inc()

        # Remove start time if exists
        key = (event.run_id, event.stage)
        self._stage_start_times.pop(key, None)

    async def _handle_source_found(self, event: SourceFoundEvent) -> None:
        """Handle source found event."""
        sources_found_total.labels(connector=event.connector, source_type=event.source_type).inc()

    async def _handle_quality_check_passed(self, event: QualityCheckPassedEvent) -> None:
        """Handle quality check passed event."""
        quality_checks_total.labels(check_name=event.check_name, status="passed").inc()

    async def _handle_quality_check_failed(self, event: QualityCheckFailedEvent) -> None:
        """Handle quality check failed event."""
        quality_checks_total.labels(check_name=event.check_name, status="failed").inc()

    async def _handle_error(self, event: ErrorEvent) -> None:
        """Handle error event."""
        errors_total.labels(severity=event.severity, stage=event.stage or "unknown").inc()

    async def _handle_cache_hit(self, event: CacheHitEvent) -> None:
        """Handle cache hit event."""
        cache_operations_total.labels(operation="hit", cache_type=event.cache_type).inc()

    async def _handle_cache_miss(self, event: CacheMissEvent) -> None:
        """Handle cache miss event."""
        cache_operations_total.labels(operation="miss", cache_type=event.cache_type).inc()

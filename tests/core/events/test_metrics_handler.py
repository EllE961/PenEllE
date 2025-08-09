"""Tests for metrics event handler."""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from src.core.events import EventType
from src.core.events.handlers.metrics import MetricsHandler
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
    StageStartedEvent,
    StageType,
)


class TestMetricsHandler:
    """Test cases for MetricsHandler."""

    @pytest.fixture()
    def handler(self):
        """Create a metrics handler instance."""
        return MetricsHandler()

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
        assert handler.event_types == set(EventType)
        assert handler._run_start_times == {}
        assert handler._stage_start_times == {}

    @pytest.mark.asyncio()
    async def test_initialize(self, handler):
        """Test initialization with pipeline info."""
        with patch("src.core.events.handlers.metrics.pipeline_info") as mock_info:
            await handler.initialize()
            mock_info.info.assert_called_once_with({"version": "1.0.0", "name": "PenEllE"})

    @pytest.mark.asyncio()
    async def test_shutdown_clears_times(self, handler, run_id):
        """Test shutdown clears tracked times."""
        handler._run_start_times[run_id] = datetime.utcnow()
        handler._stage_start_times[(run_id, StageType.DRAFT)] = datetime.utcnow()

        await handler.initialize()
        await handler.shutdown()

        assert handler._run_start_times == {}
        assert handler._stage_start_times == {}

    @pytest.mark.asyncio()
    async def test_handle_run_started(self, handler, run_id, timestamp):
        """Test handling run started event."""
        event = RunStartedEvent(
            id=str(uuid4()),
            type=EventType.RUN_STARTED,
            timestamp=timestamp,
            run_id=run_id,
            topic="Test Topic",
            user_id=str(uuid4()),
            request_id=str(uuid4()),
            config={},
        )

        with patch("src.core.events.handlers.metrics.pipeline_runs_total") as mock_counter, patch(
            "src.core.events.handlers.metrics.active_pipeline_runs"
        ) as mock_gauge:
            mock_event = Mock()
            mock_event.id = event.id
            mock_event.to_dict.return_value = event.__dict__

            await handler.handle(mock_event)

            assert handler._run_start_times[run_id] == timestamp
            mock_counter.labels.assert_called_with(status="started")
            mock_counter.labels().inc.assert_called_once()
            mock_gauge.inc.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_run_completed_with_duration(self, handler, run_id, timestamp):
        """Test handling run completed event with duration tracking."""
        start_time = timestamp - timedelta(seconds=100)
        handler._run_start_times[run_id] = start_time

        event = RunCompletedEvent(
            id=str(uuid4()),
            type=EventType.RUN_COMPLETED,
            timestamp=timestamp,
            run_id=run_id,
            duration_seconds=100.0,
            total_stages=5,
            output_formats=["pdf"],
            output_paths={},
            metrics={},
        )

        with patch("src.core.events.handlers.metrics.pipeline_runs_total") as mock_counter, patch(
            "src.core.events.handlers.metrics.active_pipeline_runs"
        ) as mock_gauge, patch(
            "src.core.events.handlers.metrics.pipeline_run_duration_seconds"
        ) as mock_histogram:
            mock_event = Mock()
            mock_event.id = event.id
            mock_event.to_dict.return_value = event.__dict__

            await handler.handle(mock_event)

            assert run_id not in handler._run_start_times
            mock_counter.labels.assert_called_with(status="completed")
            mock_gauge.dec.assert_called_once()
            mock_histogram.observe.assert_called_once_with(100.0)

    @pytest.mark.asyncio()
    async def test_handle_run_failed(self, handler, run_id, timestamp):
        """Test handling run failed event."""
        handler._run_start_times[run_id] = timestamp

        event = RunFailedEvent(
            id=str(uuid4()),
            type=EventType.RUN_FAILED,
            timestamp=timestamp,
            run_id=run_id,
            error_message="Test error",
            error_type="TestError",
            failed_stage=StageType.DRAFT,
        )

        with patch("src.core.events.handlers.metrics.pipeline_runs_total") as mock_counter, patch(
            "src.core.events.handlers.metrics.active_pipeline_runs"
        ) as mock_gauge:
            mock_event = Mock()
            mock_event.id = event.id
            mock_event.to_dict.return_value = event.__dict__

            await handler.handle(mock_event)

            assert run_id not in handler._run_start_times
            mock_counter.labels.assert_called_with(status="failed")
            mock_gauge.dec.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_stage_lifecycle(self, handler, run_id, timestamp):
        """Test handling stage started and completed events."""
        stage = StageType.DRAFT
        start_time = timestamp
        end_time = timestamp + timedelta(seconds=30)

        # Stage started
        start_event = StageStartedEvent(
            id=str(uuid4()),
            type=EventType.STAGE_STARTED,
            timestamp=start_time,
            run_id=run_id,
            stage=stage,
            stage_config={},
            metadata={},
        )

        with patch("src.core.events.handlers.metrics.stage_executions_total") as mock_counter:
            mock_event = Mock()
            mock_event.id = start_event.id
            mock_event.to_dict.return_value = start_event.__dict__

            await handler.handle(mock_event)

            assert (run_id, stage) in handler._stage_start_times
            mock_counter.labels.assert_called_with(stage=stage, status="started")

        # Stage completed
        complete_event = StageCompletedEvent(
            id=str(uuid4()),
            type=EventType.STAGE_COMPLETED,
            timestamp=end_time,
            run_id=run_id,
            stage=stage,
            duration_seconds=30.0,
            outputs={},
            metrics={},
        )

        with patch(
            "src.core.events.handlers.metrics.stage_executions_total"
        ) as mock_counter, patch(
            "src.core.events.handlers.metrics.stage_duration_seconds"
        ) as mock_histogram:
            mock_event = Mock()
            mock_event.id = complete_event.id
            mock_event.to_dict.return_value = complete_event.__dict__

            await handler.handle(mock_event)

            assert (run_id, stage) not in handler._stage_start_times
            mock_counter.labels.assert_called_with(stage=stage, status="completed")
            mock_histogram.labels.assert_called_with(stage=stage)
            mock_histogram.labels().observe.assert_called_once_with(30.0)

    @pytest.mark.asyncio()
    async def test_handle_source_found(self, handler, run_id, timestamp):
        """Test handling source found event."""
        event = SourceFoundEvent(
            id=str(uuid4()),
            type=EventType.SOURCE_FOUND,
            timestamp=timestamp,
            run_id=run_id,
            source_id=str(uuid4()),
            title="Test Source",
            quality_score=0.9,
            connector="pubmed",
            source_type="journal_article",
            authors=[],
            year=2024,
            metadata={},
        )

        with patch("src.core.events.handlers.metrics.sources_found_total") as mock_counter:
            mock_event = Mock()
            mock_event.id = event.id
            mock_event.to_dict.return_value = event.__dict__

            await handler.handle(mock_event)

            mock_counter.labels.assert_called_with(
                connector="pubmed", source_type="journal_article"
            )
            mock_counter.labels().inc.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_quality_checks(self, handler, run_id, timestamp):
        """Test handling quality check events."""
        # Passed check
        passed_event = QualityCheckPassedEvent(
            id=str(uuid4()),
            type=EventType.QUALITY_CHECK_PASSED,
            timestamp=timestamp,
            run_id=run_id,
            check_name="grammar_check",
            check_type="linguistic",
            target="draft_output",
            score=0.95,
            details={},
            metadata={},
        )

        with patch("src.core.events.handlers.metrics.quality_checks_total") as mock_counter:
            mock_event = Mock()
            mock_event.id = passed_event.id
            mock_event.to_dict.return_value = passed_event.__dict__

            await handler.handle(mock_event)

            mock_counter.labels.assert_called_with(check_name="grammar_check", status="passed")

        # Failed check
        failed_event = QualityCheckFailedEvent(
            id=str(uuid4()),
            type=EventType.QUALITY_CHECK_FAILED,
            timestamp=timestamp,
            run_id=run_id,
            check_name="citation_check",
            check_type="reference",
            target="draft_output",
            score=0.3,
            failures=["Missing citations"],
            recommendations=[],
            metadata={},
        )

        with patch("src.core.events.handlers.metrics.quality_checks_total") as mock_counter:
            mock_event = Mock()
            mock_event.id = failed_event.id
            mock_event.to_dict.return_value = failed_event.__dict__

            await handler.handle(mock_event)

            mock_counter.labels.assert_called_with(check_name="citation_check", status="failed")

    @pytest.mark.asyncio()
    async def test_handle_error_event(self, handler, run_id, timestamp):
        """Test handling error event."""
        event = ErrorEvent(
            id=str(uuid4()),
            type=EventType.ERROR_OCCURRED,
            timestamp=timestamp,
            run_id=run_id,
            error_message="Test error",
            error_type="ValueError",
            severity="high",
            stage=StageType.REVIEW,
            context={},
        )

        with patch("src.core.events.handlers.metrics.errors_total") as mock_counter:
            mock_event = Mock()
            mock_event.id = event.id
            mock_event.to_dict.return_value = event.__dict__

            await handler.handle(mock_event)

            mock_counter.labels.assert_called_with(severity="high", stage="review")

    @pytest.mark.asyncio()
    async def test_handle_cache_events(self, handler, run_id, timestamp):
        """Test handling cache hit and miss events."""
        # Cache hit
        hit_event = CacheHitEvent(
            id=str(uuid4()),
            type=EventType.CACHE_HIT,
            timestamp=timestamp,
            run_id=run_id,
            cache_key="source:123",
            cache_type="redis",
            ttl_remaining=300,
        )

        with patch("src.core.events.handlers.metrics.cache_operations_total") as mock_counter:
            mock_event = Mock()
            mock_event.id = hit_event.id
            mock_event.to_dict.return_value = hit_event.__dict__

            await handler.handle(mock_event)

            mock_counter.labels.assert_called_with(operation="hit", cache_type="redis")

        # Cache miss
        miss_event = CacheMissEvent(
            id=str(uuid4()),
            type=EventType.CACHE_MISS,
            timestamp=timestamp,
            run_id=run_id,
            cache_key="source:456",
            cache_type="redis",
            will_cache=True,
        )

        with patch("src.core.events.handlers.metrics.cache_operations_total") as mock_counter:
            mock_event = Mock()
            mock_event.id = miss_event.id
            mock_event.to_dict.return_value = miss_event.__dict__

            await handler.handle(mock_event)

            mock_counter.labels.assert_called_with(operation="miss", cache_type="redis")

    @pytest.mark.asyncio()
    async def test_handle_exception(self, handler):
        """Test exception handling during event processing."""
        bad_event = Mock()
        bad_event.id = "bad-id"
        bad_event.to_dict.side_effect = Exception("Processing error")

        with patch("src.core.events.handlers.metrics.logger") as mock_logger:
            await handler.handle(bad_event)

            mock_logger.error.assert_called_once()
            error_msg = mock_logger.error.call_args[0][0]
            assert "Failed to update metrics for event bad-id" in error_msg

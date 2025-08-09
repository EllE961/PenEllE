"""Tests for event models."""

import uuid
from datetime import datetime

import pytest

from src.core.events.models import (
    EVENT_TYPE_MAP,
    BaseEvent,
    CacheHitEvent,
    CacheMissEvent,
    ClaimGeneratedEvent,
    ErrorEvent,
    EventType,
    EvidenceExtractedEvent,
    MetricRecordedEvent,
    QualityCheckFailedEvent,
    QualityCheckPassedEvent,
    QualityCheckStartedEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunStartedEvent,
    SourceFoundEvent,
    StageCompletedEvent,
    StageFailedEvent,
    StageStartedEvent,
    StageType,
    create_error_event,
    create_run_started_event,
    create_stage_started_event,
    deserialize_event,
)


class TestEnums:
    """Test event enums."""

    def test_event_type_enum(self):
        """Test EventType enum values."""
        assert EventType.RUN_STARTED == "run.started"
        assert EventType.STAGE_COMPLETED == "stage.completed"
        assert EventType.ERROR_OCCURRED == "error.occurred"

    def test_stage_type_enum(self):
        """Test StageType enum values."""
        assert StageType.RESEARCH == "research"
        assert StageType.DRAFT == "draft"
        assert StageType.FORMAT == "format"


class TestBaseEvent:
    """Test BaseEvent model."""

    def test_base_event_creation(self):
        """Test creating a base event."""
        event = BaseEvent(type=EventType.RUN_STARTED, run_id="run-123", stage=StageType.RESEARCH)

        assert event.id is not None
        assert event.type == EventType.RUN_STARTED
        assert event.run_id == "run-123"
        assert event.stage == StageType.RESEARCH
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_base_event_with_metadata(self):
        """Test base event with metadata."""
        metadata = {"key": "value", "count": 42}
        event = BaseEvent(type=EventType.RUN_STARTED, run_id="run-123", metadata=metadata)

        assert event.metadata == metadata

    def test_base_event_custom_id_and_timestamp(self):
        """Test base event with custom ID and timestamp."""
        custom_id = str(uuid.uuid4())
        custom_time = datetime(2024, 1, 1, 12, 0, 0)

        event = BaseEvent(
            id=custom_id, timestamp=custom_time, type=EventType.RUN_STARTED, run_id="run-123"
        )

        assert event.id == custom_id
        assert event.timestamp == custom_time


class TestRunEvents:
    """Test run-related events."""

    def test_run_started_event(self):
        """Test RunStartedEvent."""
        config = {"models": {"research": "gpt-4"}}

        event = RunStartedEvent(
            run_id="run-123",
            request_id="req-456",
            topic="AI in Healthcare",
            user_id="user-001",
            config=config,
        )

        assert event.type == EventType.RUN_STARTED
        assert event.request_id == "req-456"
        assert event.topic == "AI in Healthcare"
        assert event.user_id == "user-001"
        assert event.config == config

    def test_run_completed_event(self):
        """Test RunCompletedEvent."""
        metrics = {"sources": 25, "claims": 15}

        event = RunCompletedEvent(
            run_id="run-123",
            duration_seconds=300.5,
            total_stages=5,
            output_formats=["markdown", "pdf"],
            metrics=metrics,
        )

        assert event.type == EventType.RUN_COMPLETED
        assert event.duration_seconds == 300.5
        assert event.total_stages == 5
        assert "markdown" in event.output_formats
        assert event.metrics["sources"] == 25

    def test_run_failed_event(self):
        """Test RunFailedEvent."""
        event = RunFailedEvent(
            run_id="run-123",
            error_message="Connection timeout",
            error_type="TimeoutError",
            failed_stage=StageType.RESEARCH,
            traceback="Full traceback here...",
        )

        assert event.type == EventType.RUN_FAILED
        assert event.error_message == "Connection timeout"
        assert event.error_type == "TimeoutError"
        assert event.failed_stage == StageType.RESEARCH


class TestStageEvents:
    """Test stage-related events."""

    def test_stage_started_event(self):
        """Test StageStartedEvent."""
        stage_config = {"model": "gpt-4", "temperature": 0.7}

        event = StageStartedEvent(
            run_id="run-123", stage=StageType.RESEARCH, stage_config=stage_config, retry_count=0
        )

        assert event.type == EventType.STAGE_STARTED
        assert event.stage == StageType.RESEARCH
        assert event.stage_config["model"] == "gpt-4"
        assert event.retry_count == 0

    def test_stage_completed_event(self):
        """Test StageCompletedEvent."""
        outputs = {"sources_found": 30, "quality_score": 0.85}
        metrics = {"api_calls": 5, "tokens_used": 1500}

        event = StageCompletedEvent(
            run_id="run-123",
            stage=StageType.RESEARCH,
            duration_seconds=120.5,
            outputs=outputs,
            metrics=metrics,
        )

        assert event.type == EventType.STAGE_COMPLETED
        assert event.duration_seconds == 120.5
        assert event.outputs["sources_found"] == 30
        assert event.metrics["api_calls"] == 5

    def test_stage_failed_event(self):
        """Test StageFailedEvent."""
        event = StageFailedEvent(
            run_id="run-123",
            stage=StageType.DRAFT,
            error_message="Model rate limit exceeded",
            error_type="RateLimitError",
            retry_count=2,
            will_retry=True,
        )

        assert event.type == EventType.STAGE_FAILED
        assert event.retry_count == 2
        assert event.will_retry is True


class TestSourceAndEvidenceEvents:
    """Test source and evidence events."""

    def test_source_found_event(self):
        """Test SourceFoundEvent."""
        event = SourceFoundEvent(
            run_id="run-123",
            source_id="doi:10.1234/example",
            source_type="journal_article",
            title="AI Applications in Healthcare",
            authors=["Smith, J.", "Doe, A."],
            year=2024,
            quality_score=0.85,
            connector="semantic_scholar",
        )

        assert event.type == EventType.SOURCE_FOUND
        assert event.stage == StageType.RESEARCH
        assert event.source_id == "doi:10.1234/example"
        assert len(event.authors) == 2
        assert event.quality_score == 0.85

    def test_evidence_extracted_event(self):
        """Test EvidenceExtractedEvent."""
        event = EvidenceExtractedEvent(
            run_id="run-123",
            source_id="source-456",
            evidence_id="evidence-789",
            evidence_type="statistical",
            confidence=0.9,
            text_snippet="Studies show 85% improvement...",
        )

        assert event.type == EventType.EVIDENCE_EXTRACTED
        assert event.source_id == "source-456"
        assert event.confidence == 0.9


class TestClaimAndQualityEvents:
    """Test claim and quality check events."""

    def test_claim_generated_event(self):
        """Test ClaimGeneratedEvent."""
        event = ClaimGeneratedEvent(
            run_id="run-123",
            stage=StageType.OUTLINE,
            claim_id="claim-001",
            claim_text="AI improves diagnostic accuracy",
            supporting_evidence_ids=["ev-1", "ev-2", "ev-3"],
            confidence=0.85,
        )

        assert event.type == EventType.CLAIM_GENERATED
        assert event.claim_id == "claim-001"
        assert len(event.supporting_evidence_ids) == 3

    def test_quality_check_events(self):
        """Test quality check events."""
        # Started event
        started = QualityCheckStartedEvent(
            run_id="run-123",
            stage=StageType.REVIEW,
            check_name="readability",
            check_type="text_analysis",
            target="draft_output",
            criteria={"min_score": 0.7},
        )

        assert started.type == EventType.QUALITY_CHECK_STARTED
        assert started.check_name == "readability"

        # Passed event
        passed = QualityCheckPassedEvent(
            run_id="run-123",
            stage=StageType.REVIEW,
            check_name="readability",
            check_type="text_analysis",
            target="draft_output",
            score=0.85,
            details={"flesch_score": 65},
        )

        assert passed.type == EventType.QUALITY_CHECK_PASSED
        assert passed.score == 0.85

        # Failed event
        failed = QualityCheckFailedEvent(
            run_id="run-123",
            stage=StageType.REVIEW,
            check_name="evidence",
            check_type="validation",
            target="claims",
            score=0.4,
            failures=["Insufficient sources", "Low confidence"],
            recommendations=["Add more sources", "Verify claims"],
        )

        assert failed.type == EventType.QUALITY_CHECK_FAILED
        assert len(failed.failures) == 2
        assert len(failed.recommendations) == 2


class TestUtilityEvents:
    """Test utility events (error, metric, cache)."""

    def test_error_event(self):
        """Test ErrorEvent."""
        context = {"stage": "research", "attempt": 3}

        event = ErrorEvent(
            run_id="run-123",
            stage=StageType.RESEARCH,
            error_message="API connection failed",
            error_type="ConnectionError",
            severity="high",
            context=context,
            traceback="Full traceback...",
        )

        assert event.type == EventType.ERROR_OCCURRED
        assert event.severity == "high"
        assert event.context["attempt"] == 3

    def test_metric_recorded_event(self):
        """Test MetricRecordedEvent."""
        event = MetricRecordedEvent(
            run_id="run-123",
            stage=StageType.DRAFT,
            metric_name="tokens_used",
            metric_value=1500.0,
            metric_unit="tokens",
            labels={"model": "gpt-4", "provider": "openai"},
        )

        assert event.type == EventType.METRIC_RECORDED
        assert event.metric_value == 1500.0
        assert event.labels["model"] == "gpt-4"

    def test_cache_events(self):
        """Test cache hit/miss events."""
        # Cache hit
        hit = CacheHitEvent(
            run_id="run-123",
            stage=StageType.RESEARCH,
            cache_key="research:ai-healthcare:sources",
            cache_type="research_results",
            ttl_remaining=3600,
        )

        assert hit.type == EventType.CACHE_HIT
        assert hit.ttl_remaining == 3600

        # Cache miss
        miss = CacheMissEvent(
            run_id="run-123",
            stage=StageType.RESEARCH,
            cache_key="research:ai-healthcare:sources",
            cache_type="research_results",
            will_cache=True,
        )

        assert miss.type == EventType.CACHE_MISS
        assert miss.will_cache is True


class TestFactoryFunctions:
    """Test event factory functions."""

    def test_create_run_started_event(self):
        """Test create_run_started_event factory."""
        event = create_run_started_event(
            run_id="run-123",
            request_id="req-456",
            topic="Test Topic",
            user_id="user-001",
            config={"test": True},
        )

        assert isinstance(event, RunStartedEvent)
        assert event.run_id == "run-123"
        assert event.topic == "Test Topic"

    def test_create_stage_started_event(self):
        """Test create_stage_started_event factory."""
        event = create_stage_started_event(
            run_id="run-123", stage=StageType.DRAFT, stage_config={"model": "gpt-4"}, retry_count=1
        )

        assert isinstance(event, StageStartedEvent)
        assert event.stage == StageType.DRAFT
        assert event.retry_count == 1

    def test_create_error_event(self):
        """Test create_error_event factory."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            event = create_error_event(
                run_id="run-123",
                error=e,
                stage=StageType.RESEARCH,
                severity="medium",
                context={"test": True},
            )

        assert isinstance(event, ErrorEvent)
        assert event.error_message == "Test error"
        assert event.error_type == "ValueError"
        assert event.severity == "medium"
        assert event.traceback is not None


class TestEventDeserialization:
    """Test event deserialization."""

    def test_deserialize_run_started_event(self):
        """Test deserializing RunStartedEvent."""
        data = {
            "id": "event-123",
            "timestamp": datetime.utcnow().isoformat(),
            "type": "run.started",
            "run_id": "run-456",
            "request_id": "req-789",
            "topic": "Test Topic",
            "user_id": "user-001",
            "config": {},
        }

        event = deserialize_event(data)

        assert isinstance(event, RunStartedEvent)
        assert event.run_id == "run-456"
        assert event.topic == "Test Topic"

    def test_deserialize_unknown_event_type(self):
        """Test deserializing unknown event type."""
        data = {"type": "unknown.event", "run_id": "run-123"}

        with pytest.raises(ValueError) as exc_info:
            deserialize_event(data)

        assert "Unknown event type" in str(exc_info.value)

    def test_deserialize_missing_type(self):
        """Test deserializing without type field."""
        data = {"run_id": "run-123"}

        with pytest.raises(ValueError) as exc_info:
            deserialize_event(data)

        assert "missing 'type' field" in str(exc_info.value)

    def test_event_type_map_completeness(self):
        """Test that EVENT_TYPE_MAP contains all event types."""
        # Check that all EventType values have corresponding classes
        for event_type in EventType:
            assert event_type in EVENT_TYPE_MAP, f"Missing mapping for {event_type}"

        # Verify each mapped class is a BaseEvent subclass
        for event_class in EVENT_TYPE_MAP.values():
            assert issubclass(event_class, BaseEvent)

"""Event models for the PenEllE pipeline.

This module defines all event types following the specification
for pipeline execution tracking and monitoring.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, cast

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Enumeration of all event types."""

    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"

    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    STAGE_RETRYING = "stage.retrying"

    PLANNING_STARTED = "planning.started"
    PLANNING_COMPLETED = "planning.completed"
    PLANNING_FAILED = "planning.failed"

    SOURCE_FOUND = "source.found"
    SOURCE_FAILED = "source.failed"

    EVIDENCE_EXTRACTED = "evidence.extracted"
    EVIDENCE_FILTERED = "evidence.filtered"

    CLAIM_GENERATED = "claim.generated"
    CLAIM_VALIDATED = "claim.validated"

    QUALITY_CHECK_STARTED = "quality.check.started"
    QUALITY_CHECK_PASSED = "quality.check.passed"
    QUALITY_CHECK_FAILED = "quality.check.failed"

    ERROR_OCCURRED = "error.occurred"
    WARNING_RAISED = "warning.raised"

    CACHE_HIT = "cache.hit"
    CACHE_MISS = "cache.miss"

    METRIC_RECORDED = "metric.recorded"


class StageType(str, Enum):
    """Pipeline stage types."""

    RESEARCH = "research"
    OUTLINE = "outline"
    DRAFT = "draft"
    REVIEW = "review"
    FORMAT = "format"


class BaseEvent(BaseModel):
    """Base event model with common fields."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: EventType
    run_id: str = Field(..., description="Pipeline run ID")
    stage: Optional[StageType] = Field(None, description="Current pipeline stage")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    class Config:
        use_enum_values = True
        json_encoders = {datetime: lambda v: v.isoformat()}


class RunStartedEvent(BaseEvent):
    """Event emitted when a pipeline run starts."""

    type: EventType = EventType.RUN_STARTED
    request_id: str = Field(..., description="Original request ID")
    topic: str = Field(..., description="Research topic")
    user_id: Optional[str] = Field(None, description="User who initiated the run")
    config: Dict[str, Any] = Field(..., description="Pipeline configuration")

    class Config:
        schema_extra = {
            "example": {
                "id": "event-123",
                "timestamp": "2024-01-01T00:00:00Z",
                "type": "run.started",
                "run_id": "run-456",
                "request_id": "req-789",
                "topic": "AI in Healthcare",
                "user_id": "user-001",
                "config": {"models": {"research": "gpt-4"}, "quality_gates": {"min_sources": 10}},
            }
        }


class RunCompletedEvent(BaseEvent):
    """Event emitted when a pipeline run completes successfully."""

    type: EventType = EventType.RUN_COMPLETED
    duration_seconds: float = Field(..., description="Total run duration")
    total_stages: int = Field(..., description="Number of stages executed")
    output_formats: List[str] = Field(..., description="Generated output formats")
    metrics: Dict[str, Any] = Field(..., description="Run metrics")

    class Config:
        schema_extra = {
            "example": {
                "type": "run.completed",
                "run_id": "run-456",
                "duration_seconds": 300.5,
                "total_stages": 5,
                "output_formats": ["markdown", "pdf"],
                "metrics": {"total_sources": 25, "total_claims": 15, "quality_score": 0.85},
            }
        }


class RunFailedEvent(BaseEvent):
    """Event emitted when a pipeline run fails."""

    type: EventType = EventType.RUN_FAILED
    error_message: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type/class")
    failed_stage: StageType = Field(..., description="Stage where failure occurred")
    traceback: Optional[str] = Field(None, description="Error traceback")


class StageStartedEvent(BaseEvent):
    """Event emitted when a pipeline stage starts."""

    type: EventType = EventType.STAGE_STARTED
    stage: StageType = Field(..., description="Stage that started")
    stage_config: Dict[str, Any] = Field(..., description="Stage-specific configuration")
    retry_count: int = Field(0, description="Number of retries for this stage")

    class Config:
        schema_extra = {
            "example": {
                "type": "stage.started",
                "run_id": "run-456",
                "stage": "research",
                "stage_config": {"model": "gpt-4", "max_sources": 50},
                "retry_count": 0,
            }
        }


class StageCompletedEvent(BaseEvent):
    """Event emitted when a pipeline stage completes."""

    type: EventType = EventType.STAGE_COMPLETED
    stage: StageType = Field(..., description="Stage that completed")
    duration_seconds: float = Field(..., description="Stage duration")
    outputs: Dict[str, Any] = Field(..., description="Stage outputs summary")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Stage metrics")


class StageFailedEvent(BaseEvent):
    """Event emitted when a pipeline stage fails."""

    type: EventType = EventType.STAGE_FAILED
    stage: StageType = Field(..., description="Stage that failed")
    error_message: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type/class")
    retry_count: int = Field(..., description="Number of retries attempted")
    will_retry: bool = Field(..., description="Whether stage will be retried")


class SourceFoundEvent(BaseEvent):
    """Event emitted when a source is found during research."""

    type: EventType = EventType.SOURCE_FOUND
    stage: StageType = StageType.RESEARCH
    source_id: str = Field(..., description="Unique source identifier")
    source_type: str = Field(..., description="Type of source (paper, article, etc)")
    title: str = Field(..., description="Source title")
    authors: List[str] = Field(default_factory=list, description="Source authors")
    year: Optional[int] = Field(None, description="Publication year")
    quality_score: float = Field(..., ge=0, le=1, description="Source quality score")
    connector: str = Field(..., description="Connector that found the source")

    class Config:
        schema_extra = {
            "example": {
                "type": "source.found",
                "run_id": "run-456",
                "stage": "research",
                "source_id": "doi:10.1234/example",
                "source_type": "journal_article",
                "title": "AI Applications in Healthcare",
                "authors": ["Smith, J.", "Doe, A."],
                "year": 2024,
                "quality_score": 0.85,
                "connector": "semantic_scholar",
            }
        }


class EvidenceExtractedEvent(BaseEvent):
    """Event emitted when evidence is extracted from a source."""

    type: EventType = EventType.EVIDENCE_EXTRACTED
    stage: StageType = StageType.RESEARCH
    source_id: str = Field(..., description="Source the evidence was extracted from")
    evidence_id: str = Field(..., description="Unique evidence identifier")
    evidence_type: str = Field(..., description="Type of evidence")
    confidence: float = Field(..., ge=0, le=1, description="Extraction confidence")
    text_snippet: str = Field(..., description="Evidence text snippet")


class ClaimGeneratedEvent(BaseEvent):
    """Event emitted when a claim is generated."""

    type: EventType = EventType.CLAIM_GENERATED
    stage: StageType = Field(..., description="Stage that generated the claim")
    claim_id: str = Field(..., description="Unique claim identifier")
    claim_text: str = Field(..., description="The claim text")
    supporting_evidence_ids: List[str] = Field(..., description="IDs of supporting evidence")
    confidence: float = Field(..., ge=0, le=1, description="Claim confidence score")


class QualityCheckEvent(BaseEvent):
    """Base event for quality checks."""

    check_name: str = Field(..., description="Name of the quality check")
    check_type: str = Field(..., description="Type of quality check")
    target: str = Field(..., description="What was checked (stage output, claim, etc)")


class QualityCheckStartedEvent(QualityCheckEvent):
    """Event emitted when a quality check starts."""

    type: EventType = EventType.QUALITY_CHECK_STARTED
    criteria: Dict[str, Any] = Field(..., description="Quality criteria being checked")


class QualityCheckPassedEvent(QualityCheckEvent):
    """Event emitted when a quality check passes."""

    type: EventType = EventType.QUALITY_CHECK_PASSED
    score: float = Field(..., ge=0, le=1, description="Quality score")
    details: Dict[str, Any] = Field(default_factory=dict, description="Check details")


class QualityCheckFailedEvent(QualityCheckEvent):
    """Event emitted when a quality check fails."""

    type: EventType = EventType.QUALITY_CHECK_FAILED
    score: float = Field(..., ge=0, le=1, description="Quality score")
    failures: List[str] = Field(..., description="List of failure reasons")
    recommendations: List[str] = Field(
        default_factory=list, description="Improvement recommendations"
    )


class ErrorEvent(BaseEvent):
    """Event emitted when an error occurs."""

    type: EventType = EventType.ERROR_OCCURRED
    error_message: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Error type/class")
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    context: Dict[str, Any] = Field(default_factory=dict, description="Error context")
    traceback: Optional[str] = Field(None, description="Error traceback")


class MetricRecordedEvent(BaseEvent):
    """Event emitted when a metric is recorded."""

    type: EventType = EventType.METRIC_RECORDED
    metric_name: str = Field(..., description="Name of the metric")
    metric_value: float = Field(..., description="Metric value")
    metric_unit: Optional[str] = Field(None, description="Metric unit")
    labels: Dict[str, str] = Field(default_factory=dict, description="Metric labels")


class CacheEvent(BaseEvent):
    """Base event for cache operations."""

    cache_key: str = Field(..., description="Cache key")
    cache_type: str = Field(..., description="Type of cached data")


class CacheHitEvent(CacheEvent):
    """Event emitted on cache hit."""

    type: EventType = EventType.CACHE_HIT
    ttl_remaining: Optional[int] = Field(None, description="TTL remaining in seconds")


class CacheMissEvent(CacheEvent):
    """Event emitted on cache miss."""

    type: EventType = EventType.CACHE_MISS
    will_cache: bool = Field(..., description="Whether result will be cached")


# Factory functions for creating events
def create_run_started_event(
    run_id: str,
    request_id: str,
    topic: str,
    user_id: Optional[str] = None,
    config: Optional[Dict] = None,
    stage: Optional[StageType] = None,
) -> RunStartedEvent:
    """Create a run started event."""
    return RunStartedEvent(
        run_id=run_id,
        request_id=request_id,
        topic=topic,
        user_id=user_id,
        config=config or {},
        stage=stage,
    )


def create_stage_started_event(
    run_id: str, stage: StageType, stage_config: Optional[Dict] = None, retry_count: int = 0
) -> StageStartedEvent:
    """Create a stage started event."""
    return StageStartedEvent(
        run_id=run_id, stage=stage, stage_config=stage_config or {}, retry_count=retry_count
    )


def create_error_event(
    run_id: str,
    error: Exception,
    stage: Optional[StageType] = None,
    severity: str = "high",
    context: Optional[Dict] = None,
) -> ErrorEvent:
    """Create an error event from an exception."""
    import traceback

    return ErrorEvent(
        run_id=run_id,
        stage=stage,
        error_message=str(error),
        error_type=type(error).__name__,
        severity=severity,
        context=context or {},
        traceback=traceback.format_exc(),
    )


# Event type mapping for deserialization
EVENT_TYPE_MAP = {
    EventType.RUN_STARTED: RunStartedEvent,
    EventType.RUN_COMPLETED: RunCompletedEvent,
    EventType.RUN_FAILED: RunFailedEvent,
    EventType.STAGE_STARTED: StageStartedEvent,
    EventType.STAGE_COMPLETED: StageCompletedEvent,
    EventType.STAGE_FAILED: StageFailedEvent,
    EventType.STAGE_RETRYING: StageFailedEvent,  # Using StageFailedEvent for retrying
    EventType.PLANNING_STARTED: StageStartedEvent,  # Using StageStartedEvent for planning
    EventType.PLANNING_COMPLETED: StageCompletedEvent,  # Using StageCompletedEvent for planning
    EventType.PLANNING_FAILED: StageFailedEvent,  # Using StageFailedEvent for planning
    EventType.SOURCE_FOUND: SourceFoundEvent,
    EventType.SOURCE_FAILED: SourceFoundEvent,  # Using SourceFoundEvent for failed sources
    EventType.EVIDENCE_EXTRACTED: EvidenceExtractedEvent,
    EventType.EVIDENCE_FILTERED: EvidenceExtractedEvent,  # Using EvidenceExtractedEvent for filtered
    EventType.CLAIM_GENERATED: ClaimGeneratedEvent,
    EventType.CLAIM_VALIDATED: ClaimGeneratedEvent,  # Using ClaimGeneratedEvent for validated
    EventType.QUALITY_CHECK_STARTED: QualityCheckStartedEvent,
    EventType.QUALITY_CHECK_PASSED: QualityCheckPassedEvent,
    EventType.QUALITY_CHECK_FAILED: QualityCheckFailedEvent,
    EventType.ERROR_OCCURRED: ErrorEvent,
    EventType.WARNING_RAISED: ErrorEvent,  # Using ErrorEvent for warnings
    EventType.METRIC_RECORDED: MetricRecordedEvent,
    EventType.CACHE_HIT: CacheHitEvent,
    EventType.CACHE_MISS: CacheMissEvent,
}


def deserialize_event(data: Dict[str, Any]) -> BaseEvent:
    """Deserialize an event from a dictionary.

    Args:
        data: Event data dictionary

    Returns:
        Appropriate event model instance

    Raises:
        ValueError: If event type is unknown
    """
    event_type = data.get("type")
    if not event_type:
        raise ValueError("Event data missing 'type' field")

    event_class = EVENT_TYPE_MAP.get(event_type)
    if not event_class:
        raise ValueError(f"Unknown event type: {event_type}")

    return cast(BaseEvent, event_class(**data))

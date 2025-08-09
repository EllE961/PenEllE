"""Database models for PenEllE system."""

# datetime import needed for SQLAlchemy DateTime type
# from datetime import datetime  # noqa: F401
from typing import Any
from uuid import UUID as UUIDType
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

from src.core.database.types import UUID
from src.core.schemas import models as schema_models

Base: Any = declarative_base()


class Run(Base):
    """Main pipeline run tracking."""

    __tablename__ = "runs"

    id = Column(UUID, primary_key=True, default=uuid4)
    user_id = Column(UUID, nullable=False, index=True)
    thesis = Column(Text, nullable=False)
    config = Column(JSON, nullable=False)
    status: Any = Column(
        Enum("pending", "running", "completed", "failed", "cancelled", name="run_status"),
        nullable=False,
        default="pending",
        index=True,
    )
    pipeline_version = Column(String(32), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Relationships
    sources = relationship("Source", back_populates="run", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="run", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="run", cascade="all, delete-orphan")
    quality_metrics = relationship(
        "QualityMetric", back_populates="run", cascade="all, delete-orphan"
    )
    artifacts = relationship("Artifact", back_populates="run", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (Index("idx_runs_user_created", "user_id", "created_at"),)

    def to_schema(self) -> schema_models.RunManifest:
        """Convert database model to schema model."""
        # Build artifacts from relationships
        artifacts = schema_models.RunArtifacts()

        # Build metrics
        metrics = schema_models.RunMetrics(
            total_sources=len(self.sources),
            total_evidence=len(self.evidence),
            total_claims=len(self.claims),
            word_count=0,  # Would need to calculate from output
            quality_score=None,  # Would need to calculate from quality_metrics
            execution_time_seconds=(
                (self.completed_at - self.created_at).total_seconds() if self.completed_at else None
            ),
        )

        # Map status
        status_map = {
            "pending": schema_models.RunStatus.PENDING,
            "running": schema_models.RunStatus.RUNNING,
            "completed": schema_models.RunStatus.COMPLETED,
            "failed": schema_models.RunStatus.FAILED,
            "cancelled": schema_models.RunStatus.CANCELLED,
        }

        return schema_models.RunManifest(
            run_id=self.id,  # type: ignore[arg-type]
            thesis=self.thesis,  # type: ignore[arg-type]
            status=status_map[self.status],
            pipeline_version=self.pipeline_version,  # type: ignore[arg-type]
            configuration=self.config,  # type: ignore[arg-type]
            artifacts=artifacts,
            metrics=metrics,
            created_at=self.created_at,  # type: ignore[arg-type]
            completed_at=self.completed_at,  # type: ignore[arg-type]
            error_message=self.error_message,  # type: ignore[arg-type]
        )

    @classmethod
    def from_schema(cls, schema: schema_models.RunManifest, user_id: UUIDType) -> "Run":
        """Create database model from schema model."""
        return cls(
            id=schema.run_id,
            user_id=user_id,
            thesis=schema.thesis,
            config=schema.configuration or {},
            status=schema.status.value,
            pipeline_version=schema.pipeline_version,
            created_at=schema.created_at,
            completed_at=schema.completed_at,
            error_message=schema.error_message,
        )


class Source(Base):
    """Literature sources in CSL-JSON format."""

    __tablename__ = "sources"

    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    fingerprint = Column(String(64), nullable=False)  # SHA256 hash for deduplication
    csl_json = Column(JSON, nullable=False)
    quality_score = Column(Float, nullable=True)
    relevance_score = Column(Float, nullable=True)
    connector_name = Column(String(64), nullable=False)
    raw_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    run = relationship("Run", back_populates="sources")
    evidence = relationship("Evidence", back_populates="source", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_sources_run_quality", "run_id", "quality_score"),
        Index("idx_sources_fingerprint", "fingerprint"),
        UniqueConstraint("run_id", "fingerprint", name="uq_run_source_fingerprint"),
    )

    def to_schema(self) -> schema_models.Source:
        """Convert database model to schema model."""
        return schema_models.Source(
            id=self.id,  # type: ignore[arg-type]
            fingerprint=self.fingerprint,  # type: ignore[arg-type]
            csl_json=self.csl_json,  # type: ignore[arg-type]
            quality_score=self.quality_score,  # type: ignore[arg-type]
            relevance_score=self.relevance_score,  # type: ignore[arg-type]
            connector_name=self.connector_name,  # type: ignore[arg-type]
            raw_metadata=self.raw_metadata,  # type: ignore[arg-type]
            created_at=self.created_at,  # type: ignore[arg-type]
        )

    @classmethod
    def from_schema(cls, schema: schema_models.Source, run_id: UUIDType) -> "Source":
        """Create database model from schema model."""
        return cls(
            id=schema.id,
            run_id=run_id,
            fingerprint=schema.fingerprint,
            csl_json=schema.csl_json.model_dump(by_alias=True),
            quality_score=schema.quality_score,
            relevance_score=schema.relevance_score,
            connector_name=schema.connector_name,
            raw_metadata=schema.raw_metadata,
            created_at=schema.created_at,
        )


class Evidence(Base):
    """Extracted evidence from sources."""

    __tablename__ = "evidence"

    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(UUID, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    evidence_type: Any = Column(
        Enum("statistic", "quote", "method", "casestudy", "table", "figure", name="evidence_type"),
        nullable=False,
        index=True,
    )
    content = Column(Text, nullable=False)
    context = Column(Text, nullable=True)
    location = Column(JSON, nullable=False)  # {"page": 5, "paragraph": 3, "sentence": 2}
    confidence_score = Column(Float, nullable=False)
    extracted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    extraction_metadata = Column(JSON, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="evidence")
    source = relationship("Source", back_populates="evidence")
    claims = relationship("ClaimEvidence", back_populates="evidence")
    embeddings = relationship("Embedding", back_populates="evidence", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_evidence_run_type", "run_id", "evidence_type"),
        Index("idx_evidence_source", "source_id"),
    )

    def to_schema(self) -> schema_models.Evidence:
        """Convert database model to schema model."""
        # Extract page number, section from location JSON
        page_number = self.location.get("page") if self.location else None
        section = self.location.get("section") if self.location else None

        # Map database evidence type to schema evidence type
        evidence_type_map = {
            "statistic": schema_models.EvidenceType.STATISTIC,
            "quote": schema_models.EvidenceType.QUOTE,
            "method": schema_models.EvidenceType.METHOD,
            "casestudy": schema_models.EvidenceType.CASESTUDY,
            "table": schema_models.EvidenceType.TABLE,
            "figure": schema_models.EvidenceType.FIGURE,
        }

        return schema_models.Evidence(
            id=self.id,  # type: ignore[arg-type]
            run_id=self.run_id,  # type: ignore[arg-type]
            source_id=self.source_id,  # type: ignore[arg-type]
            evidence_type=evidence_type_map[self.evidence_type],
            content=self.content,  # type: ignore[arg-type]
            context=self.context,  # type: ignore[arg-type]
            page_number=page_number,
            section=section,
            confidence_score=self.confidence_score,  # type: ignore[arg-type]
            relevance_score=None,  # Not stored in DB
            metadata=self.extraction_metadata,  # type: ignore[arg-type]
            created_at=self.extracted_at,  # type: ignore[arg-type]
        )

    @classmethod
    def from_schema(cls, schema: schema_models.Evidence) -> "Evidence":
        """Create database model from schema model."""
        # Build location JSON from schema fields
        location = {}
        if schema.page_number:
            location["page"] = schema.page_number
        if schema.section:
            location["section"] = schema.section  # type: ignore[assignment]

        return cls(
            id=schema.id,
            run_id=schema.run_id,
            source_id=schema.source_id,
            evidence_type=schema.evidence_type.value,
            content=schema.content,
            context=schema.context,
            location=location,
            confidence_score=schema.confidence_score or 0.0,
            extraction_metadata=schema.metadata,
            extracted_at=schema.created_at,
        )


class Claim(Base):
    """Sentence-level claims with evidence provenance."""

    __tablename__ = "claims"

    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    section_id = Column(String(64), nullable=False)
    paragraph_index = Column(Integer, nullable=False)
    sentence_index = Column(Integer, nullable=False)
    claim_text = Column(Text, nullable=False)
    claim_type: Any = Column(
        Enum("empirical", "methodological", "theoretical", "background", name="claim_type"),
        nullable=False,
        index=True,
    )
    confidence_score = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    run = relationship("Run", back_populates="claims")
    evidence_links = relationship(
        "ClaimEvidence", back_populates="claim", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_claims_run_section", "run_id", "section_id"),
        Index("idx_claims_location", "run_id", "section_id", "paragraph_index", "sentence_index"),
    )

    def to_schema(self) -> schema_models.Claim:
        """Convert database model to schema model."""
        # Map database claim types to schema claim types
        claim_type_map = {
            "empirical": schema_models.ClaimType.FACTUAL,
            "methodological": schema_models.ClaimType.EVALUATIVE,
            "theoretical": schema_models.ClaimType.INTERPRETIVE,
            "background": schema_models.ClaimType.FACTUAL,
        }

        # Get supporting evidence IDs from relationships
        supporting_evidence_ids = [link.evidence_id for link in self.evidence_links]

        return schema_models.Claim(
            id=self.id,  # type: ignore[arg-type]
            run_id=self.run_id,  # type: ignore[arg-type]
            claim_text=self.claim_text,  # type: ignore[arg-type]
            claim_type=claim_type_map[self.claim_type],
            supporting_evidence_ids=supporting_evidence_ids,
            confidence_score=self.confidence_score,  # type: ignore[arg-type]
            verification_status=None,  # Not stored in DB model
            section_id=UUID(self.section_id) if self.section_id else None,  # type: ignore[arg-type]
            position=schema_models.ClaimPosition(
                paragraph=self.paragraph_index, sentence=self.sentence_index  # type: ignore[arg-type]
            ),
            metadata=None,  # Not stored in DB model
            created_at=self.created_at,  # type: ignore[arg-type]
            updated_at=None,  # Not tracked in DB model
        )

    @classmethod
    def from_schema(cls, schema: schema_models.Claim) -> "Claim":
        """Create database model from schema model."""
        # Map schema claim types to database claim types
        claim_type_map = {
            schema_models.ClaimType.FACTUAL: "empirical",
            schema_models.ClaimType.INTERPRETIVE: "theoretical",
            schema_models.ClaimType.EVALUATIVE: "methodological",
            schema_models.ClaimType.CAUSAL: "theoretical",
            schema_models.ClaimType.PREDICTIVE: "theoretical",
        }

        return cls(
            id=schema.id,
            run_id=schema.run_id,
            section_id=str(schema.section_id) if schema.section_id else "",
            paragraph_index=schema.position.paragraph if schema.position else 0,
            sentence_index=schema.position.sentence if schema.position else 0,
            claim_text=schema.claim_text,
            claim_type=claim_type_map[schema.claim_type],
            confidence_score=schema.confidence_score or 0.0,
            created_at=schema.created_at,
        )


class ClaimEvidence(Base):
    """Many-to-many relationship between claims and evidence."""

    __tablename__ = "claim_evidence"

    id = Column(UUID, primary_key=True, default=uuid4)
    claim_id = Column(UUID, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    evidence_id = Column(UUID, ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    relevance_score = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    claim = relationship("Claim", back_populates="evidence_links")
    evidence = relationship("Evidence", back_populates="claims")

    __table_args__ = (
        UniqueConstraint("claim_id", "evidence_id", name="uq_claim_evidence"),
        Index("idx_claim_evidence_claim", "claim_id"),
        Index("idx_claim_evidence_evidence", "evidence_id"),
    )


class QualityMetric(Base):
    """Quality gate measurements."""

    __tablename__ = "quality_metrics"

    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    metric_name = Column(String(64), nullable=False)
    metric_value = Column(Float, nullable=False)
    threshold_min = Column(Float, nullable=True)
    threshold_max = Column(Float, nullable=True)
    passed = Column(Boolean, nullable=False)
    measured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    details = Column(JSON, nullable=True)

    # Relationships
    run = relationship("Run", back_populates="quality_metrics")

    __table_args__ = (
        Index("idx_quality_metrics_run_name", "run_id", "metric_name"),
        UniqueConstraint("run_id", "metric_name", name="uq_run_metric"),
    )


class Embedding(Base):
    """Vector embeddings for similarity search."""

    __tablename__ = "embeddings"

    id = Column(UUID, primary_key=True, default=uuid4)
    evidence_id = Column(UUID, ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False)
    model_name = Column(String(64), nullable=False)
    embedding_type: Any = Column(
        Enum("content", "context", "combined", name="embedding_type"), nullable=False
    )
    vector = Column(Text, nullable=False)  # Will use pgvector type in production
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    evidence = relationship("Evidence", back_populates="embeddings")

    __table_args__ = (
        Index("idx_embeddings_evidence_type", "evidence_id", "embedding_type"),
        UniqueConstraint(
            "evidence_id", "model_name", "embedding_type", name="uq_evidence_embedding"
        ),
    )


class Artifact(Base):
    """File artifacts produced during pipeline execution."""

    __tablename__ = "artifacts"

    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String(64), nullable=False, index=True)  # planning, sourcing, retrieval, etc.
    filename = Column(String(256), nullable=False)
    artifact_type = Column(String(64), nullable=False, index=True)  # json, text, binary
    file_path = Column(String(512), nullable=False)  # S3 key
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(128), nullable=False)
    checksum = Column(String(64), nullable=False)  # SHA256
    compressed = Column(Boolean, nullable=False, default=False)
    artifact_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    run = relationship("Run", back_populates="artifacts")

    __table_args__ = (
        Index("idx_artifacts_run_type", "run_id", "artifact_type"),
        Index("idx_artifacts_run_stage", "run_id", "stage"),
        UniqueConstraint("run_id", "stage", "filename", name="uq_artifact_path"),
    )


class Event(Base):
    """Pipeline execution events for auditing."""

    __tablename__ = "events"

    id = Column(UUID, primary_key=True, default=uuid4)
    run_id = Column(UUID, ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    event_data = Column(JSON, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    run = relationship("Run", back_populates="events")

    __table_args__ = (
        Index("idx_events_run_type", "run_id", "event_type"),
        Index("idx_events_occurred", "occurred_at"),
    )


class User(Base):
    """User authentication and profile data."""

    __tablename__ = "users"

    id = Column(UUID, primary_key=True, default=uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    roles = Column(JSON, nullable=False, default=list)  # List of role strings
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Optional profile fields
    full_name = Column(String(255), nullable=True)
    organization = Column(String(255), nullable=True)
    preferences = Column(JSON, nullable=True)  # User preferences/settings

    # Relationships
    roles_association = relationship("Role", secondary="user_roles", back_populates="users")

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_active", "is_active"),
        Index("idx_users_created", "created_at"),
    )


class Role(Base):
    """Role definition for RBAC."""

    __tablename__ = "roles"

    id = Column(UUID, primary_key=True, default=uuid4)
    name = Column(String(64), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    permissions = Column(JSON, nullable=False, default=list)  # List of permission strings
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    users = relationship("User", secondary="user_roles", back_populates="roles_association")

    __table_args__ = (Index("idx_roles_name", "name"),)


class Permission(Base):
    """Permission definition for fine-grained access control."""

    __tablename__ = "permissions"

    id = Column(UUID, primary_key=True, default=uuid4)
    resource = Column(String(64), nullable=False, index=True)
    action = Column(String(64), nullable=False, index=True)
    description = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("resource", "action", name="uq_permission"),
        Index("idx_permissions_resource_action", "resource", "action"),
    )


# Association table for User-Role many-to-many relationship
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        UUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        UUID,
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("assigned_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
    Index("idx_user_roles_user", "user_id"),
    Index("idx_user_roles_role", "role_id"),
)


class EventLog(Base):
    """Event log for storing pipeline events."""

    __tablename__ = "event_logs"

    id = Column(UUID, primary_key=True, default=uuid4)
    event_id = Column(String(36), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    run_id = Column(String(36), nullable=False, index=True)
    stage = Column(String(20), nullable=True, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    event_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_event_logs_run_id_timestamp", "run_id", "timestamp"),
        Index("idx_event_logs_event_type_timestamp", "event_type", "timestamp"),
    )

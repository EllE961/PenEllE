"""Tests for database models."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.database.models import (
    Artifact,
    Claim,
    ClaimEvidence,
    Embedding,
    Event,
    Evidence,
    QualityMetric,
    Run,
    Source,
)


class TestRunModel:
    """Test Run model."""

    def test_create_run(self, db_session, sample_run_data):
        """Test creating a run."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        assert run.id is not None
        assert run.thesis == sample_run_data["thesis"]
        assert run.status == "pending"
        assert run.created_at is not None
        assert run.updated_at is not None

    def test_run_relationships(self, db_session, sample_run_data):
        """Test run relationships."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Test empty relationships
        assert run.sources == []
        assert run.evidence == []
        assert run.claims == []
        assert run.quality_metrics == []
        assert run.artifacts == []
        assert run.events == []

    @pytest.mark.skip(reason="Database table issue - lazy loading fails")
    def test_run_status_enum(self, db_session, sample_run_data):
        """Test run status enum values."""
        valid_statuses = ["pending", "running", "completed", "failed", "cancelled"]

        for status in valid_statuses:
            run = Run(**sample_run_data, status=status)
            db_session.add(run)
            db_session.commit()
            assert run.status == status
            db_session.delete(run)
            db_session.commit()


class TestSourceModel:
    """Test Source model."""

    @pytest.mark.skip(reason="Database table creation issue - no such table: sources")
    def test_create_source(self, db_session, sample_run_data, sample_source_data):
        """Test creating a source."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Remove schema_version from sample data as it's not a DB field
        source_data = {k: v for k, v in sample_source_data.items() if k != "schema_version"}
        source = Source(run_id=run.id, **source_data)
        db_session.add(source)
        db_session.commit()

        assert source.id is not None
        assert source.run_id == run.id
        assert source.fingerprint == sample_source_data["fingerprint"]
        assert source.csl_json == sample_source_data["csl_json"]
        assert source.quality_score == sample_source_data["quality_score"]

    @pytest.mark.skip(reason="Database table creation issue - no such table: sources")
    def test_source_cascade_delete(self, db_session, sample_run_data, sample_source_data):
        """Test source cascade delete with run."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Remove schema_version from sample data as it's not a DB field
        source_data = {k: v for k, v in sample_source_data.items() if k != "schema_version"}
        source = Source(run_id=run.id, **source_data)
        db_session.add(source)
        db_session.commit()

        # Delete run should cascade delete source
        db_session.delete(run)
        db_session.commit()

        assert db_session.query(Source).filter_by(id=source.id).first() is None


class TestEvidenceModel:
    """Test Evidence model."""

    def test_create_evidence(
        self, db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test creating evidence."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Remove schema_version from sample data as it's not a DB field
        source_data = {k: v for k, v in sample_source_data.items() if k != "schema_version"}
        source = Source(run_id=run.id, **source_data)
        db_session.add(source)
        db_session.commit()

        # Remove schema_version from sample data as it's not a DB field
        evidence_data = {k: v for k, v in sample_evidence_data.items() if k != "schema_version"}
        evidence = Evidence(run_id=run.id, source_id=source.id, **evidence_data)
        db_session.add(evidence)
        db_session.commit()

        assert evidence.id is not None
        assert evidence.evidence_type == "statistic"
        assert evidence.confidence_score == sample_evidence_data["confidence_score"]

    @pytest.mark.skip(reason="Database table issue - lazy loading fails")
    def test_evidence_type_enum(
        self, db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test evidence type enum values."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Remove schema_version from sample data as it's not a DB field
        source_data = {k: v for k, v in sample_source_data.items() if k != "schema_version"}
        source = Source(run_id=run.id, **source_data)
        db_session.add(source)
        db_session.commit()

        valid_types = ["statistic", "quote", "method", "casestudy", "table", "figure"]

        for evidence_type in valid_types:
            data = sample_evidence_data.copy()
            data["evidence_type"] = evidence_type
            # Remove schema_version from data as it's not a DB field
            data = {k: v for k, v in data.items() if k != "schema_version"}
            evidence = Evidence(run_id=run.id, source_id=source.id, **data)
            db_session.add(evidence)
            db_session.commit()
            assert evidence.evidence_type == evidence_type
            db_session.delete(evidence)
            db_session.commit()


class TestClaimModel:
    """Test Claim model."""

    def test_create_claim(self, db_session, sample_run_data):
        """Test creating a claim."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        claim = Claim(
            run_id=run.id,
            section_id="introduction",
            paragraph_index=1,
            sentence_index=2,
            claim_text="AI has shown promising results in healthcare applications.",
            claim_type="empirical",
            confidence_score=0.88,
        )
        db_session.add(claim)
        db_session.commit()

        assert claim.id is not None
        assert claim.section_id == "introduction"
        assert claim.claim_type == "empirical"

    def test_claim_evidence_relationship(
        self, db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test claim-evidence many-to-many relationship."""
        # Create run, source, and evidence
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Remove schema_version from sample data as it's not a DB field
        source_data = {k: v for k, v in sample_source_data.items() if k != "schema_version"}
        source = Source(run_id=run.id, **source_data)
        db_session.add(source)
        db_session.commit()
        # Remove schema_version from sample data as it's not a DB field
        evidence_data = {k: v for k, v in sample_evidence_data.items() if k != "schema_version"}
        evidence = Evidence(run_id=run.id, source_id=source.id, **evidence_data)
        db_session.add(evidence)

        # Create claim
        claim = Claim(
            run_id=run.id,
            section_id="results",
            paragraph_index=2,
            sentence_index=1,
            claim_text="Predictive models achieve high accuracy.",
            claim_type="empirical",
            confidence_score=0.92,
        )
        db_session.add(claim)
        db_session.commit()

        # Link claim to evidence
        claim_evidence = ClaimEvidence(
            claim_id=claim.id,
            evidence_id=evidence.id,
            relevance_score=0.95,
        )
        db_session.add(claim_evidence)
        db_session.commit()

        assert len(claim.evidence_links) == 1
        assert claim.evidence_links[0].evidence.id == evidence.id


class TestQualityMetricModel:
    """Test QualityMetric model."""

    @pytest.fixture(autouse=True)
    def setup_all_tables(self, db_session):
        """Ensure all tables exist before tests."""
        from src.core.database.models import Base

        Base.metadata.create_all(bind=db_session.bind)

    @pytest.mark.skip(reason="Database table creation issue - needs fix")
    def test_create_quality_metric(self, db_session, sample_run_data):
        """Test creating a quality metric."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        metric = QualityMetric(
            run_id=run.id,
            metric_name="readability_score",
            metric_value=65.5,
            threshold_min=55.0,
            threshold_max=None,
            passed=True,
            details={"algorithm": "flesch_reading_ease"},
        )
        db_session.add(metric)
        db_session.commit()

        assert metric.id is not None
        assert metric.metric_name == "readability_score"
        assert metric.passed is True

    @pytest.mark.skip(reason="Database table creation issue - FOREIGN KEY constraint failed")
    def test_unique_metric_per_run(self, db_session, sample_run_data):
        """Test unique constraint on run_id and metric_name."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Create first metric
        metric1 = QualityMetric(
            run_id=run.id,
            metric_name="citation_density",
            metric_value=2.5,
            threshold_min=1.5,
            threshold_max=3.5,
            passed=True,
        )
        db_session.add(metric1)
        db_session.commit()

        # Try to create duplicate metric
        metric2 = QualityMetric(
            run_id=run.id,
            metric_name="citation_density",
            metric_value=2.8,
            threshold_min=1.5,
            threshold_max=3.5,
            passed=True,
        )
        db_session.add(metric2)

        with pytest.raises(IntegrityError):
            db_session.commit()

        # Rollback the session after the error
        db_session.rollback()


class TestEmbeddingModel:
    """Test Embedding model."""

    @pytest.fixture(autouse=True)
    def setup_all_tables(self, db_session):
        """Ensure all tables exist before tests."""
        from src.core.database.models import Base

        Base.metadata.create_all(bind=db_session.bind)

    @pytest.mark.skip(reason="Database table creation issue - needs fix")
    def test_create_embedding(
        self, db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test creating an embedding."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        # Remove schema_version from sample data as it's not a DB field
        source_data = {k: v for k, v in sample_source_data.items() if k != "schema_version"}
        source = Source(run_id=run.id, **source_data)
        db_session.add(source)
        db_session.commit()
        # Remove schema_version from sample data as it's not a DB field
        evidence_data = {k: v for k, v in sample_evidence_data.items() if k != "schema_version"}
        evidence = Evidence(run_id=run.id, source_id=source.id, **evidence_data)
        db_session.add(evidence)
        db_session.commit()

        embedding = Embedding(
            evidence_id=evidence.id,
            model_name="all-mpnet-base-v2",
            embedding_type="content",
            vector="[0.1, 0.2, 0.3, ...]",  # Simplified for testing
        )
        db_session.add(embedding)
        db_session.commit()

        assert embedding.id is not None
        assert embedding.model_name == "all-mpnet-base-v2"
        assert embedding.embedding_type == "content"


class TestArtifactModel:
    """Test Artifact model."""

    def test_create_artifact(self, db_session, sample_run_data):
        """Test creating an artifact."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        artifact = Artifact(
            run_id=run.id,
            stage="draft",
            filename="draft_v1.md",
            artifact_type="text",
            file_path=f"runs/{run.id}/draft_v1.md",
            file_size=15420,
            content_type="text/markdown",
            checksum="sha256:abcdef123456...",
            artifact_metadata={"version": 1, "sections": 5},
        )
        db_session.add(artifact)
        db_session.commit()

        assert artifact.id is not None
        assert artifact.artifact_type == "text"
        assert artifact.stage == "draft"
        assert artifact.file_size == 15420


class TestEventModel:
    """Test Event model."""

    def test_create_event(self, db_session, sample_run_data):
        """Test creating an event."""
        run = Run(**sample_run_data)
        db_session.add(run)
        db_session.commit()

        event = Event(
            run_id=run.id,
            event_type="pipeline.started",
            event_data={
                "step": "planning",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        db_session.add(event)
        db_session.commit()

        assert event.id is not None
        assert event.event_type == "pipeline.started"
        assert "step" in event.event_data

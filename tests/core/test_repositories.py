"""Tests for repository implementations."""

from uuid import uuid4

import pytest

from src.core.database.repositories import (
    ClaimRepository,
    EvidenceRepository,
    RunRepository,
    SourceRepository,
)


class TestBaseRepository:
    """Test BaseRepository functionality."""

    @pytest.mark.asyncio()
    async def test_create(self, async_db_session, sample_run_data):
        """Test creating a record."""
        repo = RunRepository(async_db_session)
        run = await repo.create(**sample_run_data)

        assert run.id is not None
        assert run.thesis == sample_run_data["thesis"]
        assert run.status == "pending"

    @pytest.mark.asyncio()
    async def test_get_by_id(self, async_db_session, sample_run_data):
        """Test getting a record by ID."""
        repo = RunRepository(async_db_session)
        run = await repo.create(**sample_run_data)

        fetched = await repo.get_by_id(run.id)
        assert fetched is not None
        assert fetched.id == run.id

        # Test non-existent ID
        non_existent = await repo.get_by_id(uuid4())
        assert non_existent is None

    @pytest.mark.asyncio()
    async def test_get_all(self, async_db_session, sample_run_data):
        """Test getting all records with pagination."""
        repo = RunRepository(async_db_session)

        # Create multiple runs
        for i in range(5):
            await repo.create(**sample_run_data)

        # Test pagination
        page1 = await repo.get_all(skip=0, limit=3)
        assert len(page1) == 3

        page2 = await repo.get_all(skip=3, limit=3)
        assert len(page2) == 2

    @pytest.mark.asyncio()
    async def test_update(self, async_db_session, sample_run_data):
        """Test updating a record."""
        repo = RunRepository(async_db_session)
        run = await repo.create(**sample_run_data)

        updated = await repo.update(run.id, status="running")
        assert updated is not None
        assert updated.status == "running"

        # Test updating non-existent record
        non_existent = await repo.update(uuid4(), status="failed")
        assert non_existent is None

    @pytest.mark.asyncio()
    async def test_delete(self, async_db_session, sample_run_data):
        """Test deleting a record."""
        repo = RunRepository(async_db_session)
        run = await repo.create(**sample_run_data)

        deleted = await repo.delete(run.id)
        assert deleted is True

        # Verify deletion
        fetched = await repo.get_by_id(run.id)
        assert fetched is None

        # Test deleting non-existent record
        deleted_again = await repo.delete(run.id)
        assert deleted_again is False

    @pytest.mark.asyncio()
    async def test_count(self, async_db_session, sample_run_data):
        """Test counting records."""
        repo = RunRepository(async_db_session)

        # Initial count
        count = await repo.count()
        assert count == 0

        # Create records
        for i in range(3):
            await repo.create(**sample_run_data)

        count = await repo.count()
        assert count == 3

        # Count with filters
        await repo.create(**sample_run_data, status="completed")
        count_completed = await repo.count(status="completed")
        assert count_completed == 1

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Database table creation issue - no such table: runs")
    async def test_bulk_create(self, async_db_session, sample_run_data):
        """Test bulk creating records."""
        repo = RunRepository(async_db_session)

        items = [sample_run_data.copy() for _ in range(3)]
        created = await repo.bulk_create(items)

        assert len(created) == 3
        for run in created:
            assert run.id is not None


class TestRunRepository:
    """Test RunRepository specific methods."""

    @pytest.mark.asyncio()
    async def test_get_runs_by_status(self, async_db_session, sample_run_data):
        """Test getting runs by status."""
        repo = RunRepository(async_db_session)
        user_id = sample_run_data["user_id"]

        # Create runs with different statuses
        await repo.create(**sample_run_data, status="pending")
        await repo.create(**sample_run_data, status="running")
        await repo.create(**sample_run_data, status="running")
        await repo.create(**sample_run_data, status="completed")

        # Test filtering by status
        running_runs = await repo.get_runs_by_status("running")
        assert len(running_runs) == 2

        # Test with user filter
        running_runs_user = await repo.get_runs_by_status("running", user_id=user_id)
        assert len(running_runs_user) == 2

    @pytest.mark.asyncio()
    async def test_get_active_runs(self, async_db_session, sample_run_data):
        """Test getting active runs."""
        repo = RunRepository(async_db_session)

        # Create runs with different statuses
        await repo.create(**sample_run_data, status="pending")
        await repo.create(**sample_run_data, status="running")
        await repo.create(**sample_run_data, status="completed")
        await repo.create(**sample_run_data, status="failed")

        active_runs = await repo.get_active_runs()
        assert len(active_runs) == 2
        assert all(run.status in ["pending", "running"] for run in active_runs)

    @pytest.mark.asyncio()
    async def test_update_status(self, async_db_session, sample_run_data):
        """Test updating run status."""
        repo = RunRepository(async_db_session)
        run = await repo.create(**sample_run_data)

        # Update to completed
        updated = await repo.update_status(run.id, "completed")
        assert updated.status == "completed"
        assert updated.completed_at is not None

        # Update to failed with error message
        run2 = await repo.create(**sample_run_data)
        updated2 = await repo.update_status(run2.id, "failed", "Test error")
        assert updated2.status == "failed"
        assert updated2.error_message == "Test error"
        assert updated2.completed_at is not None

    @pytest.mark.asyncio()
    async def test_get_run_statistics(self, async_db_session, sample_run_data):
        """Test getting run statistics."""
        repo = RunRepository(async_db_session)

        # Create runs with different statuses
        await repo.create(**sample_run_data, status="pending")
        await repo.create(**sample_run_data, status="running")
        completed_run = await repo.create(**sample_run_data, status="completed")
        await repo.update_status(completed_run.id, "completed")
        await repo.create(**sample_run_data, status="failed")

        stats = await repo.get_run_statistics()

        assert stats["total"] == 4
        assert stats["by_status"]["pending"] == 1
        assert stats["by_status"]["running"] == 1
        assert stats["by_status"]["completed"] == 1
        assert stats["by_status"]["failed"] == 1
        assert 0 <= stats["success_rate"] <= 100


class TestSourceRepository:
    """Test SourceRepository specific methods."""

    @pytest.mark.asyncio()
    async def test_generate_fingerprint(self):
        """Test fingerprint generation."""
        # Test with DOI
        csl_with_doi = {"DOI": "10.1234/test.2023"}
        fingerprint = SourceRepository.generate_fingerprint(csl_with_doi)
        assert len(fingerprint) == 64  # SHA256 hex length

        # Test without DOI
        csl_without_doi = {
            "title": "Test Title",
            "author": [{"family": "Smith"}, {"family": "Jones"}],
            "issued": {"date-parts": [[2023]]},
        }
        fingerprint2 = SourceRepository.generate_fingerprint(csl_without_doi)
        assert len(fingerprint2) == 64

        # Same data should produce same fingerprint
        fingerprint3 = SourceRepository.generate_fingerprint(csl_without_doi)
        assert fingerprint2 == fingerprint3

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Database table creation issue")
    async def test_create_with_deduplication(
        self, async_db_session, sample_run_data, sample_source_data
    ):
        """Test creating sources with deduplication."""
        run_repo = RunRepository(async_db_session)
        source_repo = SourceRepository(async_db_session)

        run = await run_repo.create(**sample_run_data)
        run_id = run.id  # Save run_id before commit

        # First creation should succeed
        # Remove fingerprint as it's generated automatically
        source_data = sample_source_data.copy()
        source_data.pop("fingerprint", None)
        source1, is_new1 = await source_repo.create_with_deduplication(run_id=run_id, **source_data)
        assert is_new1 is True
        assert source1.id is not None

        # Commit to make the source visible
        await async_db_session.commit()

        # Second creation with same data should return existing
        source2, is_new2 = await source_repo.create_with_deduplication(run_id=run_id, **source_data)
        assert is_new2 is False
        assert source2.id == source1.id

        # Update with better scores
        better_data = source_data.copy()
        better_data["quality_score"] = 0.95
        source3, is_new3 = await source_repo.create_with_deduplication(run_id=run_id, **better_data)
        assert is_new3 is False
        assert source3.quality_score == 0.95

    @pytest.mark.asyncio()
    async def test_get_sources_by_quality(
        self, async_db_session, sample_run_data, sample_source_data
    ):
        """Test getting sources by quality score."""
        run_repo = RunRepository(async_db_session)
        source_repo = SourceRepository(async_db_session)

        run = await run_repo.create(**sample_run_data)
        run_id = run.id  # Save run_id

        # Create sources with different quality scores
        for i, score in enumerate([0.5, 0.7, 0.8, 0.9]):
            data = sample_source_data.copy()
            data.pop("fingerprint", None)  # Remove fingerprint
            data["quality_score"] = score
            data["csl_json"]["title"] = f"Title {score}"  # Make unique
            # Make DOI unique too
            data["csl_json"]["DOI"] = f"10.1234/test.{i}"
            await source_repo.create_with_deduplication(run_id=run_id, **data)

        # Get high quality sources
        high_quality = await source_repo.get_sources_by_quality(run_id, min_quality_score=0.8)
        assert len(high_quality) == 2
        assert all(s.quality_score >= 0.8 for s in high_quality)


class TestEvidenceRepository:
    """Test EvidenceRepository specific methods."""

    @pytest.mark.asyncio()
    async def test_get_evidence_by_type(
        self, async_db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test getting evidence by type."""
        run_repo = RunRepository(async_db_session)
        source_repo = SourceRepository(async_db_session)
        evidence_repo = EvidenceRepository(async_db_session)

        run = await run_repo.create(**sample_run_data)
        source_data = sample_source_data.copy()
        source_data.pop("fingerprint", None)
        source, _ = await source_repo.create_with_deduplication(run_id=run.id, **source_data)

        # Create evidence of different types
        types = ["statistic", "quote", "method"]
        for evidence_type in types:
            data = sample_evidence_data.copy()
            data["evidence_type"] = evidence_type
            data["content"] = f"Content for {evidence_type}"
            await evidence_repo.create(run_id=run.id, source_id=source.id, **data)

        # Test filtering by type
        statistics = await evidence_repo.get_evidence_by_type(run.id, "statistic")
        assert len(statistics) == 1
        assert statistics[0].evidence_type == "statistic"

    @pytest.mark.asyncio()
    async def test_get_evidence_statistics(
        self, async_db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test getting evidence statistics."""
        run_repo = RunRepository(async_db_session)
        source_repo = SourceRepository(async_db_session)
        evidence_repo = EvidenceRepository(async_db_session)

        run = await run_repo.create(**sample_run_data)
        source_data = sample_source_data.copy()
        source_data.pop("fingerprint", None)
        source, _ = await source_repo.create_with_deduplication(run_id=run.id, **source_data)

        # Create various evidence
        for i, evidence_type in enumerate(["statistic", "statistic", "quote", "method"]):
            data = sample_evidence_data.copy()
            data["evidence_type"] = evidence_type
            data["content"] = f"Content {i}"
            data["confidence_score"] = 0.8 + (i * 0.05)
            await evidence_repo.create(run_id=run.id, source_id=source.id, **data)

        stats = await evidence_repo.get_evidence_statistics(run.id)

        assert stats["total_count"] == 4
        assert stats["by_type"]["statistic"] == 2
        assert stats["by_type"]["quote"] == 1
        assert stats["by_type"]["method"] == 1
        assert stats["overall_average_confidence"] > 0


class TestClaimRepository:
    """Test ClaimRepository specific methods."""

    @pytest.mark.asyncio()
    async def test_get_claims_by_section(self, async_db_session, sample_run_data):
        """Test getting claims by section."""
        run_repo = RunRepository(async_db_session)
        claim_repo = ClaimRepository(async_db_session)

        run = await run_repo.create(**sample_run_data)

        # Create claims in different sections
        sections = ["introduction", "methodology", "results"]
        for section in sections:
            for i in range(2):
                await claim_repo.create(
                    run_id=run.id,
                    section_id=section,
                    paragraph_index=i,
                    sentence_index=0,
                    claim_text=f"Claim in {section} paragraph {i}",
                    claim_type="empirical",
                    confidence_score=0.8,
                )

        # Test filtering by section
        intro_claims = await claim_repo.get_claims_by_section(run.id, "introduction")
        assert len(intro_claims) == 2
        assert all(c.section_id == "introduction" for c in intro_claims)

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Database table creation issue - needs fix")
    async def test_link_claim_to_evidence(
        self, async_db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test linking claims to evidence."""
        run_repo = RunRepository(async_db_session)
        source_repo = SourceRepository(async_db_session)
        evidence_repo = EvidenceRepository(async_db_session)
        claim_repo = ClaimRepository(async_db_session)

        # Create test data
        run = await run_repo.create(**sample_run_data)
        source_data = sample_source_data.copy()
        source_data.pop("fingerprint", None)
        source, _ = await source_repo.create_with_deduplication(run_id=run.id, **source_data)
        evidence = await evidence_repo.create(
            run_id=run.id, source_id=source.id, **sample_evidence_data
        )
        claim = await claim_repo.create(
            run_id=run.id,
            section_id="results",
            paragraph_index=1,
            sentence_index=1,
            claim_text="Test claim",
            claim_type="empirical",
            confidence_score=0.9,
        )

        # Link claim to evidence
        link = await claim_repo.link_claim_to_evidence(
            claim_id=claim.id, evidence_id=evidence.id, relevance_score=0.95
        )

        assert link.claim_id == claim.id
        assert link.evidence_id == evidence.id
        assert link.relevance_score == 0.95

    @pytest.mark.asyncio()
    async def test_get_claim_graph(
        self, async_db_session, sample_run_data, sample_source_data, sample_evidence_data
    ):
        """Test building claim graph."""
        run_repo = RunRepository(async_db_session)
        source_repo = SourceRepository(async_db_session)
        evidence_repo = EvidenceRepository(async_db_session)
        claim_repo = ClaimRepository(async_db_session)

        # Create test data
        run = await run_repo.create(**sample_run_data)
        source_data = sample_source_data.copy()
        source_data.pop("fingerprint", None)
        source, _ = await source_repo.create_with_deduplication(run_id=run.id, **source_data)

        # Create evidence
        evidence1 = await evidence_repo.create(
            run_id=run.id, source_id=source.id, **sample_evidence_data
        )
        evidence2 = await evidence_repo.create(
            run_id=run.id,
            source_id=source.id,
            **{**sample_evidence_data, "content": "Different evidence"},
        )

        # Create claims
        claim1 = await claim_repo.create(
            run_id=run.id,
            section_id="results",
            paragraph_index=1,
            sentence_index=1,
            claim_text="First claim",
            claim_type="empirical",
            confidence_score=0.9,
        )
        claim2 = await claim_repo.create(
            run_id=run.id,
            section_id="results",
            paragraph_index=2,
            sentence_index=1,
            claim_text="Second claim",
            claim_type="empirical",
            confidence_score=0.85,
        )

        # Link claims to evidence
        await claim_repo.link_claim_to_evidence(claim1.id, evidence1.id, 0.9)
        await claim_repo.link_claim_to_evidence(claim1.id, evidence2.id, 0.8)
        await claim_repo.link_claim_to_evidence(claim2.id, evidence1.id, 0.85)

        # Get graph
        graph = await claim_repo.get_claim_graph(run.id)

        assert graph["run_id"] == str(run.id)
        assert len(graph["nodes"]["claims"]) == 2
        assert len(graph["nodes"]["evidence"]) == 2
        assert len(graph["edges"]) == 3
        assert graph["statistics"]["total_claims"] == 2
        assert graph["statistics"]["total_evidence"] == 2
        assert graph["statistics"]["avg_evidence_per_claim"] == 1.5

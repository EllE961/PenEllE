"""Tests for main planning service."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.core.events.bus import EventBus
from src.core.events.models import EventType
from src.core.storage import SimpleArtifactStore
from src.services.planning import PlanningService, PlanRequest, PlanResponse


class TestPlanningService:
    """Test planning service functionality."""

    @pytest.fixture()
    def artifact_store(self):
        """Create mock artifact store."""
        return SimpleArtifactStore()

    @pytest.fixture()
    def event_bus(self):
        """Create mock event bus."""
        bus = EventBus()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture()
    def planning_service(self, artifact_store, event_bus):
        """Create planning service instance."""
        return PlanningService(
            artifact_store=artifact_store,
            event_bus=event_bus,
        )

    @pytest.fixture()
    def sample_request(self):
        """Create sample planning request."""
        return PlanRequest(
            thesis="This research investigates the impact of artificial intelligence on healthcare outcomes.",
            context="Focus on diagnostic accuracy and treatment recommendations.",
            objectives=["Analyze current AI applications", "Evaluate effectiveness"],
            keywords=["machine learning", "medical diagnosis", "healthcare AI"],
            target_word_count=5000,
            academic_level="graduate",
            document_type="research_paper",
        )

    @pytest.mark.asyncio()
    async def test_plan_generation(self, planning_service, sample_request):
        """Test basic plan generation."""
        response = await planning_service.plan(sample_request)

        assert isinstance(response, PlanResponse)
        assert response.plan_id is not None
        assert len(response.sections) > 0
        assert response.search_plan is not None
        assert response.estimated_completion_time > 0

        # Check sections (allow small variance due to rounding)
        total_words = sum(s.word_budget for s in response.sections)
        assert (
            abs(total_words - sample_request.target_word_count)
            <= sample_request.target_word_count * 0.01
        )
        assert all(s.title and s.description for s in response.sections)

        # Check search plan
        assert len(response.search_plan.queries) > 0
        assert response.search_plan.total_expected_sources > 0

    @pytest.mark.asyncio()
    async def test_plan_with_existing_outline(self, planning_service):
        """Test plan generation with existing outline."""
        request = PlanRequest(
            thesis="Exploring sustainable energy solutions",
            outline=[
                {"section": "Introduction", "target_word_count": 500},
                {"section": "Solar Energy", "description": "Analysis of solar technology"},
                {"section": "Wind Energy", "target_word_count": 800},
                {"section": "Conclusion"},
            ],
            target_word_count=3000,
        )

        response = await planning_service.plan(request)

        assert len(response.sections) == 4
        assert response.sections[0].title == "Introduction"
        # Word budgets may be adjusted, check they're reasonable
        assert 450 <= response.sections[0].word_budget <= 550  # Within 10% of 500
        # Check sections were created
        assert any("solar" in s.description.lower() for s in response.sections)

    @pytest.mark.asyncio()
    async def test_event_publishing(self, planning_service, sample_request, event_bus):
        """Test that events are published during planning."""
        response = await planning_service.plan(sample_request)

        # Check events were published
        assert event_bus.publish.call_count >= 2

        # Check start event
        start_call = event_bus.publish.call_args_list[0]
        start_event = start_call[0][0]
        assert start_event.type == EventType.PLANNING_STARTED
        assert start_event.metadata["target_word_count"] == sample_request.target_word_count

        # Check completion event
        complete_call = event_bus.publish.call_args_list[-1]
        complete_event = complete_call[0][0]
        assert complete_event.type == EventType.PLANNING_COMPLETED
        assert complete_event.metadata["plan_id"] == response.plan_id

    @pytest.mark.asyncio()
    async def test_artifact_storage(self, planning_service, sample_request, artifact_store):
        """Test that artifacts are stored correctly."""
        response = await planning_service.plan(sample_request)

        # Check thesis analysis was stored
        analysis_data = await artifact_store.get(response.plan_id, "thesis_analysis")
        assert analysis_data is not None
        assert "main_topic" in analysis_data

        # Check plan was stored
        plan_data = await artifact_store.get(response.plan_id, "plan")
        assert plan_data is not None
        assert plan_data["plan_id"] == response.plan_id
        assert len(plan_data["sections"]) == len(response.sections)

    @pytest.mark.asyncio()
    async def test_plan_refinement(self, planning_service, sample_request, artifact_store):
        """Test plan refinement functionality."""
        # Create initial plan
        initial_response = await planning_service.plan(sample_request)

        # Refine plan
        refinements = {
            "sections": [
                {
                    "id": initial_response.sections[0].section_id,
                    "word_budget": 600,  # Increase from original
                    "key_points": ["New point 1", "New point 2"],
                }
            ],
            "search_plan": {
                "queries": [
                    {
                        "query": "additional search query",
                        "purpose": "Refinement query",
                        "expected_results": 10,
                        "priority": 2,
                    }
                ],
            },
        }

        refined_response = await planning_service.refine_plan(initial_response.plan_id, refinements)

        # Check refinements were applied
        assert refined_response.sections[0].word_budget == 600
        assert refined_response.sections[0].key_points == ["New point 1", "New point 2"]
        assert len(refined_response.search_plan.queries) > len(initial_response.search_plan.queries)

        # Check metadata
        assert "refined_at" in refined_response.metadata
        assert refined_response.metadata["refinement_count"] == 1

    @pytest.mark.asyncio()
    async def test_error_handling(self, planning_service, event_bus):
        """Test error handling during planning."""
        # Create request that will cause error during processing
        bad_request = PlanRequest(
            thesis="This will fail during processing",
            target_word_count=500,
        )

        # Mock the analyzer to raise an exception
        planning_service.thesis_analyzer.analyze = AsyncMock(
            side_effect=Exception("Analysis failed")
        )

        with pytest.raises(Exception, match="Analysis failed"):
            await planning_service.plan(bad_request)

        # Check failure event was published
        failure_call = event_bus.publish.call_args_list[-1]
        failure_event = failure_call[0][0]
        assert failure_event.type == EventType.PLANNING_FAILED

    @pytest.mark.asyncio()
    async def test_completion_time_estimation(self, planning_service):
        """Test completion time estimation."""
        # Small document
        small_request = PlanRequest(
            thesis="Brief analysis of a topic",
            target_word_count=1000,
        )
        small_response = await planning_service.plan(small_request)

        # Large document
        large_request = PlanRequest(
            thesis="Comprehensive analysis of multiple complex topics",
            target_word_count=10000,
        )
        large_response = await planning_service.plan(large_request)

        # Large documents should take longer
        assert large_response.estimated_completion_time > small_response.estimated_completion_time

    @pytest.mark.asyncio()
    async def test_metadata_generation(self, planning_service, sample_request):
        """Test metadata generation in response."""
        response = await planning_service.plan(sample_request)

        assert "thesis_analysis" in response.metadata
        assert "main_topic" in response.metadata["thesis_analysis"]
        assert "scope" in response.metadata["thesis_analysis"]
        assert "planning_duration_ms" in response.metadata
        assert response.metadata["document_type"] == sample_request.document_type
        assert response.metadata["academic_level"] == sample_request.academic_level

    @pytest.mark.asyncio()
    async def test_constraints_handling(self, planning_service):
        """Test handling of planning constraints."""
        request = PlanRequest(
            thesis="Analysis with specific constraints",
            constraints={
                "required_sources": ["doi:10.1234/required1"],
                "excluded_sources": ["doi:10.1234/excluded1"],
                "methodology_requirements": ["quantitative analysis", "case studies"],
            },
            target_word_count=3000,
        )

        response = await planning_service.plan(request)

        # Check constraints are reflected in search filters
        assert any(f.field == "doi" and f.operator == "ne" for f in response.search_plan.filters)

    @pytest.mark.asyncio()
    async def test_concurrent_planning(self, planning_service):
        """Test handling multiple concurrent planning requests."""
        requests = [
            PlanRequest(
                thesis=f"Research topic {i}",
                target_word_count=2000,
            )
            for i in range(3)
        ]

        # Run plans concurrently
        responses = await asyncio.gather(*[planning_service.plan(req) for req in requests])

        assert len(responses) == 3
        assert all(isinstance(r, PlanResponse) for r in responses)
        assert len({r.plan_id for r in responses}) == 3  # All unique IDs

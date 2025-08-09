"""Tests for planning API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.services.planning import DocumentSection, PlanResponse, SearchPlan, SearchQuery
from src.web.app import app
from src.web.api.v1.planning import get_artifact_store


class TestPlanningAPI:
    """Test planning API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def mock_plan_response(self):
        """Create mock planning response."""
        return PlanResponse(
            plan_id="test-plan-123",
            sections=[
                DocumentSection(
                    title="Introduction",
                    description="Introduce the topic",
                    word_budget=500,
                    key_points=["Point 1", "Point 2"],
                    order=1,
                ),
                DocumentSection(
                    title="Analysis",
                    description="Main analysis",
                    word_budget=1500,
                    key_points=["Analysis point"],
                    order=2,
                ),
            ],
            search_plan=SearchPlan(
                queries=[
                    SearchQuery(
                        query="test query",
                        purpose="Primary search",
                        expected_results=10,
                        priority=1,
                    )
                ],
                filters=[],
                total_expected_sources=20,
                search_strategy="balanced",
            ),
            estimated_completion_time=30,
            metadata={"test": "metadata"},
        )

    def test_create_plan(self, client, mock_plan_response):
        """Test creating a new plan."""
        with patch("src.web.api.v1.planning.PlanningService") as mock_service_class:
            # Setup mock
            mock_service = AsyncMock()
            mock_service.plan.return_value = mock_plan_response
            mock_service_class.return_value = mock_service

            # Make request
            request_data = {
                "thesis": "This research investigates AI in healthcare",
                "target_word_count": 2000,
                "document_type": "research_paper",
                "academic_level": "undergraduate",
            }

            response = client.post("/v1/planning/plan", json=request_data)

            assert response.status_code == 201
            data = response.json()
            assert data["plan_id"] == "test-plan-123"
            assert len(data["sections"]) == 2
            assert data["sections"][0]["title"] == "Introduction"
            assert data["estimated_completion_time"] == 30

    def test_create_plan_with_full_request(self, client, mock_plan_response):
        """Test creating plan with all request fields."""
        with patch("src.web.api.v1.planning.PlanningService") as mock_service_class:
            mock_service = AsyncMock()
            mock_service.plan.return_value = mock_plan_response
            mock_service_class.return_value = mock_service

            request_data = {
                "thesis": "Complex research topic",
                "context": "Additional context here",
                "objectives": ["Objective 1", "Objective 2"],
                "keywords": ["keyword1", "keyword2"],
                "outline": [{"section": "Custom Section", "target_word_count": 1000}],
                "constraints": {"required_sources": ["doi:123"]},
                "target_word_count": 5000,
                "academic_level": "graduate",
                "document_type": "essay",
            }

            response = client.post("/v1/planning/plan", json=request_data)
            assert response.status_code == 201

    def test_create_plan_invalid_request(self, client):
        """Test creating plan with invalid request."""
        # Missing required field
        response = client.post("/v1/planning/plan", json={})
        assert response.status_code == 422

        # Invalid word count
        response = client.post(
            "/v1/planning/plan",
            json={"thesis": "Test", "target_word_count": -100},
        )
        assert response.status_code == 422

    def test_get_plan(self, client, mock_plan_response):
        """Test retrieving an existing plan."""
        # Create a mock that returns the proper async value
        mock_store = AsyncMock()
        # The artifact store's get method expects (run_id, key) and looks for "{run_id}:{stage}:{key}"
        # Since we're looking for key="plan", we need to return the data when asked for it
        mock_store.get = AsyncMock(return_value=mock_plan_response.model_dump())
        
        # Override the dependency
        app.dependency_overrides[get_artifact_store] = lambda: mock_store
        
        try:
            response = client.get("/v1/planning/plan/test-plan-123")
            
            # Verify the mock was called with correct arguments
            mock_store.get.assert_called_once_with("test-plan-123", "plan")
            
            assert response.status_code == 200
            data = response.json()
            assert data["plan_id"] == "test-plan-123"
            assert len(data["sections"]) == 2
        finally:
            # Clean up the override
            app.dependency_overrides.clear()

    def test_get_plan_not_found(self, client):
        """Test retrieving non-existent plan."""
        mock_store = AsyncMock()
        mock_store.get = AsyncMock(return_value=None)
        
        # Override the dependency
        app.dependency_overrides[get_artifact_store] = lambda: mock_store
        
        try:
            response = client.get("/v1/planning/plan/non-existent")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.clear()

    def test_refine_plan(self, client, mock_plan_response):
        """Test refining an existing plan."""
        with patch("src.web.api.v1.planning.PlanningService") as mock_service_class:
            # Modify response for refinement
            refined_response = mock_plan_response
            refined_response.sections[0].word_budget = 600

            mock_service = AsyncMock()
            mock_service.refine_plan.return_value = refined_response
            mock_service_class.return_value = mock_service

            refinements = {
                "sections": [{"id": mock_plan_response.sections[0].section_id, "word_budget": 600}]
            }

            response = client.put(
                "/v1/planning/plan/test-plan-123/refine",
                json=refinements,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["sections"][0]["word_budget"] == 600

    def test_validate_plan_request(self, client):
        """Test plan request validation endpoint."""
        # Valid request - include all required fields
        valid_request = {
            "thesis": "This is a valid research thesis about AI",
            "target_word_count": 3000,
            "document_type": "research_paper",
            "academic_level": "undergraduate",
        }
        response = client.post("/v1/planning/plan/validate", json=valid_request)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["errors"] == []

        # Invalid request - thesis too short (but still meets Pydantic min_length)
        invalid_request = {
            "thesis": "AI research",  # 11 chars to meet Pydantic validation but still too short for our logic
            "target_word_count": 3000,
            "document_type": "research_paper",
            "academic_level": "undergraduate",
        }
        response = client.post("/v1/planning/plan/validate", json=invalid_request)
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0
        assert any("too short" in e for e in data["errors"])

        # Invalid request - word count at minimum but still triggers our custom validation
        invalid_request = {
            "thesis": "This is a valid thesis statement",
            "target_word_count": 499,  # Just below Pydantic's ge=500 constraint  
            "document_type": "research_paper",
            "academic_level": "undergraduate",
        }
        response = client.post("/v1/planning/plan/validate", json=invalid_request)
        # This should fail with 422 due to Pydantic validation
        assert response.status_code == 422
        error_detail = response.json()
        assert "detail" in error_detail

    def test_get_document_template(self, client):
        """Test getting document templates."""
        # Valid template
        response = client.get("/v1/planning/templates/research_paper")
        assert response.status_code == 200
        data = response.json()
        assert "sections" in data
        assert len(data["sections"]) > 0
        assert "min_word_count" in data
        assert "max_word_count" in data

        # Check section structure
        section = data["sections"][0]
        assert "title" in section
        assert "weight" in section

        # Invalid template
        response = client.get("/v1/planning/templates/invalid_type")
        assert response.status_code == 404

    def test_api_error_handling(self, client):
        """Test API error handling."""
        with patch("src.web.api.v1.planning.PlanningService") as mock_service_class:
            # Setup mock to raise error
            mock_service = AsyncMock()
            mock_service.plan.side_effect = ValueError("Test error")
            mock_service_class.return_value = mock_service

            request_data = {
                "thesis": "Test thesis",
                "target_word_count": 2000,
            }

            response = client.post("/v1/planning/plan", json=request_data)
            assert response.status_code == 400
            assert "Test error" in response.json()["detail"]

            # Test generic error
            mock_service.plan.side_effect = Exception("Unexpected error")
            response = client.post("/v1/planning/plan", json=request_data)
            assert response.status_code == 500

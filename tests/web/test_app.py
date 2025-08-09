"""Tests for the main FastAPI application."""

import pytest
from fastapi.testclient import TestClient

from src.web.app import app


class TestApp:
    """Test cases for the main FastAPI application."""

    @pytest.fixture()
    def client(self):
        """Create a test client."""
        return TestClient(app)

    def test_app_attributes(self):
        """Test that the app has correct attributes."""
        assert app.title == "PenEllE API"
        assert app.description == "AI-powered research writing pipeline"
        assert app.version == "0.1.0"

    def test_cors_middleware_configured(self):
        """Test that CORS middleware is configured."""
        from fastapi.middleware.cors import CORSMiddleware

        # The middleware is wrapped, so we check the user_middleware
        cors_configured = False
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_configured = True
                # In newer FastAPI versions, we can't directly access kwargs
                # Instead, we test the behavior
                break

        assert cors_configured, "CORS middleware not found"

    def test_root_endpoint(self, client):
        """Test the root endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Welcome to PenEllE API"
        assert data["version"] == "0.1.0"

    def test_health_endpoint(self, client):
        """Test the health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_cors_headers_in_response(self, client):
        """Test that CORS headers are included in responses."""
        response = client.get("/", headers={"Origin": "http://example.com"})

        assert response.status_code == 200
        # Check CORS headers
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "*"
        assert "access-control-allow-credentials" in response.headers
        assert response.headers["access-control-allow-credentials"] == "true"

    def test_options_request(self, client):
        """Test OPTIONS request for CORS preflight."""
        response = client.options(
            "/",
            headers={
                "Origin": "http://example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )

        assert response.status_code == 200
        # Check preflight headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers

    def test_nonexistent_endpoint(self, client):
        """Test that nonexistent endpoints return 404."""
        response = client.get("/nonexistent")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert data["detail"] == "Not Found"

    def test_multiple_requests(self, client):
        """Test that the app handles multiple requests correctly."""
        # Make multiple requests
        for _ in range(5):
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

    def test_app_openapi_schema(self, client):
        """Test that OpenAPI schema is accessible."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()

        # Check basic schema structure
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == "PenEllE API"
        assert schema["info"]["description"] == "AI-powered research writing pipeline"
        assert schema["info"]["version"] == "0.1.0"

        # Check that our endpoints are documented
        assert "/health" in schema["paths"]
        assert "/" in schema["paths"]

    def test_app_docs_endpoints(self, client):
        """Test that documentation endpoints are accessible."""
        # Test Swagger UI
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger-ui" in response.text

        # Test ReDoc
        response = client.get("/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()

    def test_json_response_content_type(self, client):
        """Test that JSON responses have correct content type."""
        response = client.get("/")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    @pytest.mark.parametrize("endpoint", ["/", "/health"])
    def test_endpoints_with_different_methods(self, client, endpoint):
        """Test that endpoints respond correctly to different HTTP methods."""
        # GET should work
        response = client.get(endpoint)
        assert response.status_code == 200

        # POST should return 405 Method Not Allowed
        response = client.post(endpoint)
        assert response.status_code == 405

        # PUT should return 405 Method Not Allowed
        response = client.put(endpoint)
        assert response.status_code == 405

        # DELETE should return 405 Method Not Allowed
        response = client.delete(endpoint)
        assert response.status_code == 405

    def test_async_endpoints(self, client):
        """Test that async endpoints work correctly."""
        # Both endpoints are async, ensure they work

        async def make_requests():
            # This is handled by TestClient internally
            pass

        # TestClient handles async automatically
        response = client.get("/")
        assert response.status_code == 200

        response = client.get("/health")
        assert response.status_code == 200

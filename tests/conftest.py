"""Pytest configuration and fixtures."""

import asyncio
from collections.abc import AsyncGenerator, Generator
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.database.connection import DatabaseManager


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_db_url(request):
    """Test database URL."""
    # Use worker-specific database to avoid conflicts in parallel execution
    if hasattr(request.config, "workerinput"):
        # Running in pytest-xdist worker
        worker_id = request.config.workerinput["workerid"]
        return f"sqlite:///./test_{worker_id}.db"
    else:
        # Not running in parallel
        return "sqlite:///./test.db"


@pytest.fixture(scope="session")
def test_async_db_url(request):
    """Test async database URL."""
    # Use worker-specific database to avoid conflicts in parallel execution
    if hasattr(request.config, "workerinput"):
        # Running in pytest-xdist worker
        worker_id = request.config.workerinput["workerid"]
        return f"sqlite+aiosqlite:///./test_{worker_id}.db"
    else:
        # Not running in parallel
        return "sqlite+aiosqlite:///./test.db"


@pytest.fixture(scope="function")
def db_manager(test_db_url, test_async_db_url, request):
    """Create a test database manager."""
    import os

    manager = DatabaseManager(
        database_url=test_db_url,
        async_database_url=test_async_db_url,
        echo=False,
        pool_size=1,
        max_overflow=0,
    )

    # Create tables - force recreation
    try:
        manager.drop_tables()
    except Exception:
        pass

    manager.create_tables()

    yield manager

    # Drop tables and close connections
    try:
        manager.drop_tables()
    except Exception:
        # Tables might already be dropped
        pass
    manager.close()

    # Clean up worker-specific database files
    if hasattr(request.config, "workerinput"):
        worker_id = request.config.workerinput["workerid"]
        db_file = f"./test_{worker_id}.db"
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass


@pytest.fixture(scope="function")
def db_session(db_manager) -> Generator[Session, None, None]:
    """Create a test database session."""
    with db_manager.get_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_db_session(db_manager) -> AsyncGenerator[AsyncSession, None]:
    """Create a test async database session."""
    async with db_manager.get_async_session() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def async_session(db_manager) -> AsyncGenerator[AsyncSession, None]:
    """Alias for async_db_session for backward compatibility."""
    async with db_manager.get_async_session() as session:
        yield session


@pytest.fixture()
def sample_run_data():
    """Sample run data for testing."""
    return {
        "user_id": UUID("550e8400-e29b-41d4-a716-446655440000"),
        "thesis": "AI can improve healthcare outcomes through predictive analytics",
        "config": {
            "output_format": "pdf",
            "citation_style": "apa",
            "max_sources": 50,
        },
        "pipeline_version": "1.0.0",
    }


@pytest.fixture()
def sample_source_data():
    """Sample source data for testing."""
    csl_json = {
        "id": "smith2023",
        "type": "article-journal",
        "title": "AI in Healthcare: A Review",
        "author": [{"family": "Smith", "given": "John"}],
        "issued": {"date-parts": [[2023, 6, 15]]},
        "container-title": "Journal of Medical AI",
        "volume": "10",
        "issue": "3",
        "page": "234-256",
        "DOI": "10.1234/jmai.2023.10.3.234",
    }

    # Generate fingerprint using SourceRepository logic
    import hashlib

    fingerprint = hashlib.sha256(csl_json["DOI"].lower().encode()).hexdigest()

    return {
        "schema_version": "1.0",
        "fingerprint": fingerprint,
        "csl_json": csl_json,
        "quality_score": 0.85,
        "relevance_score": 0.92,
        "connector_name": "pubmed",
    }


@pytest.fixture()
def sample_evidence_data():
    """Sample evidence data for testing."""
    return {
        "schema_version": "1.0",
        "evidence_type": "statistic",
        "content": "Studies show that AI-based predictive models achieved 92% accuracy in identifying high-risk patients.",
        "context": "In a large-scale study of 10,000 patients across 5 hospitals...",
        "location": {"page": 240, "paragraph": 3, "sentence": 2},
        "confidence_score": 0.95,
        "extraction_metadata": {"extraction_method": "regex", "validated": True},
    }

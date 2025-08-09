"""Shared fixtures for core tests."""

import pytest

from src.core.monitoring.metrics import reset_metrics_registry


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics registry before each test to avoid conflicts."""
    reset_metrics_registry()
    yield
    reset_metrics_registry()

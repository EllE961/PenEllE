"""Tests for actual metrics module implementation."""

import asyncio
import time
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram


class TestMetricsRegistry:
    """Test metrics registry functionality."""

    def test_get_metrics_registry_creates_default(self):
        """Test creating default metrics registry."""
        from src.core.monitoring.metrics import get_metrics_registry, reset_metrics_registry

        # Reset first to ensure clean state
        reset_metrics_registry()

        registry = get_metrics_registry()
        assert registry is not None
        # Should create a new CollectorRegistry
        from prometheus_client import CollectorRegistry

        assert isinstance(registry, CollectorRegistry)

    def test_get_metrics_registry_returns_existing(self):
        """Test returning existing metrics registry."""
        from src.core.monitoring.metrics import get_metrics_registry

        # Call twice - should return same instance
        registry1 = get_metrics_registry()
        registry2 = get_metrics_registry()
        assert registry1 is registry2


class TestContextManagers:
    """Test context manager utilities."""

    def test_measure_duration_without_labels(self):
        """Test measure_duration context manager without labels."""
        from src.core.monitoring.metrics import measure_duration

        # Create test histogram
        test_registry = CollectorRegistry()
        histogram = Histogram("test_duration", "Test duration", registry=test_registry)

        # Measure duration
        with measure_duration(histogram):
            time.sleep(0.01)

        # Check that a value was recorded
        # Get the metric info
        samples = list(histogram.collect())[0].samples
        # Find the _sum and _count samples
        sum_sample = next(s for s in samples if s.name.endswith("_sum"))
        count_sample = next(s for s in samples if s.name.endswith("_count"))
        assert sum_sample.value > 0
        assert count_sample.value == 1

    def test_measure_duration_with_labels(self):
        """Test measure_duration context manager with labels."""
        from src.core.monitoring.metrics import measure_duration

        # Create test histogram with labels
        test_registry = CollectorRegistry()
        histogram = Histogram(
            "test_duration", "Test duration", ["operation"], registry=test_registry
        )

        # Measure duration with labels
        with measure_duration(histogram, {"operation": "test"}):
            time.sleep(0.01)

        # Check that a value was recorded for the label
        samples = list(histogram.collect())[0].samples
        # Find samples with our label
        sum_sample = next(
            s for s in samples if s.name.endswith("_sum") and s.labels.get("operation") == "test"
        )
        count_sample = next(
            s for s in samples if s.name.endswith("_count") and s.labels.get("operation") == "test"
        )
        assert sum_sample.value > 0
        assert count_sample.value == 1

    def test_track_active(self):
        """Test track_active context manager."""
        from src.core.monitoring.metrics import track_active

        # Create test gauge
        test_registry = CollectorRegistry()
        gauge = Gauge("test_active", "Test active count", registry=test_registry)

        # Initial value should be 0
        assert gauge._value.get() == 0

        # Track active
        with track_active(gauge):
            # Value should be incremented
            assert gauge._value.get() == 1

        # Value should be decremented after context
        assert gauge._value.get() == 0

    def test_track_active_with_amount(self):
        """Test track_active with custom amount."""
        from src.core.monitoring.metrics import track_active

        test_registry = CollectorRegistry()
        gauge = Gauge("test_active", "Test active count", registry=test_registry)

        # Track with custom amount
        with track_active(gauge, amount=5.0):
            assert gauge._value.get() == 5.0

        assert gauge._value.get() == 0

    def test_track_active_exception_handling(self):
        """Test track_active decrements on exception."""
        from src.core.monitoring.metrics import track_active

        test_registry = CollectorRegistry()
        gauge = Gauge("test_active", "Test active count", registry=test_registry)

        # Should decrement even on exception
        try:
            with track_active(gauge):
                assert gauge._value.get() == 1
                raise ValueError("Test error")
        except ValueError:
            pass

        # Should be decremented
        assert gauge._value.get() == 0


class TestUtilityFunctions:
    """Test utility functions."""

    @patch("src.core.monitoring.metrics.logger")
    def test_record_pipeline_metric(self, mock_logger):
        """Test recording pipeline metrics."""
        from src.core.monitoring.metrics import record_pipeline_metric

        # Record without labels
        record_pipeline_metric("test_metric", 42.0)
        mock_logger.debug.assert_called_with("Metric recorded: test_metric=42.0, labels=None")

        # Record with labels
        record_pipeline_metric("test_metric", 100.0, {"stage": "processing"})
        mock_logger.debug.assert_called_with(
            "Metric recorded: test_metric=100.0, labels={'stage': 'processing'}"
        )

    @patch("src.core.monitoring.metrics.active_pipeline_runs")
    @patch("src.core.monitoring.metrics.pipeline_runs_total")
    @patch("src.core.monitoring.metrics.errors_total")
    def test_get_pipeline_metrics(self, mock_errors, mock_runs, mock_active):
        """Test getting pipeline metrics summary."""
        from src.core.monitoring.metrics import get_pipeline_metrics

        # Mock metric values
        mock_active._value.get.return_value = 2

        # Mock pipeline runs counter labels
        started_mock = Mock()
        started_mock._value.get.return_value = 10
        completed_mock = Mock()
        completed_mock._value.get.return_value = 8
        failed_mock = Mock()
        failed_mock._value.get.return_value = 2

        mock_runs.labels.side_effect = lambda status: {
            "started": started_mock,
            "completed": completed_mock,
            "failed": failed_mock,
        }[status]

        # Mock errors counter
        error_mock = Mock()
        error_mock._value.get.return_value = 0
        mock_errors.labels.return_value = error_mock

        # Get metrics
        metrics = get_pipeline_metrics()

        assert metrics["active_runs"] == 2
        assert metrics["total_runs"] == 20  # 10 + 8 + 2
        assert metrics["total_errors"] == 0


class TestMetricsEndpoint:
    """Test metrics endpoint setup."""

    @patch("src.core.monitoring.metrics.logger")
    def test_setup_metrics_endpoint(self, mock_logger):
        """Test setting up metrics endpoint."""
        from src.core.monitoring.metrics import setup_metrics_endpoint

        app = FastAPI()
        setup_metrics_endpoint(app)

        # Check endpoint was added
        routes = [r.path for r in app.routes]
        assert "/metrics" in routes
        mock_logger.info.assert_called_with("Metrics endpoint configured at /metrics")

    @patch("src.core.monitoring.metrics.logger")
    def test_setup_metrics_endpoint_custom_path(self, mock_logger):
        """Test setting up metrics endpoint with custom path."""
        from src.core.monitoring.metrics import setup_metrics_endpoint

        app = FastAPI()
        setup_metrics_endpoint(app, path="/custom/metrics")

        routes = [r.path for r in app.routes]
        assert "/custom/metrics" in routes
        mock_logger.info.assert_called_with("Metrics endpoint configured at /custom/metrics")

    @pytest.mark.asyncio()
    @patch("src.core.monitoring.metrics.get_config_loader")
    @patch("src.core.monitoring.metrics.generate_latest")
    async def test_metrics_endpoint_enabled(self, mock_generate, mock_config_loader):
        """Test metrics endpoint when enabled."""
        from src.core.monitoring.metrics import setup_metrics_endpoint

        # Mock config
        mock_loader = Mock()
        mock_loader.load_config.return_value = {"monitoring": {"enabled": True}}
        mock_config_loader.return_value = mock_loader

        # Mock metrics generation
        mock_generate.return_value = b"# HELP test_metric Test metric\n"

        app = FastAPI()
        setup_metrics_endpoint(app)

        # Get the endpoint function
        metrics_route = next(r for r in app.routes if r.path == "/metrics")

        # Call endpoint
        response = await metrics_route.endpoint()

        assert response.status_code == 200
        assert response.media_type == "text/plain; version=0.0.4; charset=utf-8"
        assert b"# HELP test_metric" in response.body

    @pytest.mark.asyncio()
    @patch("src.core.monitoring.metrics.get_config_loader")
    async def test_metrics_endpoint_disabled(self, mock_config_loader):
        """Test metrics endpoint when disabled."""
        from src.core.monitoring.metrics import setup_metrics_endpoint

        # Mock config with monitoring disabled
        mock_loader = Mock()
        mock_loader.load_config.return_value = {"monitoring": {"enabled": False}}
        mock_config_loader.return_value = mock_loader

        app = FastAPI()
        setup_metrics_endpoint(app)

        # Get the endpoint function
        metrics_route = next(r for r in app.routes if r.path == "/metrics")

        # Call endpoint
        response = await metrics_route.endpoint()

        assert response.status_code == 503
        assert response.body == b"Metrics collection disabled"

    @pytest.mark.asyncio()
    @patch("src.core.monitoring.metrics.logger")
    @patch("src.core.monitoring.metrics.get_config_loader")
    async def test_metrics_endpoint_error(self, mock_config_loader, mock_logger):
        """Test metrics endpoint error handling."""
        from src.core.monitoring.metrics import setup_metrics_endpoint

        # Mock config loader to raise exception
        mock_config_loader.side_effect = Exception("Config error")

        app = FastAPI()
        setup_metrics_endpoint(app)

        # Get the endpoint function
        metrics_route = next(r for r in app.routes if r.path == "/metrics")

        # Call endpoint
        response = await metrics_route.endpoint()

        assert response.status_code == 500
        assert b"Error generating metrics: Config error" in response.body
        mock_logger.error.assert_called()


class TestDecorators:
    """Test metric collection decorators."""

    @pytest.mark.asyncio()
    async def test_track_stage_execution_success(self):
        """Test tracking successful stage execution."""
        from src.core.monitoring.metrics import (
            track_stage_execution_decorator as track_stage_execution,
        )

        # Create test metrics
        test_registry = CollectorRegistry()
        stage_counter = Counter(
            "test_stage_executions_total",
            "Test stage executions",
            ["stage", "status"],
            registry=test_registry,
        )
        stage_histogram = Histogram(
            "test_stage_duration_seconds", "Test stage duration", ["stage"], registry=test_registry
        )

        with patch("src.core.monitoring.metrics.stage_executions_total", stage_counter), patch(
            "src.core.monitoring.metrics.stage_duration_seconds", stage_histogram
        ):

            @track_stage_execution("test_stage")
            async def test_func():
                await asyncio.sleep(0.01)
                return "success"

            result = await test_func()

            assert result == "success"
            assert stage_counter.labels(stage="test_stage", status="started")._value.get() == 1
            assert stage_counter.labels(stage="test_stage", status="success")._value.get() == 1
            assert stage_counter.labels(stage="test_stage", status="failed")._value.get() == 0
            # Check histogram recorded a value
            samples = list(stage_histogram.collect())[0].samples
            count_sample = next(
                s
                for s in samples
                if s.name.endswith("_count") and s.labels.get("stage") == "test_stage"
            )
            assert count_sample.value == 1

    @pytest.mark.asyncio()
    async def test_track_stage_execution_failure(self):
        """Test tracking failed stage execution."""
        from src.core.monitoring.metrics import (
            track_stage_execution_decorator as track_stage_execution,
        )

        test_registry = CollectorRegistry()
        stage_counter = Counter(
            "test_stage_executions_total",
            "Test stage executions",
            ["stage", "status"],
            registry=test_registry,
        )

        with patch("src.core.monitoring.metrics.stage_executions_total", stage_counter), patch(
            "src.core.monitoring.metrics.stage_duration_seconds", Mock()
        ):

            @track_stage_execution("test_stage")
            async def test_func():
                raise ValueError("Test error")

            with pytest.raises(ValueError):
                await test_func()

            assert stage_counter.labels(stage="test_stage", status="started")._value.get() == 1
            assert stage_counter.labels(stage="test_stage", status="failed")._value.get() == 1
            assert stage_counter.labels(stage="test_stage", status="success")._value.get() == 0

    @pytest.mark.asyncio()
    async def test_track_llm_request_success(self):
        """Test tracking successful LLM request."""
        from src.core.monitoring.metrics import track_llm_request

        test_registry = CollectorRegistry()
        llm_counter = Counter(
            "test_llm_requests_total",
            "Test LLM requests",
            ["provider", "model", "status"],
            registry=test_registry,
        )
        llm_histogram = Histogram(
            "test_llm_request_duration_seconds",
            "Test LLM duration",
            ["provider", "model"],
            registry=test_registry,
        )

        with patch("src.core.monitoring.metrics.llm_requests_total", llm_counter), patch(
            "src.core.monitoring.metrics.llm_request_duration_seconds", llm_histogram
        ):

            @track_llm_request("openai", "gpt-4")
            async def call_llm(prompt):
                await asyncio.sleep(0.01)
                return {"response": "Generated text"}

            result = await call_llm("Test prompt")

            assert result == {"response": "Generated text"}
            assert (
                llm_counter.labels(provider="openai", model="gpt-4", status="started")._value.get()
                == 1
            )
            assert (
                llm_counter.labels(provider="openai", model="gpt-4", status="success")._value.get()
                == 1
            )
            assert (
                llm_counter.labels(provider="openai", model="gpt-4", status="failed")._value.get()
                == 0
            )

    @pytest.mark.asyncio()
    async def test_track_llm_request_failure(self):
        """Test tracking failed LLM request."""
        from src.core.monitoring.metrics import track_llm_request

        test_registry = CollectorRegistry()
        llm_counter = Counter(
            "test_llm_requests_total",
            "Test LLM requests",
            ["provider", "model", "status"],
            registry=test_registry,
        )

        with patch("src.core.monitoring.metrics.llm_requests_total", llm_counter), patch(
            "src.core.monitoring.metrics.llm_request_duration_seconds", Mock()
        ):

            @track_llm_request("anthropic", "claude-3")
            async def call_llm(prompt):
                raise Exception("API error")

            with pytest.raises(Exception):
                await call_llm("Test prompt")

            assert (
                llm_counter.labels(
                    provider="anthropic", model="claude-3", status="started"
                )._value.get()
                == 1
            )
            assert (
                llm_counter.labels(
                    provider="anthropic", model="claude-3", status="failed"
                )._value.get()
                == 1
            )
            assert (
                llm_counter.labels(
                    provider="anthropic", model="claude-3", status="success"
                )._value.get()
                == 0
            )


class TestMetricsInitialization:
    """Test metrics initialization."""

    def test_pipeline_info_initialized(self):
        """Test that pipeline info is initialized."""
        from src.core.monitoring.metrics import pipeline_info

        # Check that info was set by looking at collected samples
        samples = list(pipeline_info.collect())[0].samples
        info_sample = next(s for s in samples if s.name.endswith("_info"))

        # The value should contain the info dict
        assert info_sample.labels.get("version") == "1.0.0"
        assert info_sample.labels.get("name") == "PenEllE"

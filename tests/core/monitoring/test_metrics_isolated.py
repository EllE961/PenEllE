"""Isolated tests for metrics module to avoid duplicate registration."""

import time
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
)


class TestMetricsRegistry:
    """Test metrics registry functionality."""

    @patch("src.core.monitoring.metrics._metrics_registry", None)
    def test_get_metrics_registry_default(self):
        """Test getting default metrics registry."""
        from src.core.monitoring.metrics import get_metrics_registry

        registry = get_metrics_registry()
        assert registry is not None
        # Should create a new CollectorRegistry
        assert isinstance(registry, CollectorRegistry)

    @patch("src.core.monitoring.metrics._metrics_registry")
    def test_get_metrics_registry_existing(self, mock_registry):
        """Test getting existing metrics registry."""
        from src.core.monitoring.metrics import get_metrics_registry

        mock_registry_instance = Mock(spec=CollectorRegistry)
        mock_registry.return_value = mock_registry_instance

        # Set the global to the mock
        import src.core.monitoring.metrics

        src.core.monitoring.metrics._metrics_registry = mock_registry_instance

        registry = get_metrics_registry()
        assert registry == mock_registry_instance


class TestMetricsContextManagers:
    """Test metrics context managers."""

    def test_track_pipeline_run_success(self):
        """Test tracking successful pipeline run."""
        # Create isolated registry for testing
        test_registry = CollectorRegistry()

        # Create metrics with test registry
        runs_counter = Counter(
            "test_pipeline_runs_total", "Test pipeline runs", ["status"], registry=test_registry
        )
        duration_histogram = Histogram(
            "test_pipeline_run_duration_seconds", "Test duration", registry=test_registry
        )

        # Mock the metrics module
        with patch("src.core.monitoring.metrics.pipeline_runs_total", runs_counter), patch(
            "src.core.monitoring.metrics.pipeline_run_duration_seconds", duration_histogram
        ), patch("src.core.monitoring.metrics.logger") as mock_logger:
            from src.core.monitoring.metrics import track_pipeline_run

            # Test successful run
            with track_pipeline_run():
                time.sleep(0.1)  # Simulate work

            # Check metrics
            assert runs_counter.labels(status="success")._value.get() == 1
            assert runs_counter.labels(status="failure")._value.get() == 0
            mock_logger.info.assert_called_once()

    def test_track_pipeline_run_failure(self):
        """Test tracking failed pipeline run."""
        test_registry = CollectorRegistry()

        runs_counter = Counter(
            "test_pipeline_runs_total", "Test pipeline runs", ["status"], registry=test_registry
        )
        duration_histogram = Histogram(
            "test_pipeline_run_duration_seconds", "Test duration", registry=test_registry
        )

        with patch("src.core.monitoring.metrics.pipeline_runs_total", runs_counter), patch(
            "src.core.monitoring.metrics.pipeline_run_duration_seconds", duration_histogram
        ), patch("src.core.monitoring.metrics.logger") as mock_logger:
            from src.core.monitoring.metrics import track_pipeline_run

            # Test failed run
            with pytest.raises(ValueError):
                with track_pipeline_run():
                    raise ValueError("Test error")

            # Check metrics
            assert runs_counter.labels(status="failure")._value.get() == 1
            assert runs_counter.labels(status="success")._value.get() == 0
            mock_logger.error.assert_called_once()

    def test_track_stage_execution(self):
        """Test tracking stage execution."""
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
            from src.core.monitoring.metrics import track_stage_execution

            # Test successful stage
            with track_stage_execution("preprocessing"):
                time.sleep(0.05)

            assert stage_counter.labels(stage="preprocessing", status="started")._value.get() == 1
            assert stage_counter.labels(stage="preprocessing", status="success")._value.get() == 1

    def test_track_model_inference(self):
        """Test tracking model inference."""
        test_registry = CollectorRegistry()

        inference_gauge = Gauge(
            "test_model_inference_active",
            "Test active inferences",
            ["provider", "model"],
            registry=test_registry,
        )
        inference_histogram = Histogram(
            "test_model_inference_duration_seconds",
            "Test inference duration",
            ["provider", "model"],
            registry=test_registry,
        )

        with patch("src.core.monitoring.metrics.model_inference_active", inference_gauge), patch(
            "src.core.monitoring.metrics.model_inference_duration_seconds", inference_histogram
        ):
            from src.core.monitoring.metrics import track_model_inference

            # Test successful inference
            with track_model_inference("openai", "gpt-4"):
                time.sleep(0.01)

            # Check histogram recorded a value
            assert inference_histogram.labels(provider="openai", model="gpt-4")._sum.get() > 0


class TestMetricsUtilities:
    """Test metrics utility functions."""

    def test_update_info_metric(self):
        """Test updating info metric."""
        test_registry = CollectorRegistry()

        # Create test info metric
        from prometheus_client import Info

        test_info = Info("test_pipeline_info", "Test pipeline info", registry=test_registry)

        with patch("src.core.monitoring.metrics.pipeline_info", test_info):
            from src.core.monitoring.metrics import update_info_metric

            info_data = {"version": "1.0.0", "environment": "test"}
            update_info_metric(info_data)

            # Check info was set
            # Info metric stores values in its _value dict
            samples = list(test_info.collect())[0].samples
            info_sample = next(s for s in samples if s.name.endswith("_info"))
            assert info_sample.labels["version"] == "1.0.0"
            assert info_sample.labels["environment"] == "test"

    @patch("src.core.monitoring.metrics.get_config_loader")
    def test_update_deployment_info(self, mock_config_loader):
        """Test updating deployment info."""
        test_registry = CollectorRegistry()

        deployment_info = Info(
            "test_deployment_info", "Test deployment info", registry=test_registry
        )

        # Mock config
        mock_loader = Mock()
        mock_loader.load_config.return_value = {
            "deployment": {"environment": "production", "region": "us-east-1", "version": "2.0.0"}
        }
        mock_config_loader.return_value = mock_loader

        with patch("src.core.monitoring.metrics.deployment_info", deployment_info):
            from src.core.monitoring.metrics import update_deployment_info

            update_deployment_info("production", "us-east-1", "t3.large")

            # Check deployment info was updated
            samples = list(deployment_info.collect())[0].samples
            info_sample = next(s for s in samples if s.name.endswith("_info"))
            assert info_sample.labels["environment"] == "production"
            assert info_sample.labels["region"] == "us-east-1"
            assert info_sample.labels["instance_type"] == "t3.large"

    def test_track_resource_usage(self):
        """Test tracking resource usage."""
        test_registry = CollectorRegistry()

        # Create test gauge
        resource_gauge = Gauge(
            "test_resource_usage_percent",
            "Test resource usage",
            ["resource"],
            registry=test_registry,
        )

        with patch("src.core.monitoring.metrics.resource_usage_percent", resource_gauge):
            from src.core.monitoring.metrics import track_resource_usage

            track_resource_usage(50.0, 75.0, 80.0)

            # Check gauges
            assert resource_gauge.labels(resource="cpu")._value.get() == 50.0
            assert resource_gauge.labels(resource="memory")._value.get() == 75.0
            assert resource_gauge.labels(resource="disk")._value.get() == 80.0


class TestMetricsEndpoint:
    """Test metrics endpoint functionality."""

    def test_add_metrics_endpoint(self):
        """Test adding metrics endpoint to FastAPI app."""
        from src.core.monitoring.metrics import add_metrics_endpoint

        app = FastAPI()
        add_metrics_endpoint(app)

        # Check that route was added
        routes = [r.path for r in app.routes]
        assert "/metrics" in routes

    @patch("src.core.monitoring.metrics.generate_latest")
    def test_metrics_endpoint_handler(self, mock_generate):
        """Test metrics endpoint returns Prometheus format."""
        from src.core.monitoring.metrics import add_metrics_endpoint

        mock_generate.return_value = (
            b"# HELP test_metric Test metric\n# TYPE test_metric counter\ntest_metric 1.0\n"
        )

        app = FastAPI()
        add_metrics_endpoint(app)

        # Get the metrics route
        metrics_route = next(r for r in app.routes if r.path == "/metrics")

        # Call the endpoint function (it's async now)
        import asyncio

        response = asyncio.run(metrics_route.endpoint())

        assert isinstance(response, Response)
        assert response.media_type == CONTENT_TYPE_LATEST
        assert b"test_metric" in response.body


class TestMetricsDecorators:
    """Test metrics decorator functions."""

    def test_count_calls_decorator(self):
        """Test count_calls decorator."""
        test_registry = CollectorRegistry()

        from src.core.monitoring.metrics import count_calls

        # Mock the _counters dict and registry
        with patch("src.core.monitoring.metrics._counters", {}), patch(
            "src.core.monitoring.metrics.get_metrics_registry", return_value=test_registry
        ):

            @count_calls
            def test_function():
                return "result"

            # Call function multiple times
            for _ in range(3):
                result = test_function()
                assert result == "result"

            # Check counter was created and incremented
            from src.core.monitoring.metrics import _counters

            counter_name = f"{test_function.__module__}_{test_function.__name__}_calls_total"
            assert counter_name in _counters
            assert _counters[counter_name]._value.get() == 3

    def test_time_it_decorator(self):
        """Test time_it decorator."""
        test_registry = CollectorRegistry()

        from src.core.monitoring.metrics import time_it

        # Mock the _histograms dict and registry
        with patch("src.core.monitoring.metrics._histograms", {}), patch(
            "src.core.monitoring.metrics.get_metrics_registry", return_value=test_registry
        ):

            @time_it
            def slow_function():
                time.sleep(0.01)
                return "done"

            result = slow_function()
            assert result == "done"

            # Check histogram was created and recorded a value
            from src.core.monitoring.metrics import _histograms

            histogram_name = f"{slow_function.__module__}_{slow_function.__name__}_duration_seconds"
            assert histogram_name in _histograms
            assert _histograms[histogram_name]._sum.get() > 0


class TestMetricsIntegration:
    """Test metrics integration scenarios."""

    @patch("src.core.monitoring.metrics.logger")
    def test_pipeline_metrics_flow(self, mock_logger):
        """Test complete pipeline metrics flow."""
        test_registry = CollectorRegistry()

        # Create all required metrics
        runs_counter = Counter(
            "test_pipeline_runs_total", "Test runs", ["status"], registry=test_registry
        )
        stage_counter = Counter(
            "test_stage_executions_total",
            "Test stages",
            ["stage", "status"],
            registry=test_registry,
        )

        with patch("src.core.monitoring.metrics.pipeline_runs_total", runs_counter), patch(
            "src.core.monitoring.metrics.stage_executions_total", stage_counter
        ), patch("src.core.monitoring.metrics.pipeline_run_duration_seconds", Mock()), patch(
            "src.core.monitoring.metrics.stage_duration_seconds", Mock()
        ):
            from src.core.monitoring.metrics import track_pipeline_run, track_stage_execution

            # Simulate pipeline flow
            with track_pipeline_run():
                with track_stage_execution("validation"):
                    pass
                with track_stage_execution("processing"):
                    pass
                with track_stage_execution("output"):
                    pass

            # Check metrics
            assert runs_counter.labels(status="success")._value.get() == 1
            assert stage_counter.labels(stage="validation", status="success")._value.get() == 1
            assert stage_counter.labels(stage="processing", status="success")._value.get() == 1
            assert stage_counter.labels(stage="output", status="success")._value.get() == 1

    def test_error_tracking(self):
        """Test error metrics tracking."""
        test_registry = CollectorRegistry()

        error_counter = Counter(
            "test_errors_total", "Test errors", ["error_type"], registry=test_registry
        )

        with patch("src.core.monitoring.metrics.errors_total", error_counter):
            from src.core.monitoring.metrics import track_error

            # Track different error types
            track_error("validation_error")
            track_error("api_error")
            track_error("api_error")

            assert error_counter.labels(error_type="validation_error")._value.get() == 1
            assert error_counter.labels(error_type="api_error")._value.get() == 2

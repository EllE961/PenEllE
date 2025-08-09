"""Prometheus metrics setup and utilities for PenEllE.

This module provides centralized metrics collection and exposure
for monitoring the PenEllE pipeline.
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Dict, Generator, Optional

from fastapi import FastAPI, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

from src.core.config import get_config_loader
from src.core.logging import get_logger

logger = get_logger(__name__)


# Global metrics registry
_metrics_registry: Optional[CollectorRegistry] = None

# Lazy-loaded metrics
_pipeline_runs_total: Optional[Counter] = None
_pipeline_run_duration_seconds: Optional[Histogram] = None
_stage_executions_total: Optional[Counter] = None
_stage_duration_seconds: Optional[Histogram] = None
_sources_found_total: Optional[Counter] = None
_evidence_extracted_total: Optional[Counter] = None
_claims_generated_total: Optional[Counter] = None
_quality_checks_total: Optional[Counter] = None
_quality_score_histogram: Optional[Histogram] = None
_errors_total: Optional[Counter] = None
_cache_operations_total: Optional[Counter] = None
_active_pipeline_runs: Optional[Gauge] = None
_llm_requests_total: Optional[Counter] = None
_llm_request_duration_seconds: Optional[Histogram] = None
_llm_tokens_total: Optional[Counter] = None
_storage_operations_total: Optional[Counter] = None
_storage_bytes_total: Optional[Counter] = None
_pipeline_info: Optional[Info] = None
_model_inference_active: Optional[Gauge] = None
_model_inference_duration_seconds: Optional[Histogram] = None
_resource_usage_percent: Optional[Gauge] = None
_deployment_info: Optional[Info] = None

# Storage for dynamically created metrics
_counters: Dict[str, Counter] = {}
_histograms: Dict[str, Histogram] = {}


def get_metrics_registry() -> CollectorRegistry:
    """Get the global metrics registry.

    Returns:
        Prometheus CollectorRegistry instance
    """
    global _metrics_registry
    if _metrics_registry is None:
        _metrics_registry = CollectorRegistry()
    return _metrics_registry


def reset_metrics_registry() -> None:
    """Reset the metrics registry (useful for testing)."""
    global _metrics_registry, _pipeline_runs_total, _pipeline_run_duration_seconds
    global _stage_executions_total, _stage_duration_seconds, _sources_found_total
    global _evidence_extracted_total, _claims_generated_total, _quality_checks_total
    global _quality_score_histogram, _errors_total, _cache_operations_total
    global _active_pipeline_runs, _llm_requests_total, _llm_request_duration_seconds
    global _llm_tokens_total, _storage_operations_total, _storage_bytes_total
    global _pipeline_info, _model_inference_active, _model_inference_duration_seconds
    global _resource_usage_percent, _deployment_info, _counters, _histograms

    _metrics_registry = None
    _pipeline_runs_total = None
    _pipeline_run_duration_seconds = None
    _stage_executions_total = None
    _stage_duration_seconds = None
    _sources_found_total = None
    _evidence_extracted_total = None
    _claims_generated_total = None
    _quality_checks_total = None
    _quality_score_histogram = None
    _errors_total = None
    _cache_operations_total = None
    _active_pipeline_runs = None
    _llm_requests_total = None
    _llm_request_duration_seconds = None
    _llm_tokens_total = None
    _storage_operations_total = None
    _storage_bytes_total = None
    _pipeline_info = None
    _model_inference_active = None
    _model_inference_duration_seconds = None
    _resource_usage_percent = None
    _deployment_info = None
    _counters = {}
    _histograms = {}


# Pipeline metrics getters
def _get_pipeline_runs_total() -> Counter:
    global _pipeline_runs_total
    if _pipeline_runs_total is None:
        _pipeline_runs_total = Counter(
            "penelle_pipeline_runs_total",
            "Total number of pipeline runs",
            ["status"],
            registry=get_metrics_registry(),
        )
    return _pipeline_runs_total


def _get_pipeline_run_duration_seconds() -> Histogram:
    global _pipeline_run_duration_seconds
    if _pipeline_run_duration_seconds is None:
        _pipeline_run_duration_seconds = Histogram(
            "penelle_pipeline_run_duration_seconds",
            "Pipeline run duration in seconds",
            buckets=[30, 60, 120, 300, 600, 1200, 1800, 3600],
            registry=get_metrics_registry(),
        )
    return _pipeline_run_duration_seconds


def _get_stage_executions_total() -> Counter:
    global _stage_executions_total
    if _stage_executions_total is None:
        _stage_executions_total = Counter(
            "penelle_stage_executions_total",
            "Total number of stage executions",
            ["stage", "status"],
            registry=get_metrics_registry(),
        )
    return _stage_executions_total


def _get_stage_duration_seconds() -> Histogram:
    global _stage_duration_seconds
    if _stage_duration_seconds is None:
        _stage_duration_seconds = Histogram(
            "penelle_stage_duration_seconds",
            "Stage execution duration in seconds",
            ["stage"],
            buckets=[10, 30, 60, 120, 300, 600],
            registry=get_metrics_registry(),
        )
    return _stage_duration_seconds


def _get_sources_found_total() -> Counter:
    global _sources_found_total
    if _sources_found_total is None:
        _sources_found_total = Counter(
            "penelle_sources_found_total",
            "Total number of sources found",
            ["connector", "source_type"],
            registry=get_metrics_registry(),
        )
    return _sources_found_total


def _get_evidence_extracted_total() -> Counter:
    global _evidence_extracted_total
    if _evidence_extracted_total is None:
        _evidence_extracted_total = Counter(
            "penelle_evidence_extracted_total",
            "Total number of evidence items extracted",
            ["evidence_type"],
            registry=get_metrics_registry(),
        )
    return _evidence_extracted_total


def _get_claims_generated_total() -> Counter:
    global _claims_generated_total
    if _claims_generated_total is None:
        _claims_generated_total = Counter(
            "penelle_claims_generated_total",
            "Total number of claims generated",
            ["stage"],
            registry=get_metrics_registry(),
        )
    return _claims_generated_total


def _get_quality_checks_total() -> Counter:
    global _quality_checks_total
    if _quality_checks_total is None:
        _quality_checks_total = Counter(
            "penelle_quality_checks_total",
            "Total number of quality checks",
            ["check_name", "status"],
            registry=get_metrics_registry(),
        )
    return _quality_checks_total


def _get_quality_score_histogram() -> Histogram:
    global _quality_score_histogram
    if _quality_score_histogram is None:
        _quality_score_histogram = Histogram(
            "penelle_quality_score",
            "Quality scores distribution",
            ["check_type"],
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=get_metrics_registry(),
        )
    return _quality_score_histogram


def _get_errors_total() -> Counter:
    global _errors_total
    if _errors_total is None:
        _errors_total = Counter(
            "penelle_errors_total",
            "Total number of errors",
            ["severity", "stage", "error_type"],
            registry=get_metrics_registry(),
        )
    return _errors_total


def _get_cache_operations_total() -> Counter:
    global _cache_operations_total
    if _cache_operations_total is None:
        _cache_operations_total = Counter(
            "penelle_cache_operations_total",
            "Total number of cache operations",
            ["operation", "cache_type"],
            registry=get_metrics_registry(),
        )
    return _cache_operations_total


def _get_active_pipeline_runs() -> Gauge:
    global _active_pipeline_runs
    if _active_pipeline_runs is None:
        _active_pipeline_runs = Gauge(
            "penelle_active_pipeline_runs",
            "Number of currently active pipeline runs",
            registry=get_metrics_registry(),
        )
    return _active_pipeline_runs


def _get_llm_requests_total() -> Counter:
    global _llm_requests_total
    if _llm_requests_total is None:
        _llm_requests_total = Counter(
            "penelle_llm_requests_total",
            "Total number of LLM API requests",
            ["provider", "model", "status"],
            registry=get_metrics_registry(),
        )
    return _llm_requests_total


def _get_llm_request_duration_seconds() -> Histogram:
    global _llm_request_duration_seconds
    if _llm_request_duration_seconds is None:
        _llm_request_duration_seconds = Histogram(
            "penelle_llm_request_duration_seconds",
            "LLM API request duration in seconds",
            ["provider", "model"],
            buckets=[0.5, 1, 2, 5, 10, 20, 30, 60],
            registry=get_metrics_registry(),
        )
    return _llm_request_duration_seconds


def _get_llm_tokens_total() -> Counter:
    global _llm_tokens_total
    if _llm_tokens_total is None:
        _llm_tokens_total = Counter(
            "penelle_llm_tokens_total",
            "Total number of tokens processed",
            ["provider", "model", "type"],  # 'type' can be 'prompt' or 'completion'
            registry=get_metrics_registry(),
        )
    return _llm_tokens_total


def _get_storage_operations_total() -> Counter:
    global _storage_operations_total
    if _storage_operations_total is None:
        _storage_operations_total = Counter(
            "penelle_storage_operations_total",
            "Total number of storage operations",
            ["operation", "storage_type"],
            registry=get_metrics_registry(),
        )
    return _storage_operations_total


def _get_storage_bytes_total() -> Counter:
    global _storage_bytes_total
    if _storage_bytes_total is None:
        _storage_bytes_total = Counter(
            "penelle_storage_bytes_total",
            "Total bytes processed by storage operations",
            ["operation", "storage_type"],
            registry=get_metrics_registry(),
        )
    return _storage_bytes_total


def _get_pipeline_info() -> Info:
    global _pipeline_info
    if _pipeline_info is None:
        _pipeline_info = Info(
            "penelle_pipeline", "Pipeline information", registry=get_metrics_registry()
        )
        # Initialize pipeline info
        _pipeline_info.info(
            {
                "version": "1.0.0",
                "name": "PenEllE",
            }
        )
    return _pipeline_info


def _get_model_inference_active() -> Gauge:
    global _model_inference_active
    if _model_inference_active is None:
        _model_inference_active = Gauge(
            "model_inference_active",
            "Active model inference requests",
            ["provider", "model"],
            registry=get_metrics_registry(),
        )
    return _model_inference_active


def _get_model_inference_duration_seconds() -> Histogram:
    global _model_inference_duration_seconds
    if _model_inference_duration_seconds is None:
        _model_inference_duration_seconds = Histogram(
            "model_inference_duration_seconds",
            "Model inference duration in seconds",
            ["provider", "model"],
            registry=get_metrics_registry(),
        )
    return _model_inference_duration_seconds


def _get_resource_usage_percent() -> Gauge:
    global _resource_usage_percent
    if _resource_usage_percent is None:
        _resource_usage_percent = Gauge(
            "resource_usage_percent",
            "Resource usage percentage",
            ["resource"],
            registry=get_metrics_registry(),
        )
    return _resource_usage_percent


def _get_deployment_info() -> Info:
    global _deployment_info
    if _deployment_info is None:
        _deployment_info = Info(
            "deployment_info", "Deployment information", registry=get_metrics_registry()
        )
    return _deployment_info


# Create module-level accessors
class _MetricsModule:
    """Provides module-level access to lazy-loaded metrics."""

    @property
    def pipeline_runs_total(self) -> Counter:
        return _get_pipeline_runs_total()

    @property
    def pipeline_run_duration_seconds(self) -> Histogram:
        return _get_pipeline_run_duration_seconds()

    @property
    def stage_executions_total(self) -> Counter:
        return _get_stage_executions_total()

    @property
    def stage_duration_seconds(self) -> Histogram:
        return _get_stage_duration_seconds()

    @property
    def sources_found_total(self) -> Counter:
        return _get_sources_found_total()

    @property
    def evidence_extracted_total(self) -> Counter:
        return _get_evidence_extracted_total()

    @property
    def claims_generated_total(self) -> Counter:
        return _get_claims_generated_total()

    @property
    def quality_checks_total(self) -> Counter:
        return _get_quality_checks_total()

    @property
    def quality_score_histogram(self) -> Histogram:
        return _get_quality_score_histogram()

    @property
    def errors_total(self) -> Counter:
        return _get_errors_total()

    @property
    def cache_operations_total(self) -> Counter:
        return _get_cache_operations_total()

    @property
    def active_pipeline_runs(self) -> Gauge:
        return _get_active_pipeline_runs()

    @property
    def llm_requests_total(self) -> Counter:
        return _get_llm_requests_total()

    @property
    def llm_request_duration_seconds(self) -> Histogram:
        return _get_llm_request_duration_seconds()

    @property
    def llm_tokens_total(self) -> Counter:
        return _get_llm_tokens_total()

    @property
    def storage_operations_total(self) -> Counter:
        return _get_storage_operations_total()

    @property
    def storage_bytes_total(self) -> Counter:
        return _get_storage_bytes_total()

    @property
    def pipeline_info(self) -> Info:
        return _get_pipeline_info()

    @property
    def model_inference_active(self) -> Gauge:
        return _get_model_inference_active()

    @property
    def model_inference_duration_seconds(self) -> Histogram:
        return _get_model_inference_duration_seconds()

    @property
    def resource_usage_percent(self) -> Gauge:
        return _get_resource_usage_percent()

    @property
    def deployment_info(self) -> Info:
        return _get_deployment_info()


# Create instance to use as module
_metrics_module = _MetricsModule()

# Export metrics as module attributes
pipeline_runs_total = _metrics_module.pipeline_runs_total
pipeline_run_duration_seconds = _metrics_module.pipeline_run_duration_seconds
stage_executions_total = _metrics_module.stage_executions_total
stage_duration_seconds = _metrics_module.stage_duration_seconds
sources_found_total = _metrics_module.sources_found_total
evidence_extracted_total = _metrics_module.evidence_extracted_total
claims_generated_total = _metrics_module.claims_generated_total
quality_checks_total = _metrics_module.quality_checks_total
quality_score_histogram = _metrics_module.quality_score_histogram
errors_total = _metrics_module.errors_total
cache_operations_total = _metrics_module.cache_operations_total
active_pipeline_runs = _metrics_module.active_pipeline_runs
llm_requests_total = _metrics_module.llm_requests_total
llm_request_duration_seconds = _metrics_module.llm_request_duration_seconds
llm_tokens_total = _metrics_module.llm_tokens_total
storage_operations_total = _metrics_module.storage_operations_total
storage_bytes_total = _metrics_module.storage_bytes_total
pipeline_info = _metrics_module.pipeline_info
model_inference_active = _metrics_module.model_inference_active
model_inference_duration_seconds = _metrics_module.model_inference_duration_seconds
resource_usage_percent = _metrics_module.resource_usage_percent
deployment_info = _metrics_module.deployment_info


# Context managers for timing operations
@contextmanager
def measure_duration(
    histogram: Histogram, labels: Optional[Dict[str, str]] = None
) -> Generator[None, None, None]:
    """Context manager to measure operation duration.

    Args:
        histogram: Prometheus Histogram to record duration
        labels: Optional labels for the metric

    Example:
        with measure_duration(stage_duration_seconds, {"stage": "research"}):
            # Do some work
            pass
    """
    start_time = time.time()
    try:
        yield
    finally:
        duration = time.time() - start_time
        if labels:
            histogram.labels(**labels).observe(duration)
        else:
            histogram.observe(duration)


@contextmanager
def track_active(gauge: Gauge, amount: float = 1.0) -> Generator[None, None, None]:
    """Context manager to track active operations.

    Args:
        gauge: Prometheus Gauge to track active count
        amount: Amount to increment/decrement

    Example:
        with track_active(active_pipeline_runs):
            # Do pipeline work
            pass
    """
    gauge.inc(amount)
    try:
        yield
    finally:
        gauge.dec(amount)


# Utility functions
def record_pipeline_metric(
    metric_name: str, value: float, labels: Optional[Dict[str, str]] = None
) -> None:
    """Record a custom pipeline metric.

    Args:
        metric_name: Name of the metric
        value: Metric value
        labels: Optional metric labels
    """
    # This would typically integrate with a custom metrics system
    # For now, log it
    logger.debug(f"Metric recorded: {metric_name}={value}, labels={labels}")


def get_pipeline_metrics() -> Dict[str, Any]:
    """Get current pipeline metrics summary.

    Returns:
        Dictionary of metric summaries
    """
    # Collect current metric values
    metrics = {
        "active_runs": active_pipeline_runs._value.get(),
        "total_runs": sum(
            pipeline_runs_total.labels(status=s)._value.get()
            for s in ["started", "completed", "failed"]
        ),
        "total_errors": sum(
            errors_total.labels(severity=sev, stage="unknown", error_type="unknown")._value.get()
            for sev in ["low", "medium", "high", "critical"]
        ),
    }

    return metrics


def setup_metrics_endpoint(app: FastAPI, path: str = "/metrics") -> None:
    """Set up Prometheus metrics endpoint in FastAPI app.

    Args:
        app: FastAPI application instance
        path: URL path for metrics endpoint
    """

    @app.get(path, include_in_schema=False)
    async def metrics() -> Response:
        """Prometheus metrics endpoint."""
        try:
            # Load monitoring config
            config = get_config_loader().load_config("deployment")
            monitoring_config = config.get("monitoring", {})

            if not monitoring_config.get("enabled", True):
                return Response(content="Metrics collection disabled", status_code=503)

            # Generate metrics
            metrics_data = generate_latest(get_metrics_registry())

            return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)
        except Exception as e:
            logger.error(f"Failed to generate metrics: {e}")
            return Response(content=f"Error generating metrics: {str(e)}", status_code=500)

    logger.info(f"Metrics endpoint configured at {path}")


# Decorators for automatic metric collection
def track_stage_execution_decorator(stage: str) -> Callable:
    """Decorator to track stage execution metrics.

    Args:
        stage: Name of the pipeline stage

    Example:
        @track_stage_execution_decorator("research")
        async def research_stage(context):
            # Stage implementation
            pass
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            stage_executions_total.labels(stage=stage, status="started").inc()

            try:
                with measure_duration(stage_duration_seconds, {"stage": stage}):
                    result = await func(*args, **kwargs)

                stage_executions_total.labels(stage=stage, status="success").inc()
                return result

            except Exception:
                stage_executions_total.labels(stage=stage, status="failed").inc()
                raise

        return wrapper

    return decorator


def track_llm_request(provider: str, model: str) -> Callable:
    """Decorator to track LLM request metrics.

    Args:
        provider: LLM provider name
        model: Model name

    Example:
        @track_llm_request("openai", "gpt-4")
        async def call_openai(prompt):
            # API call implementation
            pass
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            llm_requests_total.labels(provider=provider, model=model, status="started").inc()

            try:
                with measure_duration(
                    llm_request_duration_seconds, {"provider": provider, "model": model}
                ):
                    result = await func(*args, **kwargs)

                llm_requests_total.labels(provider=provider, model=model, status="success").inc()
                return result

            except Exception:
                llm_requests_total.labels(provider=provider, model=model, status="failed").inc()
                raise

        return wrapper

    return decorator


@contextmanager
def track_pipeline_run() -> Generator[None, None, None]:
    """Track a pipeline run with metrics."""
    start_time = time.time()
    try:
        yield
        pipeline_runs_total.labels(status="success").inc()
        duration = time.time() - start_time
        pipeline_run_duration_seconds.observe(duration)
        logger.info(f"Pipeline run completed successfully in {duration:.2f}s")
    except Exception as e:
        pipeline_runs_total.labels(status="failure").inc()
        logger.error(f"Pipeline run failed: {e}")
        raise


@contextmanager
def track_model_inference(provider: str, model: str) -> Generator[None, None, None]:
    """Track model inference with metrics."""
    start_time = time.time()
    with model_inference_active.labels(provider=provider, model=model).track_inprogress():
        try:
            yield
            duration = time.time() - start_time
            model_inference_duration_seconds.labels(provider=provider, model=model).observe(
                duration
            )
        except Exception:
            raise


@contextmanager
def track_stage_execution(stage: str) -> Generator[None, None, None]:
    """Context manager to track stage execution metrics."""
    stage_executions_total.labels(stage=stage, status="started").inc()
    start_time = time.time()
    try:
        yield
        duration = time.time() - start_time
        stage_duration_seconds.labels(stage=stage).observe(duration)
        stage_executions_total.labels(stage=stage, status="success").inc()
    except Exception:
        stage_executions_total.labels(stage=stage, status="failed").inc()
        raise


def update_info_metric(info_dict: Dict[str, str]) -> None:
    """Update the pipeline info metric."""
    pipeline_info.info(info_dict)


def update_deployment_info(environment: str, region: str, instance_type: str) -> None:
    """Update deployment information metrics."""
    deployment_info.info(
        {"environment": environment, "region": region, "instance_type": instance_type}
    )


def track_resource_usage(cpu_percent: float, memory_percent: float, disk_percent: float) -> None:
    """Track resource usage metrics."""
    resource_usage_percent.labels(resource="cpu").set(cpu_percent)
    resource_usage_percent.labels(resource="memory").set(memory_percent)
    resource_usage_percent.labels(resource="disk").set(disk_percent)


def add_metrics_endpoint(app: FastAPI, path: str = "/metrics") -> None:
    """Add metrics endpoint to FastAPI app (alias for setup_metrics_endpoint)."""
    setup_metrics_endpoint(app, path)


def count_calls(func: Callable) -> Callable:
    """Decorator to count function calls."""
    counter_name = f"{func.__module__}_{func.__name__}_calls_total"
    if counter_name not in _counters:
        _counters[counter_name] = Counter(
            counter_name, f"Total calls to {func.__name__}", registry=get_metrics_registry()
        )

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        _counters[counter_name].inc()
        return func(*args, **kwargs)

    return wrapper


def time_it(func: Callable) -> Callable:
    """Decorator to time function execution."""
    histogram_name = f"{func.__module__}_{func.__name__}_duration_seconds"
    if histogram_name not in _histograms:
        _histograms[histogram_name] = Histogram(
            histogram_name,
            f"Duration of {func.__name__} in seconds",
            registry=get_metrics_registry(),
        )

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_time = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            duration = time.time() - start_time
            _histograms[histogram_name].observe(duration)

    return wrapper


def track_error(error_type: str) -> None:
    """Track an error occurrence."""
    errors_total.labels(error_type=error_type).inc()

"""Pydantic models for PenEllE configuration.

This module defines all configuration models with validation,
defaults, and examples for the PenEllE pipeline.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, validator


class ProviderType(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    AZURE = "azure"
    VERTEXAI = "vertexai"


class ConnectorType(str, Enum):
    """Supported source connectors."""

    OPENALEX = "openalex"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    PUBMED = "pubmed"
    ARXIV = "arxiv"
    CROSSREF = "crossref"


class OutputFormat(str, Enum):
    """Supported output formats."""

    MARKDOWN = "markdown"
    LATEX = "latex"
    DOCX = "docx"
    PDF = "pdf"
    HTML = "html"


class Environment(str, Enum):
    """Deployment environments."""

    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class ModelConfig(BaseModel):
    """Configuration for LLM models."""

    provider: ProviderType = Field(..., description="The LLM provider to use")
    model_name: str = Field(..., description="The specific model name/identifier")
    max_tokens: int = Field(4096, ge=1, le=32768, description="Maximum tokens for generation")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")
    top_p: float = Field(0.9, ge=0.0, le=1.0, description="Nucleus sampling parameter")
    frequency_penalty: float = Field(
        0.0, ge=-2.0, le=2.0, description="Frequency penalty for token repetition"
    )
    presence_penalty: float = Field(
        0.0, ge=-2.0, le=2.0, description="Presence penalty for token repetition"
    )
    api_key: Optional[str] = Field(None, description="API key (can use ${ENV_VAR} syntax)")
    api_base: Optional[HttpUrl] = Field(None, description="Custom API base URL")
    timeout: int = Field(300, ge=1, description="Request timeout in seconds")
    max_retries: int = Field(3, ge=0, description="Maximum number of retry attempts")

    class Config:
        schema_extra = {
            "example": {
                "provider": "openai",
                "model_name": "gpt-4-turbo-preview",
                "max_tokens": 4096,
                "temperature": 0.7,
                "top_p": 0.9,
                "api_key": "${OPENAI_API_KEY}",
            }
        }


class ConnectorConfig(BaseModel):
    """Configuration for source connectors."""

    enabled: bool = Field(True, description="Whether this connector is enabled")
    priority: int = Field(1, ge=1, le=10, description="Priority order for trying connectors")
    rate_limit: int = Field(10, ge=1, description="Requests per second limit")
    max_results: int = Field(100, ge=1, le=1000, description="Maximum results to fetch per query")
    timeout: int = Field(30, ge=1, description="Request timeout in seconds")
    api_key: Optional[str] = Field(None, description="API key if required")
    api_base: Optional[HttpUrl] = Field(None, description="Custom API endpoint")
    email: Optional[str] = Field(None, description="Email for APIs that require it (e.g., PubMed)")
    extra_params: Dict[str, Any] = Field(
        default_factory=dict, description="Additional connector-specific parameters"
    )

    class Config:
        schema_extra = {
            "example": {
                "enabled": True,
                "priority": 1,
                "rate_limit": 10,
                "max_results": 100,
                "api_key": "${SEMANTIC_SCHOLAR_API_KEY}",
            }
        }


class QualityGateConfig(BaseModel):
    """Configuration for quality gates and thresholds."""

    class EvidenceGate(BaseModel):
        """Evidence quality requirements."""

        min_sources: int = Field(10, ge=1, description="Minimum number of sources")
        max_sources: int = Field(50, ge=1, description="Maximum number of sources")
        min_evidence_per_claim: int = Field(2, ge=1, description="Minimum evidence per claim")
        min_source_quality_score: float = Field(
            0.7, ge=0.0, le=1.0, description="Minimum source quality"
        )
        require_peer_review: bool = Field(True, description="Require peer-reviewed sources")
        max_source_age_years: Optional[int] = Field(5, ge=1, description="Maximum age of sources")

    class ReadabilityGate(BaseModel):
        """Readability requirements."""

        max_passive_voice_percentage: float = Field(20, ge=0, le=100)
        min_flesch_reading_ease: float = Field(30, ge=0, le=100)
        max_sentence_length: int = Field(30, ge=10)
        max_paragraph_length: int = Field(150, ge=50)

    class OutputGate(BaseModel):
        """Output requirements."""

        min_word_count: int = Field(3000, ge=100)
        max_word_count: int = Field(10000, ge=100)
        required_sections: List[str] = Field(
            ["introduction", "methodology", "conclusion"], min_length=1
        )
        formats: List[OutputFormat] = Field([OutputFormat.MARKDOWN], min_length=1)

    evidence: "QualityGateConfig.EvidenceGate" = Field(
        default_factory=lambda: QualityGateConfig.EvidenceGate.model_validate({})
    )
    readability: "QualityGateConfig.ReadabilityGate" = Field(
        default_factory=lambda: QualityGateConfig.ReadabilityGate.model_validate({})
    )
    output: "QualityGateConfig.OutputGate" = Field(
        default_factory=lambda: QualityGateConfig.OutputGate.model_validate({})
    )

    class Config:
        schema_extra = {
            "example": {
                "evidence": {
                    "min_sources": 10,
                    "max_sources": 50,
                    "min_evidence_per_claim": 2,
                    "min_source_quality_score": 0.7,
                },
                "readability": {
                    "max_passive_voice_percentage": 20,
                    "min_flesch_reading_ease": 30,
                    "max_sentence_length": 30,
                },
                "output": {
                    "min_word_count": 3000,
                    "max_word_count": 10000,
                    "required_sections": ["introduction", "methodology", "conclusion"],
                },
            }
        }


class DeploymentConfig(BaseModel):
    """Environment-specific deployment configuration."""

    environment: Environment = Field(Environment.LOCAL, description="Deployment environment")
    debug: bool = Field(False, description="Enable debug mode")
    log_level: str = Field(
        "INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$", description="Logging level"
    )

    class DatabaseConfig(BaseModel):
        """Database configuration."""

        url: str = Field(..., description="Database connection URL")
        pool_size: int = Field(10, ge=1, description="Connection pool size")
        max_overflow: int = Field(20, ge=0, description="Maximum overflow connections")
        pool_timeout: int = Field(30, ge=1, description="Pool timeout in seconds")
        echo: bool = Field(False, description="Echo SQL statements")

    class RedisConfig(BaseModel):
        """Redis configuration."""

        url: str = Field("redis://localhost:6379", description="Redis connection URL")
        max_connections: int = Field(50, ge=1)
        decode_responses: bool = Field(True)
        socket_timeout: int = Field(5, ge=1)

    class StorageConfig(BaseModel):
        """Storage configuration."""

        type: str = Field("s3", pattern="^(s3|local|gcs|azure)$")
        bucket: Optional[str] = Field(None, description="Storage bucket name")
        prefix: str = Field("penelle", description="Storage key prefix")
        local_path: Optional[str] = Field(None, description="Local storage path")

    class MonitoringConfig(BaseModel):
        """Monitoring configuration."""

        enabled: bool = Field(True)
        prometheus_port: int = Field(9090, ge=1024, le=65535)
        metrics_path: str = Field("/metrics")
        jaeger_endpoint: Optional[HttpUrl] = Field(None)

        @validator("jaeger_endpoint", pre=True)
        def empty_string_to_none(cls, v):
            """Convert empty string to None."""
            if v == "":
                return None
            return v

    database: DatabaseConfig
    redis: RedisConfig
    storage: StorageConfig
    monitoring: "DeploymentConfig.MonitoringConfig" = Field(
        default_factory=lambda: DeploymentConfig.MonitoringConfig.model_validate({})
    )

    # Feature flags
    enable_hot_reload: bool = Field(False, description="Enable config hot-reloading")
    enable_caching: bool = Field(True, description="Enable response caching")
    enable_tracing: bool = Field(True, description="Enable distributed tracing")

    # Security
    api_key_header: str = Field("X-API-Key", description="API key header name")
    cors_origins: List[str] = Field(["*"], description="Allowed CORS origins")
    max_request_size: int = Field(10485760, ge=1024, description="Max request size in bytes")

    class Config:
        schema_extra = {
            "example": {
                "environment": "production",
                "debug": False,
                "log_level": "INFO",
                "database": {"url": "postgresql://user:pass@localhost/penelle", "pool_size": 10},
                "redis": {"url": "redis://localhost:6379", "max_connections": 50},
                "storage": {"type": "s3", "bucket": "penelle-prod", "prefix": "data"},
            }
        }


class PipelineConfig(BaseModel):
    """Overall pipeline configuration."""

    name: str = Field("PenEllE Pipeline", description="Pipeline name")
    version: str = Field("1.0.0", description="Pipeline version")

    # Model configurations
    models: Dict[str, ModelConfig] = Field(..., description="Available model configurations")

    # Default models for each stage
    default_models: Dict[str, str] = Field(
        {
            "research": "gpt-4",
            "outline": "gpt-4",
            "draft": "gpt-4",
            "review": "claude-3",
            "format": "gpt-4",
        },
        description="Default model for each pipeline stage",
    )

    # Connector configurations
    connectors: Dict[str, ConnectorConfig] = Field(
        ..., description="Source connector configurations"
    )

    # Quality gates
    quality_gates: QualityGateConfig = Field(
        default_factory=QualityGateConfig, description="Quality gate configurations"
    )

    # Pipeline behavior
    max_concurrent_runs: int = Field(10, ge=1, description="Maximum concurrent pipeline runs")
    default_timeout_minutes: int = Field(120, ge=1, description="Default pipeline timeout")
    retry_failed_stages: bool = Field(True, description="Whether to retry failed stages")
    max_stage_retries: int = Field(3, ge=0, description="Maximum retries per stage")

    # Caching
    cache_ttl_hours: int = Field(24, ge=1, description="Cache TTL in hours")
    cache_research_results: bool = Field(True, description="Cache research stage results")

    @validator("default_models")
    def validate_default_models(cls, v: Dict[str, str], values: Dict[str, Any]) -> Dict[str, str]:
        """Ensure default models exist in models config."""
        if "models" in values:
            for stage, model_name in v.items():
                if model_name not in values["models"]:
                    raise ValueError(
                        f"Default model '{model_name}' for stage '{stage}' not found in models config"
                    )
        return v

    class Config:
        schema_extra = {
            "example": {
                "name": "PenEllE Pipeline",
                "version": "1.0.0",
                "models": {
                    "gpt-4": {
                        "provider": "openai",
                        "model_name": "gpt-4-turbo-preview",
                        "max_tokens": 4096,
                    }
                },
                "connectors": {"openalex": {"enabled": True, "priority": 1, "rate_limit": 10}},
                "quality_gates": {"evidence": {"min_sources": 10}},
            }
        }


# Convenience functions for loading typed configurations
def load_model_config(config_dict: Dict[str, Any]) -> ModelConfig:
    """Load and validate a model configuration."""
    return ModelConfig(**config_dict)


def load_connector_config(config_dict: Dict[str, Any]) -> ConnectorConfig:
    """Load and validate a connector configuration."""
    return ConnectorConfig(**config_dict)


def load_quality_gates(config_dict: Dict[str, Any]) -> QualityGateConfig:
    """Load and validate quality gates configuration."""
    return QualityGateConfig(**config_dict)


def load_deployment_config(config_dict: Dict[str, Any]) -> DeploymentConfig:
    """Load and validate deployment configuration."""
    return DeploymentConfig(**config_dict)


def load_pipeline_config(config_dict: Dict[str, Any]) -> PipelineConfig:
    """Load and validate pipeline configuration."""
    return PipelineConfig(**config_dict)

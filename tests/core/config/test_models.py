"""Tests for configuration models."""

import pytest
from pydantic import ValidationError

from src.core.config.models import (
    ConnectorConfig,
    ConnectorType,
    DeploymentConfig,
    Environment,
    ModelConfig,
    OutputFormat,
    PipelineConfig,
    ProviderType,
    QualityGateConfig,
    load_connector_config,
    load_deployment_config,
    load_model_config,
    load_pipeline_config,
    load_quality_gates,
)


class TestEnums:
    """Test configuration enums."""

    def test_provider_type(self):
        """Test ProviderType enum."""
        assert ProviderType.OPENAI == "openai"
        assert ProviderType.ANTHROPIC == "anthropic"
        assert ProviderType.OLLAMA == "ollama"

    def test_connector_type(self):
        """Test ConnectorType enum."""
        assert ConnectorType.OPENALEX == "openalex"
        assert ConnectorType.SEMANTIC_SCHOLAR == "semantic_scholar"
        assert ConnectorType.PUBMED == "pubmed"

    def test_output_format(self):
        """Test OutputFormat enum."""
        assert OutputFormat.MARKDOWN == "markdown"
        assert OutputFormat.PDF == "pdf"
        assert OutputFormat.DOCX == "docx"

    def test_environment(self):
        """Test Environment enum."""
        assert Environment.LOCAL == "local"
        assert Environment.PRODUCTION == "production"


class TestModelConfig:
    """Test ModelConfig model."""

    def test_valid_model_config(self):
        """Test creating valid ModelConfig."""
        config = ModelConfig(
            provider=ProviderType.OPENAI, model_name="gpt-4", max_tokens=4096, temperature=0.7
        )

        assert config.provider == ProviderType.OPENAI
        assert config.model_name == "gpt-4"
        assert config.max_tokens == 4096
        assert config.temperature == 0.7
        assert config.top_p == 0.9  # Default

    def test_model_config_validation(self):
        """Test ModelConfig validation."""
        # Invalid temperature
        with pytest.raises(ValidationError):
            ModelConfig(provider=ProviderType.OPENAI, model_name="gpt-4", temperature=3.0)  # > 2.0

        # Invalid max_tokens
        with pytest.raises(ValidationError):
            ModelConfig(
                provider=ProviderType.OPENAI, model_name="gpt-4", max_tokens=100000  # > 32768
            )

    def test_model_config_with_api_key(self):
        """Test ModelConfig with API key."""
        config = ModelConfig(
            provider=ProviderType.OPENAI, model_name="gpt-4", api_key="${OPENAI_API_KEY}"
        )

        assert config.api_key == "${OPENAI_API_KEY}"


class TestConnectorConfig:
    """Test ConnectorConfig model."""

    def test_valid_connector_config(self):
        """Test creating valid ConnectorConfig."""
        config = ConnectorConfig(enabled=True, priority=1, rate_limit=10, max_results=100)

        assert config.enabled is True
        assert config.priority == 1
        assert config.rate_limit == 10
        assert config.timeout == 30  # Default

    def test_connector_config_with_extras(self):
        """Test ConnectorConfig with extra parameters."""
        config = ConnectorConfig(
            enabled=True,
            priority=2,
            api_key="test-key",
            email="test@example.com",
            extra_params={"filter": "open_access"},
        )

        assert config.api_key == "test-key"
        assert config.email == "test@example.com"
        assert config.extra_params["filter"] == "open_access"


class TestQualityGateConfig:
    """Test QualityGateConfig model."""

    def test_valid_quality_gate_config(self):
        """Test creating valid QualityGateConfig."""
        config = QualityGateConfig()

        # Check defaults
        assert config.evidence.min_sources == 10
        assert config.evidence.max_sources == 50
        assert config.readability.max_passive_voice_percentage == 20
        assert config.output.min_word_count == 3000

    def test_quality_gate_custom_values(self):
        """Test QualityGateConfig with custom values."""
        config = QualityGateConfig(
            evidence={"min_sources": 20, "require_peer_review": False},
            readability={"max_sentence_length": 25},
            output={"formats": [OutputFormat.MARKDOWN, OutputFormat.PDF]},
        )

        assert config.evidence.min_sources == 20
        assert config.evidence.require_peer_review is False
        assert config.readability.max_sentence_length == 25
        assert OutputFormat.PDF in config.output.formats


class TestDeploymentConfig:
    """Test DeploymentConfig model."""

    def test_valid_deployment_config(self):
        """Test creating valid DeploymentConfig."""
        config = DeploymentConfig(
            environment=Environment.PRODUCTION,
            debug=False,
            database={"url": "postgresql://user:pass@localhost/db", "pool_size": 20},
            redis={"url": "redis://localhost:6379"},
            storage={"type": "s3", "bucket": "test-bucket"},
        )

        assert config.environment == Environment.PRODUCTION
        assert config.debug is False
        assert config.database.pool_size == 20
        assert config.storage.type == "s3"

    def test_deployment_config_validation(self):
        """Test DeploymentConfig validation."""
        # Invalid log level
        with pytest.raises(ValidationError):
            DeploymentConfig(
                environment=Environment.LOCAL,
                log_level="INVALID",
                database={"url": "test"},
                redis={"url": "test"},
                storage={"type": "s3"},
            )

        # Invalid storage type
        with pytest.raises(ValidationError):
            DeploymentConfig(
                environment=Environment.LOCAL,
                database={"url": "test"},
                redis={"url": "test"},
                storage={"type": "invalid"},
            )


class TestPipelineConfig:
    """Test PipelineConfig model."""

    def test_valid_pipeline_config(self):
        """Test creating valid PipelineConfig."""
        config = PipelineConfig(
            name="Test Pipeline",
            version="1.0.0",
            models={"gpt-4": {"provider": "openai", "model_name": "gpt-4", "max_tokens": 4096}},
            connectors={"openalex": {"enabled": True, "priority": 1}},
        )

        assert config.name == "Test Pipeline"
        assert "gpt-4" in config.models
        assert "openalex" in config.connectors

    def test_pipeline_config_default_models_validation(self):
        """Test PipelineConfig validates default models exist."""
        # Valid config
        config = PipelineConfig(
            models={
                "gpt-4": {"provider": "openai", "model_name": "gpt-4", "max_tokens": 4096},
                "claude-3": {"provider": "anthropic", "model_name": "claude-3", "max_tokens": 4096},
            },
            default_models={"research": "gpt-4", "review": "claude-3"},
            connectors={},
        )

        assert config.default_models["research"] == "gpt-4"

        # Invalid - default model doesn't exist
        with pytest.raises(ValidationError) as exc_info:
            PipelineConfig(
                models={"gpt-4": {"provider": "openai", "model_name": "gpt-4", "max_tokens": 4096}},
                default_models={"research": "non-existent-model"},
                connectors={},
            )

        assert "not found in models config" in str(exc_info.value)


class TestLoadFunctions:
    """Test configuration loading functions."""

    def test_load_model_config(self):
        """Test load_model_config function."""
        data = {"provider": "openai", "model_name": "gpt-4", "max_tokens": 4096}

        config = load_model_config(data)
        assert isinstance(config, ModelConfig)
        assert config.model_name == "gpt-4"

    def test_load_connector_config(self):
        """Test load_connector_config function."""
        data = {"enabled": True, "priority": 1, "rate_limit": 10}

        config = load_connector_config(data)
        assert isinstance(config, ConnectorConfig)
        assert config.priority == 1

    def test_load_quality_gates(self):
        """Test load_quality_gates function."""
        data = {"evidence": {"min_sources": 15}}

        config = load_quality_gates(data)
        assert isinstance(config, QualityGateConfig)
        assert config.evidence.min_sources == 15

    def test_load_deployment_config(self):
        """Test load_deployment_config function."""
        data = {
            "environment": "production",
            "debug": False,
            "database": {"url": "postgresql://localhost/db"},
            "redis": {"url": "redis://localhost"},
            "storage": {"type": "s3", "bucket": "test"},
        }

        config = load_deployment_config(data)
        assert isinstance(config, DeploymentConfig)
        assert config.environment == Environment.PRODUCTION

    def test_load_pipeline_config(self):
        """Test load_pipeline_config function."""
        data = {
            "name": "Test",
            "version": "1.0",
            "models": {"test": {"provider": "openai", "model_name": "test", "max_tokens": 100}},
            "connectors": {},
        }

        config = load_pipeline_config(data)
        assert isinstance(config, PipelineConfig)
        assert config.name == "Test"

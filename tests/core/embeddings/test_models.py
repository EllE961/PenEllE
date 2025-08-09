"""Tests for embedding models."""

import pytest

from src.core.embeddings.models import (
    PREDEFINED_MODELS,
    EmbeddingModel,
    EmbeddingModelConfig,
    ModelType,
)


class TestEmbeddingModelConfig:
    """Tests for EmbeddingModelConfig."""

    def test_create_config(self):
        """Test creating model configuration."""
        config = EmbeddingModelConfig(
            name="test-model",
            dimensions=384,
            model_type=ModelType.DOCUMENT,
            max_tokens=512,
            batch_size=32,
        )

        assert config.name == "test-model"
        assert config.dimensions == 384
        assert config.model_type == "document"
        assert config.max_tokens == 512
        assert config.batch_size == 32
        assert config.normalize is True
        assert config.cache_enabled is True

    def test_config_with_device(self):
        """Test config with specific device."""
        config = EmbeddingModelConfig(
            name="test-model",
            dimensions=768,
            model_type=ModelType.QUERY,
            device="cpu",
        )

        assert config.device == "cpu"

    def test_config_model_types(self):
        """Test different model types."""
        for model_type in [ModelType.DOCUMENT, ModelType.QUERY, ModelType.MULTILINGUAL]:
            config = EmbeddingModelConfig(
                name=f"test-{model_type}",
                dimensions=384,
                model_type=model_type,
            )
            assert config.model_type == model_type.value


class TestPredefinedModels:
    """Tests for predefined model configurations."""

    def test_predefined_models_exist(self):
        """Test that predefined models are available."""
        assert len(PREDEFINED_MODELS) > 0

    def test_all_mpnet_base_v2(self):
        """Test all-mpnet-base-v2 configuration."""
        assert "all-mpnet-base-v2" in PREDEFINED_MODELS
        config = PREDEFINED_MODELS["all-mpnet-base-v2"]

        assert config.name == "sentence-transformers/all-mpnet-base-v2"
        assert config.dimensions == 768
        assert config.model_type == "document"
        assert config.max_tokens == 512

    def test_all_minilm_l6_v2(self):
        """Test all-MiniLM-L6-v2 configuration."""
        assert "all-MiniLM-L6-v2" in PREDEFINED_MODELS
        config = PREDEFINED_MODELS["all-MiniLM-L6-v2"]

        assert config.name == "sentence-transformers/all-MiniLM-L6-v2"
        assert config.dimensions == 384
        assert config.model_type == "query"
        assert config.max_tokens == 256
        assert config.batch_size == 128

    def test_multilingual_models(self):
        """Test multilingual model configurations."""
        multilingual_models = [
            name
            for name, config in PREDEFINED_MODELS.items()
            if config.model_type == "multilingual"
        ]

        assert len(multilingual_models) >= 2
        assert "bge-m3" in multilingual_models
        assert "e5-multilingual-small" in multilingual_models

    def test_cpu_optimized_models(self):
        """Test CPU-optimized models."""
        cpu_models = [name for name, config in PREDEFINED_MODELS.items() if config.device == "cpu"]

        assert "bge-small-en" in cpu_models


class TestEmbeddingModel:
    """Tests for base EmbeddingModel class."""

    def test_model_initialization(self):
        """Test model initialization."""
        config = EmbeddingModelConfig(
            name="test-model",
            dimensions=384,
            model_type=ModelType.DOCUMENT,
        )

        model = EmbeddingModel(config)

        assert model.config == config
        assert model._model is None
        assert model._tokenizer is None

    def test_model_abstract_methods(self):
        """Test that abstract methods raise NotImplementedError."""
        config = EmbeddingModelConfig(
            name="test-model",
            dimensions=384,
            model_type=ModelType.DOCUMENT,
        )

        model = EmbeddingModel(config)

        with pytest.raises(NotImplementedError):
            model._load_model()

        with pytest.raises(NotImplementedError):
            model.encode(["test text"])

    def test_encode_single(self):
        """Test encode_single method."""

        class MockModel(EmbeddingModel):
            def _load_model(self):
                pass

            def encode(self, texts, **kwargs):
                return [[1.0] * self.config.dimensions for _ in texts]

        config = EmbeddingModelConfig(
            name="test-model",
            dimensions=384,
            model_type=ModelType.DOCUMENT,
        )

        model = MockModel(config)
        embedding = model.encode_single("test text")

        assert len(embedding) == 384
        assert all(v == 1.0 for v in embedding)

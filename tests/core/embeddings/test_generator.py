"""Tests for embedding generator."""

import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.core.embeddings.cache import EmbeddingCache
from src.core.embeddings.generator import EmbeddingGenerator, SentenceTransformerModel
from src.core.embeddings.models import (
    PREDEFINED_MODELS,
    EmbeddingModelConfig,
    ModelType,
)


class TestSentenceTransformerModel:
    """Tests for SentenceTransformerModel."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return EmbeddingModelConfig(
            name="sentence-transformers/all-MiniLM-L6-v2",
            dimensions=384,
            model_type=ModelType.DOCUMENT,
            batch_size=32,
        )

    @patch("src.core.embeddings.generator.SentenceTransformer")
    def test_load_model(self, mock_st, config):
        """Test model loading."""
        # Mock sentence transformer
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384])
        mock_st.return_value = mock_model

        model = SentenceTransformerModel(config)

        # Access model property to trigger loading
        _ = model.model

        # Verify loading
        mock_st.assert_called_once_with(
            config.name,
            device="cpu",  # Default when no GPU
            trust_remote_code=False,
        )

    @patch("src.core.embeddings.generator.SentenceTransformer")
    def test_encode(self, mock_st, config):
        """Test encoding texts."""
        # Mock model
        mock_model = MagicMock()
        embeddings = np.array(
            [
                [0.1] * 384,
                [0.2] * 384,
            ]
        )
        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        model = SentenceTransformerModel(config)
        texts = ["text 1", "text 2"]

        result = model.encode(texts, show_progress=False)

        # Verify
        assert len(result) == 2
        assert len(result[0]) == 384
        assert np.allclose(result[0], [0.1] * 384)
        assert np.allclose(result[1], [0.2] * 384)

        # Check encoding parameters
        mock_model.encode.assert_called_with(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )


class TestEmbeddingGenerator:
    """Tests for EmbeddingGenerator."""

    @pytest.fixture
    def temp_cache(self):
        """Create temporary cache."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            cache = EmbeddingCache(cache_path=f.name)
        yield cache

    @pytest.fixture
    def generator(self, temp_cache):
        """Create generator with cache."""
        return EmbeddingGenerator(
            cache=temp_cache,
            default_model="all-MiniLM-L6-v2",
        )

    def test_initialization(self, generator):
        """Test generator initialization."""
        assert generator.default_model == "all-MiniLM-L6-v2"
        assert generator.cache is not None
        assert len(generator._model_configs) > 0
        assert len(generator._models) == 0  # No models loaded yet

    def test_register_model(self, generator):
        """Test registering custom model."""
        config = EmbeddingModelConfig(
            name="custom-model",
            dimensions=512,
            model_type=ModelType.QUERY,
        )

        generator.register_model("custom", config)

        assert "custom" in generator._model_configs
        assert generator._model_configs["custom"] == config

    def test_get_model_predefined(self, generator):
        """Test getting predefined model."""
        with patch("src.core.embeddings.generator.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1] * 384])
            mock_st.return_value = mock_model

            model = generator.get_model("all-MiniLM-L6-v2")

            assert isinstance(model, SentenceTransformerModel)
            assert model.config.dimensions == 384

    def test_get_model_unknown(self, generator):
        """Test getting unknown model."""
        with pytest.raises(ValueError, match="Unknown model"):
            generator.get_model("unknown-model")

    def test_compute_text_hash(self, generator):
        """Test text hash computation."""
        text = "test text"
        model = "test-model"

        hash1 = generator._compute_text_hash(text, model)
        hash2 = generator._compute_text_hash(text, model)
        hash3 = generator._compute_text_hash("different", model)

        # Same input should give same hash
        assert hash1 == hash2
        # Different input should give different hash
        assert hash1 != hash3

    @patch("src.core.embeddings.generator.SentenceTransformer")
    def test_embed_texts_single(self, mock_st, generator):
        """Test embedding single text."""
        # Mock model
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.1] * 384])
        mock_st.return_value = mock_model

        text = "test text"
        result = generator.embed_texts(text, use_cache=False)

        # Should return single embedding
        assert isinstance(result, list)
        assert len(result) == 384

    @patch("src.core.embeddings.generator.SentenceTransformer")
    def test_embed_texts_multiple(self, mock_st, generator):
        """Test embedding multiple texts."""
        # Mock model
        mock_model = MagicMock()
        embeddings = np.array(
            [
                [0.1] * 384,
                [0.2] * 384,
                [0.3] * 384,
            ]
        )
        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        texts = ["text 1", "text 2", "text 3"]
        results = generator.embed_texts(texts, use_cache=False)

        assert len(results) == 3
        assert all(len(emb) == 384 for emb in results)

    @patch("src.core.embeddings.generator.SentenceTransformer")
    def test_embed_texts_with_cache(self, mock_st, generator):
        """Test embedding with cache."""
        # Mock model
        mock_model = MagicMock()
        embeddings = np.array([[0.1] * 384, [0.2] * 384])
        # Return different values for dimension check vs actual encoding
        mock_model.encode.side_effect = [
            np.array([[0.0] * 384]),  # First call for dimension check
            embeddings,  # Second call for actual encoding
            embeddings,  # Third call (from cache test)
        ]
        mock_st.return_value = mock_model

        texts = ["text 1", "text 2"]

        # First call - should encode (plus 1 call for dimension verification)
        results1 = generator.embed_texts(texts, use_cache=True)
        assert mock_model.encode.call_count == 2  # 1 for dimension check, 1 for actual encoding

        # Second call - should use cache
        results2 = generator.embed_texts(texts, use_cache=True)
        assert mock_model.encode.call_count == 2  # No additional calls

        # Results should be the same
        assert np.allclose(results1[0], results2[0])
        assert np.allclose(results1[1], results2[1])

    def test_select_model_by_type(self, generator):
        """Test model selection by type."""
        # Query type
        query_model = generator._select_model_by_type(ModelType.QUERY)
        assert query_model in ["all-MiniLM-L6-v2", "bge-small-en"]

        # Document type
        doc_model = generator._select_model_by_type(ModelType.DOCUMENT)
        assert doc_model in PREDEFINED_MODELS

        # Multilingual type
        multi_model = generator._select_model_by_type(ModelType.MULTILINGUAL)
        config = PREDEFINED_MODELS.get(multi_model)
        assert config is not None
        assert config.model_type == "multilingual"

    @patch("src.core.embeddings.generator.SentenceTransformer")
    def test_embed_documents(self, mock_st, generator):
        """Test document embedding helper."""
        # Mock model
        mock_model = MagicMock()
        embeddings = np.array([[0.1] * 384])
        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        docs = ["document text"]
        results = generator.embed_documents(docs, use_cache=False)

        assert len(results) == 1
        assert len(results[0]) == 384

    @patch("src.core.embeddings.generator.SentenceTransformer")
    def test_embed_queries(self, mock_st, generator):
        """Test query embedding helper."""
        # Mock model
        mock_model = MagicMock()
        embeddings = np.array([[0.1] * 384])
        mock_model.encode.return_value = embeddings
        mock_st.return_value = mock_model

        queries = ["search query"]
        results = generator.embed_queries(queries, use_cache=False)

        assert len(results) == 1
        assert len(results[0]) == 384

    def test_compute_similarity_cosine(self, generator):
        """Test cosine similarity computation."""
        emb1 = [1.0, 0.0, 0.0]
        emb2 = [1.0, 0.0, 0.0]
        emb3 = [0.0, 1.0, 0.0]

        # Same vectors - similarity 1
        sim = generator.compute_similarity(emb1, emb2, metric="cosine")
        assert np.isclose(sim, 1.0)

        # Orthogonal vectors - similarity 0
        sim = generator.compute_similarity(emb1, emb3, metric="cosine")
        assert np.isclose(sim, 0.0)

    def test_compute_similarity_dot(self, generator):
        """Test dot product similarity."""
        emb1 = [1.0, 2.0, 3.0]
        emb2 = [4.0, 5.0, 6.0]

        sim = generator.compute_similarity(emb1, emb2, metric="dot")
        expected = 1 * 4 + 2 * 5 + 3 * 6  # 32
        assert np.isclose(sim, expected)

    def test_compute_similarity_euclidean(self, generator):
        """Test euclidean distance."""
        emb1 = [1.0, 0.0]
        emb2 = [0.0, 1.0]

        sim = generator.compute_similarity(emb1, emb2, metric="euclidean")
        expected = -np.sqrt(2)  # Negative distance
        assert np.isclose(sim, expected)

    def test_compute_similarity_batch(self, generator):
        """Test batch similarity computation."""
        emb1 = [[1.0, 0.0], [0.0, 1.0]]
        emb2 = [[1.0, 0.0], [0.0, 1.0]]

        sim_matrix = generator.compute_similarity(emb1, emb2, metric="cosine")

        assert sim_matrix.shape == (2, 2)
        assert np.isclose(sim_matrix[0, 0], 1.0)  # First with first
        assert np.isclose(sim_matrix[1, 1], 1.0)  # Second with second
        assert np.isclose(sim_matrix[0, 1], 0.0)  # First with second

    def test_get_model_info(self, generator):
        """Test getting model information."""
        info = generator.get_model_info("all-MiniLM-L6-v2")

        assert info["name"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert info["dimensions"] == 384
        assert info["model_type"] == "query"
        assert info["max_tokens"] == 256
        assert info["loaded"] is False  # Not loaded yet

        # Load model
        with patch("src.core.embeddings.generator.SentenceTransformer"):
            _ = generator.get_model("all-MiniLM-L6-v2")

        info = generator.get_model_info("all-MiniLM-L6-v2")
        assert info["loaded"] is True

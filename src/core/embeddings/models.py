"""Embedding model configurations and management."""

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class ModelType(str, Enum):
    """Supported embedding model types."""

    DOCUMENT = "document"
    QUERY = "query"
    MULTILINGUAL = "multilingual"


class EmbeddingModelConfig(BaseModel):
    """Configuration for an embedding model."""

    name: str = Field(..., description="Model name/identifier")
    dimensions: int = Field(..., description="Embedding vector dimensions")
    model_type: ModelType = Field(..., description="Type of model")
    max_tokens: int = Field(default=512, description="Maximum input tokens")
    batch_size: int = Field(default=32, description="Batch size for encoding")
    normalize: bool = Field(default=True, description="Whether to normalize embeddings")
    device: Optional[str] = Field(default=None, description="Device to use (cuda/cpu)")
    cache_enabled: bool = Field(default=True, description="Whether to cache embeddings")

    # Model-specific parameters
    pooling_mode: str = Field(default="mean", description="Pooling mode for sentence transformers")
    trust_remote_code: bool = Field(default=False, description="Trust remote code for HF models")

    class Config:
        use_enum_values = True


class EmbeddingModel:
    """Base class for embedding models."""

    def __init__(self, config: EmbeddingModelConfig):
        """Initialize embedding model.

        Args:
            config: Model configuration
        """
        self.config = config
        self._model = None
        self._tokenizer = None

    @property
    def model(self) -> Any:
        """Lazy load the model."""
        if self._model is None:
            self._model = self._load_model()
        return self._model

    def _load_model(self) -> Any:
        """Load the model implementation."""
        raise NotImplementedError("Subclasses must implement _load_model")

    def encode(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        show_progress: bool = False,
        **kwargs: Any,
    ) -> List[List[float]]:
        """Encode texts to embeddings.

        Args:
            texts: List of texts to encode
            batch_size: Batch size for encoding
            show_progress: Whether to show progress bar
            **kwargs: Additional model-specific arguments

        Returns:
            List of embedding vectors
        """
        raise NotImplementedError("Subclasses must implement encode")

    def encode_single(self, text: str, **kwargs: Any) -> List[float]:
        """Encode a single text.

        Args:
            text: Text to encode
            **kwargs: Additional model-specific arguments

        Returns:
            Embedding vector
        """
        return self.encode([text], **kwargs)[0]


# Predefined model configurations
PREDEFINED_MODELS = {
    # Document models (higher quality, slower)
    "all-mpnet-base-v2": EmbeddingModelConfig(
        name="sentence-transformers/all-mpnet-base-v2",
        dimensions=768,
        model_type=ModelType.DOCUMENT,
        max_tokens=512,
        batch_size=32,
        normalize=True,
        device=None,
        cache_enabled=True,
        pooling_mode="mean",
        trust_remote_code=False,
    ),
    "all-MiniLM-L12-v2": EmbeddingModelConfig(
        name="sentence-transformers/all-MiniLM-L12-v2",
        dimensions=384,
        model_type=ModelType.DOCUMENT,
        max_tokens=512,
        batch_size=64,
        normalize=True,
        device=None,
        cache_enabled=True,
        pooling_mode="mean",
        trust_remote_code=False,
    ),
    # Query models (faster, optimized for queries)
    "all-MiniLM-L6-v2": EmbeddingModelConfig(
        name="sentence-transformers/all-MiniLM-L6-v2",
        dimensions=384,
        model_type=ModelType.QUERY,
        max_tokens=256,
        batch_size=128,
        normalize=True,
        device=None,
        cache_enabled=True,
        pooling_mode="mean",
        trust_remote_code=False,
    ),
    # Local CPU-friendly models
    "bge-small-en": EmbeddingModelConfig(
        name="BAAI/bge-small-en-v1.5",
        dimensions=384,
        model_type=ModelType.DOCUMENT,
        max_tokens=512,
        batch_size=32,
        normalize=True,
        device="cpu",
        cache_enabled=True,
        pooling_mode="mean",
        trust_remote_code=False,
    ),
    # Multilingual models
    "bge-m3": EmbeddingModelConfig(
        name="BAAI/bge-m3",
        dimensions=1024,
        model_type=ModelType.MULTILINGUAL,
        max_tokens=512,
        batch_size=16,
        normalize=True,
        device=None,
        cache_enabled=True,
        pooling_mode="mean",
        trust_remote_code=False,
    ),
    "e5-multilingual-small": EmbeddingModelConfig(
        name="intfloat/multilingual-e5-small",
        dimensions=384,
        model_type=ModelType.MULTILINGUAL,
        max_tokens=512,
        batch_size=32,
        normalize=True,
        device=None,
        cache_enabled=True,
        pooling_mode="mean",
        trust_remote_code=False,
    ),
}

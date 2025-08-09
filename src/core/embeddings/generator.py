"""Embedding generator with support for multiple models."""

import hashlib
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from ..logging.structured import get_logger
from .cache import EmbeddingCache
from .models import (
    PREDEFINED_MODELS,
    EmbeddingModel,
    EmbeddingModelConfig,
    ModelType,
)

logger = get_logger(__name__)


class SentenceTransformerModel(EmbeddingModel):
    """Sentence Transformer embedding model implementation."""

    def _load_model(self) -> SentenceTransformer:
        """Load the sentence transformer model."""
        device = self.config.device or ("cuda" if torch.cuda.is_available() else "cpu")
        logger.info(f"Loading model {self.config.name} on device {device}")

        model = SentenceTransformer(
            self.config.name,
            device=device,
            trust_remote_code=self.config.trust_remote_code,
        )

        # Verify dimensions match
        test_embedding = model.encode(["test"], show_progress_bar=False)
        actual_dims = len(test_embedding[0])
        if actual_dims != self.config.dimensions:
            logger.warning(
                f"Model {self.config.name} has {actual_dims} dimensions, "
                f"but config specifies {self.config.dimensions}"
            )
            self.config.dimensions = actual_dims

        return model

    def encode(
        self,
        texts: List[str],
        batch_size: Optional[int] = None,
        show_progress: bool = False,
        **kwargs: Any,
    ) -> List[List[float]]:
        """Encode texts to embeddings."""
        if not texts:
            return []

        batch_size = batch_size or self.config.batch_size

        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=self.config.normalize,
            **kwargs,
        )

        return embeddings.tolist()  # type: ignore[no-any-return]


class EmbeddingGenerator:
    """Main embedding generator with model management and caching."""

    def __init__(
        self,
        cache: Optional[EmbeddingCache] = None,
        default_model: str = "all-MiniLM-L6-v2",
    ):
        """Initialize embedding generator.

        Args:
            cache: Optional embedding cache
            default_model: Default model to use
        """
        self.cache = cache
        self.default_model = default_model
        self._models: Dict[str, EmbeddingModel] = {}
        self._model_configs: Dict[str, EmbeddingModelConfig] = PREDEFINED_MODELS.copy()

    def register_model(self, name: str, config: EmbeddingModelConfig) -> None:
        """Register a custom model configuration.

        Args:
            name: Model identifier
            config: Model configuration
        """
        self._model_configs[name] = config
        logger.info(f"Registered model {name} with {config.dimensions} dimensions")

    def get_model(self, model_name: Optional[str] = None) -> EmbeddingModel:
        """Get or create a model instance.

        Args:
            model_name: Model name, defaults to default_model

        Returns:
            Embedding model instance
        """
        model_name = model_name or self.default_model

        if model_name not in self._models:
            if model_name not in self._model_configs:
                raise ValueError(
                    f"Unknown model {model_name}. "
                    f"Available models: {list(self._model_configs.keys())}"
                )

            config = self._model_configs[model_name]
            self._models[model_name] = SentenceTransformerModel(config)

        return self._models[model_name]

    def _compute_text_hash(self, text: str, model_name: str) -> str:
        """Compute hash for text and model combination.

        Args:
            text: Input text
            model_name: Model name

        Returns:
            Hash string
        """
        content = f"{model_name}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()

    def embed_texts(
        self,
        texts: Union[str, List[str]],
        model_name: Optional[str] = None,
        model_type: Optional[ModelType] = None,
        use_cache: bool = True,
        batch_size: Optional[int] = None,
        show_progress: bool = False,
        metadata: Optional[Dict] = None,
    ) -> Union[List[float], List[List[float]]]:
        """Embed one or more texts.

        Args:
            texts: Text or list of texts to embed
            model_name: Specific model to use
            model_type: Type of model to use (query/document/multilingual)
            use_cache: Whether to use cache
            batch_size: Batch size for encoding
            show_progress: Show progress bar
            metadata: Additional metadata for caching

        Returns:
            Embedding vector(s)
        """
        is_single = isinstance(texts, str)
        texts_list: List[str]
        if is_single:
            assert isinstance(texts, str)  # Help mypy understand the type
            texts_list = [texts]
        else:
            assert isinstance(texts, list)  # Help mypy understand the type
            texts_list = texts

        # Select model based on type if not specified
        if model_name is None and model_type is not None:
            model_name = self._select_model_by_type(model_type)

        model = self.get_model(model_name)
        model_name = model_name or self.default_model

        # Check cache if enabled
        if use_cache and self.cache is not None:
            embeddings: List[Tuple[int, List[float]]] = []
            texts_to_encode: List[str] = []
            text_indices: List[int] = []

            for i, text in enumerate(texts_list):
                text_hash = self._compute_text_hash(text, model_name)
                cached = self.cache.get(text_hash)

                if cached is not None:
                    embeddings.append((i, cached))
                else:
                    texts_to_encode.append(text)
                    text_indices.append(i)

            # Encode missing texts
            if texts_to_encode:
                new_embeddings = model.encode(
                    texts_to_encode,
                    batch_size=batch_size,
                    show_progress=show_progress,
                )

                # Cache and combine results
                for idx, text, embedding in zip(text_indices, texts_to_encode, new_embeddings):
                    text_hash = self._compute_text_hash(text, model_name)
                    self.cache.set(
                        text_hash,
                        embedding,
                        metadata={
                            "model": model_name,
                            "dimensions": len(embedding),
                            **(metadata or {}),
                        },
                    )
                    embeddings.append((idx, embedding))

            # Sort by original index
            embeddings.sort(key=lambda x: x[0])
            result = [emb for _, emb in embeddings]
        else:
            # No cache, encode directly
            result = model.encode(
                texts_list,
                batch_size=batch_size,
                show_progress=show_progress,
            )

        return result[0] if is_single else result

    def _select_model_by_type(self, model_type: ModelType) -> str:
        """Select best available model for given type.

        Args:
            model_type: Type of model needed

        Returns:
            Model name
        """
        # Find models matching the type
        candidates = [
            name for name, config in self._model_configs.items() if config.model_type == model_type
        ]

        if not candidates:
            logger.warning(f"No models found for type {model_type}, using default")
            return self.default_model

        # Prefer models that can run on available hardware
        if torch.cuda.is_available():
            # Prefer larger models on GPU
            for name in ["all-mpnet-base-v2", "bge-m3", "all-MiniLM-L12-v2"]:
                if name in candidates:
                    return name
        else:
            # Prefer smaller models on CPU
            for name in ["bge-small-en", "all-MiniLM-L6-v2", "e5-multilingual-small"]:
                if name in candidates:
                    return name

        return candidates[0]

    def embed_documents(self, documents: List[str], **kwargs: Any) -> List[List[float]]:
        """Embed documents using document-optimized model.

        Args:
            documents: List of documents
            **kwargs: Additional arguments for embed_texts

        Returns:
            Document embeddings
        """
        result = self.embed_texts(documents, model_type=ModelType.DOCUMENT, **kwargs)
        # embed_texts always returns List[List[float]] for list input
        return result  # type: ignore[return-value]

    def embed_queries(self, queries: List[str], **kwargs: Any) -> List[List[float]]:
        """Embed queries using query-optimized model.

        Args:
            queries: List of queries
            **kwargs: Additional arguments for embed_texts

        Returns:
            Query embeddings
        """
        result = self.embed_texts(queries, model_type=ModelType.QUERY, **kwargs)
        # embed_texts always returns List[List[float]] for list input
        return result  # type: ignore[return-value]

    def compute_similarity(
        self,
        embeddings1: Union[List[float], List[List[float]]],
        embeddings2: Union[List[float], List[List[float]]],
        metric: str = "cosine",
    ) -> Union[float, np.ndarray]:
        """Compute similarity between embeddings.

        Args:
            embeddings1: First embedding(s)
            embeddings2: Second embedding(s)
            metric: Similarity metric (cosine, dot, euclidean)

        Returns:
            Similarity score(s)
        """
        emb1 = np.array(embeddings1)
        emb2 = np.array(embeddings2)

        if metric == "cosine":
            # Normalize if needed
            if emb1.ndim == 1:
                emb1 = emb1 / np.linalg.norm(emb1)
                emb2 = emb2 / np.linalg.norm(emb2)
                return np.dot(emb1, emb2)  # type: ignore[no-any-return]
            else:
                emb1 = emb1 / np.linalg.norm(emb1, axis=1, keepdims=True)
                emb2 = emb2 / np.linalg.norm(emb2, axis=1, keepdims=True)
                return np.dot(emb1, emb2.T)  # type: ignore[no-any-return]
        elif metric == "dot":
            if emb1.ndim == 1:
                return np.dot(emb1, emb2)  # type: ignore[no-any-return]
            else:
                return np.dot(emb1, emb2.T)  # type: ignore[no-any-return]
        elif metric == "euclidean":
            if emb1.ndim == 1:
                return float(-np.linalg.norm(emb1 - emb2))
            else:
                return -np.linalg.norm(emb1[:, None] - emb2[None, :], axis=2)  # type: ignore[no-any-return]
        else:
            raise ValueError(f"Unknown metric: {metric}")

    def get_model_info(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a model.

        Args:
            model_name: Model name, defaults to default_model

        Returns:
            Model information
        """
        model_name = model_name or self.default_model

        if model_name not in self._model_configs:
            raise ValueError(f"Unknown model: {model_name}")

        config = self._model_configs[model_name]

        return {
            "name": config.name,
            "dimensions": config.dimensions,
            "model_type": config.model_type,
            "max_tokens": config.max_tokens,
            "device": config.device or ("cuda" if torch.cuda.is_available() else "cpu"),
            "loaded": model_name in self._models,
        }

"""Embeddings and vector search functionality."""

from .cache import EmbeddingCache
from .models import (
    PREDEFINED_MODELS,
    EmbeddingModel,
    EmbeddingModelConfig,
    ModelType,
)
from .vector_store import (
    Collection,
    EmbeddingRecord,
    SearchResult,
    VectorStore,
)

# Import modules that depend on sentence_transformers conditionally
try:
    from .collections import (
        CollectionManager,
        ContentType,
        Document,
    )
    from .generator import EmbeddingGenerator
    from .hybrid_search import (
        HybridSearch,
        HybridSearchResult,
        TextIndex,
    )

    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    # If sentence_transformers import fails, set flag
    _SENTENCE_TRANSFORMERS_AVAILABLE = False
    # Set to None for cleaner imports
    CollectionManager = None  # type: ignore[assignment,misc]
    ContentType = None  # type: ignore[assignment,misc]
    Document = None  # type: ignore[assignment,misc]
    EmbeddingGenerator = None  # type: ignore[assignment,misc]
    HybridSearch = None  # type: ignore[assignment,misc]
    HybridSearchResult = None  # type: ignore[assignment,misc]
    TextIndex = None  # type: ignore[assignment,misc]

# Base exports always available
__all__ = [
    # Cache
    "EmbeddingCache",
    # Models
    "PREDEFINED_MODELS",
    "EmbeddingModel",
    "EmbeddingModelConfig",
    "ModelType",
    # Vector Store
    "Collection",
    "EmbeddingRecord",
    "SearchResult",
    "VectorStore",
]

# Add sentence_transformers-dependent exports if available
if _SENTENCE_TRANSFORMERS_AVAILABLE:
    __all__.extend(
        [
            # Collections
            "CollectionManager",
            "ContentType",
            "Document",
            # Generator
            "EmbeddingGenerator",
            # Hybrid Search
            "HybridSearch",
            "HybridSearchResult",
            "TextIndex",
        ]
    )

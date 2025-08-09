"""Configuration for embeddings tests."""

import pytest

# Check if sentence_transformers is available
try:
    import sentence_transformers  # noqa: F401

    # Test actual functionality to catch version incompatibilities
    from sentence_transformers import SentenceTransformer  # noqa: F401

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except (ImportError, AttributeError, Exception):
    # Catch any import errors, including version incompatibilities
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Skip all tests in this directory if sentence_transformers is not available
pytestmark = pytest.mark.skipif(
    not SENTENCE_TRANSFORMERS_AVAILABLE,
    reason="sentence_transformers not available or incompatible version",
)

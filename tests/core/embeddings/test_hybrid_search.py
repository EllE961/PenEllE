"""Tests for hybrid search."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.embeddings.collections import CollectionManager, ContentType, Document
from src.core.embeddings.hybrid_search import (
    HybridSearch,
    HybridSearchResult,
    TextIndex,
)
from src.core.embeddings.vector_store import VectorStore


class TestTextIndex:
    """Tests for TextIndex."""

    @pytest.fixture
    def text_index(self):
        """Create text index."""
        return TextIndex()

    def test_initialization(self, text_index):
        """Test text index initialization."""
        assert len(text_index.documents) == 0
        assert len(text_index.tokenized_corpus) == 0
        assert len(text_index.doc_ids) == 0
        assert text_index.bm25 is None

    def test_tokenize(self, text_index):
        """Test tokenization."""
        text = "This is a TEST sentence, with punctuation!"
        tokens = text_index._tokenize(text)

        # Should lowercase and remove punctuation
        assert "this" in tokens
        assert "test" in tokens
        assert "sentence" in tokens
        assert "with" in tokens
        assert "punctuation" in tokens

        # Should filter short tokens
        assert "is" not in tokens  # Too short
        assert "a" not in tokens  # Too short

    def test_add_documents(self, text_index):
        """Test adding documents."""
        docs = [
            Document(
                content_id="1",
                content_type=ContentType.PAPER,
                text="First document about machine learning",
                metadata={},
            ),
            Document(
                content_id="2",
                content_type=ContentType.PAPER,
                text="Second document about deep learning",
                metadata={},
            ),
        ]

        text_index.add_documents(docs)

        assert len(text_index.documents) == 2
        assert len(text_index.tokenized_corpus) == 2
        assert len(text_index.doc_ids) == 2
        assert text_index.bm25 is not None

    def test_search(self, text_index):
        """Test BM25 search."""
        # Add documents
        docs = [
            Document(
                content_id="1",
                content_type=ContentType.PAPER,
                text="Machine learning is great",
                metadata={},
            ),
            Document(
                content_id="2",
                content_type=ContentType.PAPER,
                text="Deep learning is better",
                metadata={},
            ),
            Document(
                content_id="3",
                content_type=ContentType.PAPER,
                text="Natural language processing",
                metadata={},
            ),
        ]

        text_index.add_documents(docs)

        # Search
        results = text_index.search("machine learning", top_k=2)

        assert len(results) <= 2
        assert results[0][0] == "1"  # First doc should match best
        assert results[0][1] > 0  # Should have positive score

    def test_get_document(self, text_index):
        """Test getting document by ID."""
        doc = Document(
            content_id="1",
            content_type=ContentType.PAPER,
            text="Test document",
            metadata={},
        )

        text_index.add_documents([doc])

        retrieved = text_index.get_document("1")
        assert retrieved == doc

        # Non-existent
        assert text_index.get_document("999") is None

    def test_clear(self, text_index):
        """Test clearing index."""
        # Add documents
        docs = [
            Document(
                content_id=str(i),
                content_type=ContentType.PAPER,
                text=f"Document {i}",
                metadata={},
            )
            for i in range(5)
        ]

        text_index.add_documents(docs)
        assert len(text_index.documents) == 5

        # Clear
        text_index.clear()

        assert len(text_index.documents) == 0
        assert len(text_index.tokenized_corpus) == 0
        assert len(text_index.doc_ids) == 0
        assert text_index.bm25 is None


class TestHybridSearchResult:
    """Tests for HybridSearchResult."""

    def test_result_creation(self):
        """Test creating hybrid search result."""
        result = HybridSearchResult(
            content_id="123",
            content_type="paper",
            bm25_score=0.8,
            semantic_score=0.9,
            hybrid_score=0.85,
            metadata={"title": "Test"},
            text_snippet="Test snippet...",
        )

        assert result.content_id == "123"
        assert result.bm25_score == 0.8
        assert result.semantic_score == 0.9
        assert result.hybrid_score == 0.85


class TestHybridSearch:
    """Tests for HybridSearch."""

    @pytest.fixture
    def mock_vector_store(self):
        """Create mock vector store."""
        return MagicMock(spec=VectorStore)

    @pytest.fixture
    def mock_collection_manager(self):
        """Create mock collection manager."""
        manager = MagicMock(spec=CollectionManager)
        manager.add_documents = AsyncMock()
        manager.search_similar = AsyncMock(return_value=[])
        return manager

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def hybrid_search(self, mock_vector_store, mock_collection_manager, mock_session):
        """Create hybrid search instance."""
        return HybridSearch(
            vector_store=mock_vector_store,
            collection_manager=mock_collection_manager,
            session=mock_session,
            alpha=0.5,
        )

    def test_initialization(self, hybrid_search):
        """Test hybrid search initialization."""
        assert hybrid_search.alpha == 0.5
        assert len(hybrid_search._text_indices) == 0

    @pytest.mark.asyncio
    async def test_index_documents(self, hybrid_search, mock_collection_manager):
        """Test indexing documents."""
        docs = [
            Document(
                content_id="1",
                content_type=ContentType.PAPER,
                text="Test document",
                metadata={},
            ),
        ]

        await hybrid_search.index_documents(docs, "papers")

        # Should add to text index
        assert "papers" in hybrid_search._text_indices
        assert len(hybrid_search._text_indices["papers"].documents) == 1

        # Should add to vector store
        mock_collection_manager.add_documents.assert_called_once_with(
            docs,
            collection_name="papers",
        )

    @pytest.mark.asyncio
    async def test_search(self, hybrid_search, mock_collection_manager):
        """Test hybrid search."""
        # Add documents to text index
        docs = [
            Document(
                content_id="1",
                content_type=ContentType.PAPER,
                text="Machine learning paper",
                metadata={"title": "ML Paper"},
            ),
            Document(
                content_id="2",
                content_type=ContentType.PAPER,
                text="Deep learning paper",
                metadata={"title": "DL Paper"},
            ),
        ]

        text_index = hybrid_search._text_indices["papers"]
        text_index.add_documents(docs)

        # Mock semantic search results
        mock_collection_manager.search_similar.return_value = [
            {
                "content_id": "1",
                "content_type": "paper",
                "score": 0.9,
                "metadata": {"title": "ML Paper"},
            },
            {
                "content_id": "2",
                "content_type": "paper",
                "score": 0.7,
                "metadata": {"title": "DL Paper"},
            },
        ]

        # Search
        results = await hybrid_search.search(
            query="machine learning",
            collection_name="papers",
            limit=10,
        )

        assert len(results) <= 10
        assert all(isinstance(r, HybridSearchResult) for r in results)

        # Results should be sorted by hybrid score
        for i in range(len(results) - 1):
            assert results[i].hybrid_score >= results[i + 1].hybrid_score

    def test_normalize_scores(self, hybrid_search):
        """Test score normalization."""
        scores = {"doc1": 10.0, "doc2": 20.0, "doc3": 30.0}

        normalized = hybrid_search._normalize_scores(scores)

        assert normalized["doc1"] == 0.0  # Min
        assert normalized["doc3"] == 1.0  # Max
        assert 0 < normalized["doc2"] < 1  # Middle

    def test_normalize_scores_empty(self, hybrid_search):
        """Test normalizing empty scores."""
        normalized = hybrid_search._normalize_scores({})
        assert normalized == {}

    def test_normalize_scores_same(self, hybrid_search):
        """Test normalizing identical scores."""
        scores = {"doc1": 5.0, "doc2": 5.0}
        normalized = hybrid_search._normalize_scores(scores)

        assert normalized["doc1"] == 1.0
        assert normalized["doc2"] == 1.0

    def test_combine_results(self, hybrid_search):
        """Test combining BM25 and semantic results."""
        # Setup text index
        text_index = TextIndex()
        docs = [
            Document(
                content_id="1",
                content_type=ContentType.PAPER,
                text="Test 1",
                metadata={},
            ),
            Document(
                content_id="2",
                content_type=ContentType.PAPER,
                text="Test 2",
                metadata={},
            ),
        ]
        text_index.add_documents(docs)

        bm25_results = [("1", 10.0), ("2", 5.0)]
        semantic_results = [
            {"content_id": "1", "score": 0.9, "metadata": {}},
            {"content_id": "3", "score": 0.8, "metadata": {}},  # Different doc
        ]

        combined = hybrid_search._combine_results(
            bm25_results=bm25_results,
            semantic_results=semantic_results,
            alpha=0.6,
            text_index=text_index,
            return_text=False,
            snippet_length=100,
            query="test",
        )

        # Should have all unique documents
        doc_ids = {r.content_id for r in combined}
        assert "1" in doc_ids
        assert "2" in doc_ids
        assert "3" in doc_ids

        # Check hybrid scores
        for result in combined:
            expected_hybrid = 0.6 * result.semantic_score + 0.4 * result.bm25_score
            assert abs(result.hybrid_score - expected_hybrid) < 0.01

    def test_extract_snippet(self, hybrid_search):
        """Test snippet extraction."""
        text = "This is a long text about machine learning. Machine learning is very important for AI. We use deep learning too."
        query = "machine learning"

        snippet = hybrid_search._extract_snippet(text, query, max_length=50)

        assert len(snippet) <= 56  # 50 + "..."
        assert "machine learning" in snippet.lower()

    @pytest.mark.asyncio
    async def test_find_similar_with_keywords(self, hybrid_search, mock_collection_manager):
        """Test search with keyword boosting."""
        # Setup
        docs = [
            Document(
                content_id="1",
                content_type=ContentType.PAPER,
                text="Neural networks and deep learning",
                metadata={},
            ),
        ]

        text_index = hybrid_search._text_indices["papers"]
        text_index.add_documents(docs)

        # Mock search to return base results
        with patch.object(hybrid_search, "search") as mock_search:
            mock_search.return_value = [
                HybridSearchResult(
                    content_id="1",
                    content_type="paper",
                    bm25_score=0.5,
                    semantic_score=0.5,
                    hybrid_score=0.5,
                    metadata={},
                ),
            ]

            results = await hybrid_search.find_similar_with_keywords(
                query="machine learning",
                keywords=["neural", "deep"],
                collection_name="papers",
                keyword_boost=2.0,
            )

            # Result should be boosted
            assert results[0].hybrid_score > 0.5

    @pytest.mark.asyncio
    async def test_search_multiple_collections(self, hybrid_search):
        """Test searching across multiple collections."""
        # Mock search for each collection
        with patch.object(hybrid_search, "search") as mock_search:
            mock_search.side_effect = [
                [
                    HybridSearchResult(
                        content_id="1",
                        content_type="paper",
                        bm25_score=0.8,
                        semantic_score=0.9,
                        hybrid_score=0.85,
                        metadata={},
                    )
                ],
                [
                    HybridSearchResult(
                        content_id="2",
                        content_type="evidence",
                        bm25_score=0.7,
                        semantic_score=0.8,
                        hybrid_score=0.75,
                        metadata={},
                    )
                ],
            ]

            results = await hybrid_search.search_multiple_collections(
                query="test query",
                collection_names=["papers", "evidence"],
                limit_per_collection=5,
                global_limit=10,
            )

            assert len(results) == 2
            assert results[0].hybrid_score >= results[1].hybrid_score
            assert results[0].metadata["collection"] == "papers"
            assert results[1].metadata["collection"] == "evidence"

    def test_update_alpha(self, hybrid_search):
        """Test updating alpha parameter."""
        hybrid_search.update_alpha(0.7)
        assert hybrid_search.alpha == 0.7

        # Test invalid values
        with pytest.raises(ValueError):
            hybrid_search.update_alpha(1.5)

        with pytest.raises(ValueError):
            hybrid_search.update_alpha(-0.1)

    def test_clear_text_index(self, hybrid_search):
        """Test clearing text indices."""
        # Add some indices
        hybrid_search._text_indices["papers"].add_documents(
            [
                Document("1", ContentType.PAPER, "test", {}),
            ]
        )
        hybrid_search._text_indices["evidence"].add_documents(
            [
                Document("2", ContentType.EVIDENCE, "test", {}),
            ]
        )

        # Clear specific
        hybrid_search.clear_text_index("papers")
        assert len(hybrid_search._text_indices["papers"].documents) == 0
        assert len(hybrid_search._text_indices["evidence"].documents) == 1

        # Clear all
        hybrid_search.clear_text_index()
        assert len(hybrid_search._text_indices) == 0

    @pytest.mark.asyncio
    async def test_get_search_stats(self, hybrid_search, mock_vector_store):
        """Test getting search statistics."""
        # Add text index
        hybrid_search._text_indices["papers"].add_documents(
            [
                Document("1", ContentType.PAPER, "test", {}),
            ]
        )

        # Mock vector store stats
        mock_vector_store.get_collection_stats = AsyncMock(
            return_value={
                "total_embeddings": 100,
            }
        )

        stats = await hybrid_search.get_search_stats()

        assert stats["alpha"] == 0.5
        assert "papers" in stats["text_indices"]
        assert stats["text_indices"]["papers"]["document_count"] == 1

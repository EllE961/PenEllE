"""Tests for collection management."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.embeddings.collections import (
    CollectionManager,
    ContentType,
    Document,
)
from src.core.embeddings.generator import EmbeddingGenerator
from src.core.embeddings.vector_store import VectorStore


class TestDocument:
    """Tests for Document class."""

    def test_document_creation(self):
        """Test creating a document."""
        doc_id = str(uuid4())
        doc = Document(
            content_id=doc_id,
            content_type=ContentType.PAPER,
            text="Test paper content",
            metadata={"title": "Test Paper", "year": 2024},
        )

        assert str(doc.content_id) == doc_id
        assert doc.content_type == ContentType.PAPER
        assert doc.text == "Test paper content"
        assert doc.metadata["title"] == "Test Paper"

    def test_to_searchable_text_basic(self):
        """Test converting to searchable text."""
        doc = Document(
            content_id=uuid4(),
            content_type=ContentType.PAPER,
            text="Main content",
            metadata={},
        )

        searchable = doc.to_searchable_text()
        assert searchable == "Main content"

    def test_to_searchable_text_with_metadata(self):
        """Test searchable text with metadata."""
        doc = Document(
            content_id=uuid4(),
            content_type=ContentType.PAPER,
            text="Main content",
            metadata={
                "title": "Test Paper",
                "authors": ["Author 1", "Author 2"],
                "keywords": ["ML", "NLP"],
                "journal": "Test Journal",
            },
        )

        searchable = doc.to_searchable_text()

        assert "Title: Test Paper" in searchable
        assert "Main content" in searchable
        assert "Authors: Author 1, Author 2" in searchable
        assert "Keywords: ML, NLP" in searchable
        assert "Journal: Test Journal" in searchable


class TestCollectionManager:
    """Tests for CollectionManager."""

    @pytest.fixture
    def mock_vector_store(self):
        """Create mock vector store."""
        store = MagicMock(spec=VectorStore)
        store.register_collection = MagicMock()
        store.add_embeddings = AsyncMock(return_value=["emb1", "emb2"])
        store.search = AsyncMock(return_value=[])
        store.get_collection_stats = AsyncMock(return_value={"total_embeddings": 100})
        store.optimize_index = AsyncMock()
        return store

    @pytest.fixture
    def mock_generator(self):
        """Create mock embedding generator."""
        generator = MagicMock(spec=EmbeddingGenerator)
        generator.default_model = "all-MiniLM-L6-v2"
        generator.embed_texts = MagicMock(return_value=[[0.1] * 384])
        return generator

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_vector_store, mock_generator, mock_session):
        """Create collection manager."""
        return CollectionManager(
            vector_store=mock_vector_store,
            embedding_generator=mock_generator,
            session=mock_session,
        )

    def test_initialization(self, manager, mock_vector_store):
        """Test manager initialization."""
        # Should register collections
        assert mock_vector_store.register_collection.call_count >= 4

        # Check registered collections
        call_args_list = mock_vector_store.register_collection.call_args_list
        collection_names = [call[0][0].name for call in call_args_list]

        assert "papers" in collection_names
        assert "evidence" in collection_names
        assert "claims" in collection_names
        assert "sections" in collection_names

    @pytest.mark.asyncio
    async def test_add_documents(self, manager, mock_generator, mock_vector_store):
        """Test adding documents."""
        docs = [
            Document(
                content_id=uuid4(),
                content_type=ContentType.PAPER,
                text="Paper 1",
                metadata={"title": "Test 1"},
            ),
            Document(
                content_id=uuid4(),
                content_type=ContentType.PAPER,
                text="Paper 2",
                metadata={"title": "Test 2"},
            ),
        ]

        # Mock embeddings
        mock_generator.embed_texts.return_value = [[0.1] * 768, [0.2] * 768]

        # Add documents
        embedding_ids = await manager.add_documents(
            docs,
            collection_name="papers",
            batch_size=32,
        )

        assert embedding_ids == ["emb1", "emb2"]

        # Verify embedding generation
        mock_generator.embed_texts.assert_called_once()
        texts = mock_generator.embed_texts.call_args[0][0]
        assert len(texts) == 2

        # Verify vector store call
        mock_vector_store.add_embeddings.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_similar(self, manager, mock_generator, mock_vector_store):
        """Test searching similar documents."""
        # Mock search results
        mock_vector_store.search.return_value = [
            MagicMock(
                content_id="123",
                content_type="paper",
                score=0.95,
                metadata={"title": "Result Paper"},
            ),
        ]

        # Mock query embedding
        mock_generator.embed_texts.return_value = [0.1] * 768

        # Search
        results = await manager.search_similar(
            query="test query",
            collection_name="papers",
            limit=10,
        )

        assert len(results) == 1
        assert results[0]["content_id"] == "123"
        assert results[0]["score"] == 0.95
        assert results[0]["title"] == "Result Paper"

    @pytest.mark.asyncio
    async def test_add_paper(self, manager, mock_generator, mock_vector_store):
        """Test adding a paper with components."""
        paper_id = uuid4()

        # Mock embeddings for different components
        mock_generator.embed_texts.side_effect = [
            [[0.1] * 768],  # Full text
            [[0.2] * 384],  # Abstract
            [[0.3] * 384, [0.4] * 384],  # Sections
        ]

        # Add paper
        result = await manager.add_paper(
            paper_id=paper_id,
            title="Test Paper",
            abstract="Test abstract",
            full_text="Full paper text",
            authors=["Author 1"],
            sections={
                "Introduction": "Intro text",
                "Methods": "Methods text",
            },
        )

        # Should have embeddings for papers, abstract, and sections
        assert "papers" in result
        assert "abstract" in result
        assert "sections" in result

        # Verify calls
        assert mock_generator.embed_texts.call_count == 3
        assert mock_vector_store.add_embeddings.call_count == 3

    @pytest.mark.asyncio
    async def test_add_evidence(self, manager, mock_generator, mock_vector_store):
        """Test adding evidence."""
        evidence_id = uuid4()
        paper_id = uuid4()
        claim_ids = [uuid4(), uuid4()]

        mock_generator.embed_texts.return_value = [[0.1] * 384]

        embedding_ids = await manager.add_evidence(
            evidence_id=evidence_id,
            text="Evidence text",
            paper_id=paper_id,
            claim_ids=claim_ids,
            evidence_type="experimental",
            confidence=0.85,
        )

        assert embedding_ids == ["emb1", "emb2"]

        # Verify metadata
        call_args = mock_vector_store.add_embeddings.call_args
        metadata_list = call_args[1]["metadata_list"]
        assert metadata_list[0]["paper_id"] == str(paper_id)
        assert len(metadata_list[0]["claim_ids"]) == 2
        assert metadata_list[0]["evidence_type"] == "experimental"

    @pytest.mark.asyncio
    async def test_add_claim(self, manager, mock_generator, mock_vector_store):
        """Test adding a claim."""
        claim_id = uuid4()
        evidence_ids = [uuid4(), uuid4()]
        paper_ids = [uuid4()]

        mock_generator.embed_texts.return_value = [[0.1] * 384]

        embedding_ids = await manager.add_claim(
            claim_id=claim_id,
            claim_text="Test claim",
            evidence_ids=evidence_ids,
            paper_ids=paper_ids,
            claim_type="hypothesis",
            confidence=0.75,
            tags=["ML", "NLP"],
        )

        assert embedding_ids == ["emb1", "emb2"]

        # Verify metadata
        call_args = mock_vector_store.add_embeddings.call_args
        metadata_list = call_args[1]["metadata_list"]
        assert len(metadata_list[0]["evidence_ids"]) == 2
        assert len(metadata_list[0]["paper_ids"]) == 1
        assert metadata_list[0]["claim_type"] == "hypothesis"
        assert metadata_list[0]["tags"] == ["ML", "NLP"]

    @pytest.mark.asyncio
    async def test_find_related_evidence(self, manager, mock_generator, mock_vector_store):
        """Test finding related evidence."""
        mock_vector_store.search.return_value = [
            MagicMock(
                content_id="ev1",
                content_type="evidence",
                score=0.85,
                metadata={"evidence_type": "experimental"},
            ),
        ]

        results = await manager.find_related_evidence(
            claim_text="Test claim",
            limit=10,
            threshold=0.7,
        )

        assert len(results) == 1
        assert results[0]["content_id"] == "ev1"
        assert results[0]["score"] == 0.85

        # Verify search parameters
        call_args = mock_vector_store.search.call_args
        assert call_args[1]["collection"] == "evidence"
        assert call_args[1]["threshold"] == 0.7

    @pytest.mark.asyncio
    async def test_find_papers_by_topic(self, manager, mock_generator, mock_vector_store):
        """Test finding papers by topic."""
        mock_vector_store.search.return_value = [
            MagicMock(
                content_id="paper1",
                content_type="paper",
                score=0.9,
                metadata={"title": "ML Paper", "year": 2024},
            ),
        ]

        results = await manager.find_papers_by_topic(
            topic="machine learning",
            limit=5,
            year_range=(2020, 2024),
        )

        assert len(results) == 1
        assert results[0]["title"] == "ML Paper"

    def test_select_model_for_collection(self, manager):
        """Test model selection for collections."""
        assert manager._select_model_for_collection("papers") == "all-mpnet-base-v2"
        assert manager._select_model_for_collection("evidence") == "all-MiniLM-L12-v2"
        assert manager._select_model_for_collection("claims") == "all-MiniLM-L12-v2"
        assert manager._select_model_for_collection("sections") == "all-MiniLM-L6-v2"

        # Unknown collection should use default
        assert (
            manager._select_model_for_collection("unknown")
            == manager.embedding_generator.default_model
        )

    @pytest.mark.asyncio
    async def test_reindex_collection(self, manager, mock_vector_store):
        """Test reindexing collection."""
        await manager.reindex_collection("papers")

        # Should get stats and optimize
        mock_vector_store.get_collection_stats.assert_called_once_with("papers")
        mock_vector_store.optimize_index.assert_called_once_with("papers")

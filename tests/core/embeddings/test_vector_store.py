"""Tests for vector store."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.embeddings.vector_store import (
    Collection,
    SearchResult,
    VectorStore,
)


class TestCollection:
    """Tests for Collection configuration."""

    def test_collection_initialization(self):
        """Test collection initialization."""
        collection = Collection(
            name="test",
            dimensions=384,
            distance_metric="cosine",
            index_type="ivfflat",
            index_params={"lists": 100},
        )

        assert collection.name == "test"
        assert collection.dimensions == 384
        assert collection.distance_metric == "cosine"
        assert collection.index_type == "ivfflat"
        assert collection.index_params == {"lists": 100}

    def test_get_distance_op(self):
        """Test distance operator mapping."""
        # Cosine
        col = Collection("test", 384, distance_metric="cosine")
        assert col.get_distance_op() == "vector_cosine_ops"

        # L2
        col = Collection("test", 384, distance_metric="l2")
        assert col.get_distance_op() == "vector_l2_ops"

        # Inner product
        col = Collection("test", 384, distance_metric="inner_product")
        assert col.get_distance_op() == "vector_ip_ops"

    def test_unknown_distance_metric(self):
        """Test unknown distance metric."""
        col = Collection("test", 384, distance_metric="unknown")

        with pytest.raises(ValueError, match="Unknown distance metric"):
            col.get_distance_op()


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_search_result(self):
        """Test SearchResult creation."""
        result = SearchResult(
            content_id="123",
            content_type="document",
            score=0.95,
            metadata={"key": "value"},
            embedding_id="456",
        )

        assert result.content_id == "123"
        assert result.content_type == "document"
        assert result.score == 0.95
        assert result.metadata == {"key": "value"}
        assert result.embedding_id == "456"


class TestVectorStore:
    """Tests for VectorStore."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = MagicMock(spec=Session)
        session.add_all = MagicMock()
        session.commit = MagicMock()
        session.execute = MagicMock()
        return session

    @pytest.fixture
    def mock_async_session(self):
        """Create mock async database session."""
        session = AsyncMock(spec=AsyncSession)
        session.begin = AsyncMock()
        session.add_all = AsyncMock()
        session.commit = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def vector_store(self, mock_session):
        """Create vector store with mock session."""
        return VectorStore(mock_session)

    @pytest.fixture
    def async_vector_store(self, mock_async_session):
        """Create async vector store."""
        return VectorStore(mock_async_session)

    def test_initialization(self, vector_store):
        """Test vector store initialization."""
        assert vector_store.session is not None
        assert vector_store.is_async is False
        assert len(vector_store._collections) == 0

    def test_async_initialization(self, async_vector_store):
        """Test async vector store initialization."""
        assert async_vector_store.is_async is True

    def test_register_collection(self, vector_store):
        """Test registering collection."""
        collection = Collection("papers", 768)
        vector_store.register_collection(collection)

        assert "papers" in vector_store._collections
        assert vector_store._collections["papers"] == collection

    def test_get_collection(self, vector_store):
        """Test getting collection."""
        collection = Collection("papers", 768)
        vector_store.register_collection(collection)

        retrieved = vector_store.get_collection("papers")
        assert retrieved == collection

    def test_get_unknown_collection(self, vector_store):
        """Test getting unknown collection."""
        with pytest.raises(ValueError, match="Unknown collection"):
            vector_store.get_collection("unknown")

    @pytest.mark.asyncio
    async def test_add_embeddings(self, vector_store):
        """Test adding embeddings."""
        # Register collection
        collection = Collection("test", 384)
        vector_store.register_collection(collection)

        # Mock execute to return nothing
        vector_store.session.execute.return_value = None

        # Add embeddings
        embeddings = [[0.1] * 384, [0.2] * 384]
        content_ids = [str(uuid4()), str(uuid4())]
        content_types = ["document", "document"]

        embedding_ids = await vector_store.add_embeddings(
            collection="test",
            embeddings=embeddings,
            content_ids=content_ids,
            content_types=content_types,
            model_name="test-model",
        )

        # Verify
        assert len(embedding_ids) == 2
        assert all(isinstance(eid, str) for eid in embedding_ids)

        # Check session calls
        vector_store.session.add_all.assert_called_once()
        vector_store.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_embeddings_dimension_error(self, vector_store):
        """Test dimension validation."""
        collection = Collection("test", 100)  # Max 100 dimensions
        vector_store.register_collection(collection)

        embeddings = [[0.1] * 200]  # 200 dimensions

        with pytest.raises(ValueError, match="exceed collection maximum"):
            await vector_store.add_embeddings(
                collection="test",
                embeddings=embeddings,
                content_ids=[str(uuid4())],
                content_types=["document"],
                model_name="test-model",
            )

    @pytest.mark.asyncio
    async def test_search(self, vector_store):
        """Test searching embeddings."""
        # Register collection
        collection = Collection("test", 384, distance_metric="cosine")
        vector_store.register_collection(collection)

        # Mock search results
        mock_results = [
            MagicMock(
                embedding_id=uuid4(),
                content_id=uuid4(),
                content_type="document",
                meta_data={"key": "value"},
                score=0.95,
            ),
        ]

        vector_store.session.execute.return_value.all.return_value = mock_results

        # Search
        query_embedding = [0.1] * 384
        results = await vector_store.search(
            collection="test",
            query_embedding=query_embedding,
            limit=10,
        )

        # Verify
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].score == 0.95

    @pytest.mark.asyncio
    async def test_get_embedding(self, vector_store):
        """Test getting embedding by ID."""
        # Mock result
        mock_record = MagicMock()
        mock_record.embedding = [0.1, 0.2, 0.3]
        mock_record.meta_data = {"key": "value"}

        vector_store.session.execute.return_value.scalar_one_or_none.return_value = mock_record

        # Get embedding
        embedding_id = str(uuid4())
        result = await vector_store.get_embedding(embedding_id)

        assert result is not None
        embedding, metadata = result
        assert embedding == [0.1, 0.2, 0.3]
        assert metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_update_metadata(self, vector_store):
        """Test updating metadata."""
        # Mock record
        mock_record = MagicMock()
        mock_record.meta_data = {"old": "value"}

        vector_store.session.execute.return_value.scalar_one_or_none.return_value = mock_record

        # Update metadata
        embedding_id = str(uuid4())
        new_metadata = {"new": "value"}

        await vector_store.update_metadata(
            embedding_id,
            new_metadata,
            merge=True,
        )

        # Verify merge
        assert mock_record.meta_data == {"old": "value", "new": "value"}
        vector_store.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_embeddings(self, vector_store):
        """Test deleting embeddings."""
        # Mock deletion
        mock_result = MagicMock()
        mock_result.rowcount = 5
        vector_store.session.execute.return_value = mock_result

        # Delete
        deleted = await vector_store.delete_embeddings(
            collection="test",
            content_ids=[str(uuid4()), str(uuid4())],
        )

        assert deleted == 5
        vector_store.session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_collection_stats(self, vector_store):
        """Test getting collection statistics."""
        # Mock count
        vector_store.session.execute.return_value.scalar.return_value = 100

        # Mock model distribution
        model_dist = [
            MagicMock(model_name="model1", count=60),
            MagicMock(model_name="model2", count=40),
        ]

        # Mock dimension distribution
        dim_dist = [
            MagicMock(dimensions=384, count=100),
        ]

        # Set up execute to return different results
        results = [
            MagicMock(scalar=lambda: 100),  # Total count
            MagicMock(__iter__=lambda x: iter(model_dist)),  # Model dist
            MagicMock(__iter__=lambda x: iter(dim_dist)),  # Dim dist
        ]
        vector_store.session.execute.side_effect = results

        # Get stats
        stats = await vector_store.get_collection_stats("test")

        assert stats["collection"] == "test"
        assert stats["total_embeddings"] == 100
        assert stats["model_distribution"]["model1"] == 60
        assert stats["model_distribution"]["model2"] == 40
        assert stats["dimension_distribution"][384] == 100

    @pytest.mark.asyncio
    async def test_optimize_index(self, vector_store):
        """Test index optimization."""
        # Register collection
        collection = Collection("test", 384)
        vector_store.register_collection(collection)

        # Mock stats
        with patch.object(vector_store, "get_collection_stats") as mock_stats:
            mock_stats.return_value = {
                "dimension_distribution": {384: 1500},  # > 1000 threshold
            }

            # Mock index check
            vector_store.session.execute.return_value.scalar.return_value = None

            # Optimize
            await vector_store.optimize_index("test")

            # Should create index
            assert vector_store.session.execute.call_count >= 2  # Check + create
            vector_store.session.commit.assert_called()

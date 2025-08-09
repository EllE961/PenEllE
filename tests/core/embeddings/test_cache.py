"""Tests for embedding cache."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.core.embeddings.cache import EmbeddingCache


class TestEmbeddingCache:
    """Tests for EmbeddingCache."""

    @pytest.fixture
    def temp_cache_path(self):
        """Create temporary cache path."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        yield path
        # Cleanup
        Path(path).unlink(missing_ok=True)

    @pytest.fixture
    def cache(self, temp_cache_path):
        """Create cache instance."""
        return EmbeddingCache(
            cache_path=temp_cache_path,
            ttl_hours=24,
            max_size_mb=10,
        )

    def test_cache_initialization(self, cache, temp_cache_path):
        """Test cache initialization."""
        assert cache.cache_path == temp_cache_path
        assert cache.ttl_hours == 24
        assert cache.max_size_mb == 10
        assert Path(temp_cache_path).exists()

    def test_set_and_get(self, cache):
        """Test setting and getting embeddings."""
        key = "test_key"
        embedding = [0.1, 0.2, 0.3, 0.4]

        # Set embedding
        cache.set(key, embedding)

        # Get embedding
        retrieved = cache.get(key)

        assert retrieved is not None
        assert len(retrieved) == len(embedding)
        assert np.allclose(retrieved, embedding)

    def test_set_with_metadata(self, cache):
        """Test setting embedding with metadata."""
        key = "test_key_meta"
        embedding = [0.5, 0.6, 0.7]
        metadata = {"model": "test-model", "dimensions": 3}

        cache.set(key, embedding, metadata)

        # Verify stored (indirectly through export)
        exports = cache.export_metadata()
        assert len(exports) == 1
        assert exports[0]["hash"] == key
        assert exports[0]["metadata"] == metadata

    def test_get_nonexistent(self, cache):
        """Test getting non-existent key."""
        result = cache.get("nonexistent_key")
        assert result is None

    def test_delete(self, cache):
        """Test deleting embeddings."""
        key = "test_delete"
        embedding = [1.0, 2.0, 3.0]

        # Set and verify
        cache.set(key, embedding)
        assert cache.get(key) is not None

        # Delete
        deleted = cache.delete(key)
        assert deleted is True

        # Verify deleted
        assert cache.get(key) is None

        # Delete non-existent
        deleted = cache.delete("nonexistent")
        assert deleted is False

    def test_ttl_expiration(self, cache):
        """Test TTL expiration."""
        # Create cache with very short TTL
        cache_short_ttl = EmbeddingCache(
            cache_path=cache.cache_path,
            ttl_hours=0,  # Immediate expiration
            max_size_mb=10,
        )

        key = "test_ttl"
        embedding = [1.0, 2.0]

        cache_short_ttl.set(key, embedding)

        # Should be expired immediately
        result = cache_short_ttl.get(key)
        assert result is None

    def test_access_count_update(self, cache):
        """Test access count updates."""
        key = "test_access"
        embedding = [1.0]

        cache.set(key, embedding)

        # Access multiple times
        for _ in range(3):
            cache.get(key)

        # Check stats
        stats = cache.get_stats()
        assert stats["multi_access_entries"] >= 1

    def test_clear(self, cache):
        """Test clearing cache."""
        # Add multiple entries
        for i in range(5):
            cache.set(f"key_{i}", [float(i)])

        # Clear
        cache.clear()

        # Verify cleared
        stats = cache.get_stats()
        assert stats["total_entries"] == 0

    def test_get_stats(self, cache):
        """Test getting cache statistics."""
        # Add some entries
        cache.set("key1", [1.0, 2.0])
        cache.set("key2", [3.0, 4.0])
        cache.get("key1")  # Access to increase count

        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["size_mb"] > 0
        assert "hit_rate" in stats
        assert "age_distribution" in stats

    def test_export_metadata(self, cache):
        """Test exporting metadata."""
        # Add entries with and without metadata
        cache.set("key1", [1.0], {"model": "model1"})
        cache.set("key2", [2.0], {"model": "model2"})
        cache.set("key3", [3.0])  # No metadata

        exports = cache.export_metadata()

        # Should only export entries with metadata
        assert len(exports) == 2

        # Check exported data
        hashes = [e["hash"] for e in exports]
        assert "key1" in hashes
        assert "key2" in hashes
        assert "key3" not in hashes

    def test_size_limit_cleaning(self, cache):
        """Test automatic cleaning when size limit exceeded."""
        # Create cache with very small size limit
        small_cache = EmbeddingCache(
            cache_path=cache.cache_path,
            ttl_hours=24,
            max_size_mb=0.1,  # 100KB limit
        )

        # Add many entries to exceed limit
        for i in range(100):
            small_cache.set(f"key_{i}", list(range(100)))

        # Cache should have cleaned itself
        stats = small_cache.get_stats()
        # The cleaning removes 25% of entries at a time, so after multiple cleanings
        # the cache should stabilize at a reasonable size
        assert stats["size_mb"] < 0.5  # Allow reasonable overhead for SQLite

    def test_thread_safety(self, cache):
        """Test thread-local connections."""
        import threading

        results = []

        def worker(thread_id):
            # Each thread should get its own connection
            key = f"thread_{thread_id}"
            embedding = [float(thread_id)]

            cache.set(key, embedding)
            retrieved = cache.get(key)

            results.append((thread_id, retrieved))

        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify all threads succeeded
        assert len(results) == 5
        for thread_id, embedding in results:
            assert embedding == [float(thread_id)]

    def test_close(self, cache):
        """Test closing cache connection."""
        cache.set("test", [1.0])
        cache.close()

        # Should be able to reopen
        cache.get("test")  # Creates new connection

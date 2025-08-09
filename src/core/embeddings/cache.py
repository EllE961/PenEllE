"""Embedding cache with SQLite persistence."""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

import numpy as np

from ..logging.structured import get_logger

logger = get_logger(__name__)


class EmbeddingCache:
    """Cache for embeddings with SQLite persistence."""

    def __init__(
        self,
        cache_path: Optional[str] = None,
        ttl_hours: int = 24 * 30,  # 30 days default
        max_size_mb: int = 1000,  # 1GB default
    ):
        """Initialize embedding cache.

        Args:
            cache_path: Path to SQLite database file
            ttl_hours: Time-to-live for cache entries in hours
            max_size_mb: Maximum cache size in MB
        """
        self.cache_path = cache_path or str(Path.home() / ".penelle" / "embeddings.db")
        self.ttl_hours = ttl_hours
        self.max_size_mb = max_size_mb
        self._local = threading.local()

        # Ensure directory exists
        Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(self.cache_path, timeout=10.0)
            self._local.conn.row_factory = sqlite3.Row
        return cast(sqlite3.Connection, self._local.conn)

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.cache_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS embeddings (
                    hash TEXT PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    access_count INTEGER DEFAULT 1
                )
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_accessed_at
                ON embeddings(accessed_at)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON embeddings(created_at)
            """
            )

            conn.commit()

        logger.info(f"Initialized embedding cache at {self.cache_path}")

    def get(self, key: str) -> Optional[List[float]]:
        """Get embedding from cache.

        Args:
            key: Cache key (hash)

        Returns:
            Embedding vector or None if not found
        """
        cursor = self.conn.cursor()

        # Check if entry exists and is not expired
        cursor.execute(
            """
            SELECT embedding, created_at
            FROM embeddings
            WHERE hash = ?
        """,
            (key,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        # Check TTL
        created_at = datetime.fromisoformat(row["created_at"])
        if datetime.utcnow() - created_at > timedelta(hours=self.ttl_hours):
            # Expired, delete it
            cursor.execute("DELETE FROM embeddings WHERE hash = ?", (key,))
            self.conn.commit()
            return None

        # Update access time and count
        cursor.execute(
            """
            UPDATE embeddings
            SET accessed_at = CURRENT_TIMESTAMP,
                access_count = access_count + 1
            WHERE hash = ?
        """,
            (key,),
        )
        self.conn.commit()

        # Deserialize embedding
        embedding_bytes = row["embedding"]
        embedding: List[float] = np.frombuffer(embedding_bytes, dtype=np.float32).tolist()

        return embedding

    def set(
        self, key: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Store embedding in cache.

        Args:
            key: Cache key (hash)
            embedding: Embedding vector
            metadata: Optional metadata
        """
        # Check cache size and clean if needed
        self._check_and_clean_cache()

        # Serialize embedding
        embedding_array = np.array(embedding, dtype=np.float32)
        embedding_bytes = embedding_array.tobytes()

        # Serialize metadata
        metadata_json = json.dumps(metadata) if metadata else None

        cursor = self.conn.cursor()

        # Insert or replace
        cursor.execute(
            """
            INSERT OR REPLACE INTO embeddings
            (hash, embedding, metadata, created_at, accessed_at, access_count)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
        """,
            (key, embedding_bytes, metadata_json),
        )

        self.conn.commit()

    def delete(self, key: str) -> bool:
        """Delete embedding from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM embeddings WHERE hash = ?", (key,))
        self.conn.commit()

        return cursor.rowcount > 0

    def clear(self) -> None:
        """Clear all cache entries."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM embeddings")
        self.conn.commit()

        # Vacuum to reclaim space
        cursor.execute("VACUUM")

        logger.info("Cleared embedding cache")

    def _check_and_clean_cache(self) -> None:
        """Check cache size and clean if needed."""
        cursor = self.conn.cursor()

        # Get current database size
        cursor.execute(
            "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
        )
        size_bytes = cursor.fetchone()["size"]
        size_mb = size_bytes / (1024 * 1024)

        if size_mb > self.max_size_mb:
            logger.warning(
                f"Cache size ({size_mb:.1f}MB) exceeds limit ({self.max_size_mb}MB), cleaning..."
            )

            # Delete oldest entries (by access time) until we're under 80% of limit
            # target_size = self.max_size_mb * 0.8

            cursor.execute(
                """
                DELETE FROM embeddings
                WHERE hash IN (
                    SELECT hash FROM embeddings
                    ORDER BY accessed_at ASC
                    LIMIT (SELECT COUNT(*) / 4 FROM embeddings)
                )
            """
            )

            self.conn.commit()

            # Vacuum to reclaim space
            cursor.execute("VACUUM")

            logger.info(f"Cleaned cache, removed {cursor.rowcount} entries")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Cache statistics
        """
        cursor = self.conn.cursor()

        # Total entries
        cursor.execute("SELECT COUNT(*) as count FROM embeddings")
        total_entries = cursor.fetchone()["count"]

        # Database size
        cursor.execute(
            "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
        )
        size_bytes = cursor.fetchone()["size"]

        # Most accessed
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM embeddings
            WHERE access_count > 1
        """
        )
        multi_access = cursor.fetchone()["count"]

        # Age distribution
        cursor.execute(
            """
            SELECT
                COUNT(CASE WHEN julianday('now') - julianday(created_at) <= 1 THEN 1 END) as day_old,
                COUNT(CASE WHEN julianday('now') - julianday(created_at) <= 7 THEN 1 END) as week_old,
                COUNT(CASE WHEN julianday('now') - julianday(created_at) <= 30 THEN 1 END) as month_old
            FROM embeddings
        """
        )
        age_stats = cursor.fetchone()

        return {
            "total_entries": total_entries,
            "size_mb": size_bytes / (1024 * 1024),
            "multi_access_entries": multi_access,
            "hit_rate": multi_access / max(total_entries, 1),
            "age_distribution": {
                "1_day": age_stats["day_old"],
                "7_days": age_stats["week_old"],
                "30_days": age_stats["month_old"],
            },
        }

    def export_metadata(self) -> List[Dict[str, Any]]:
        """Export all metadata for analysis.

        Returns:
            List of metadata entries
        """
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT hash, metadata, created_at, accessed_at, access_count
            FROM embeddings
            WHERE metadata IS NOT NULL
        """
        )

        results = []
        for row in cursor.fetchall():
            entry = {
                "hash": row["hash"],
                "created_at": row["created_at"],
                "accessed_at": row["accessed_at"],
                "access_count": row["access_count"],
            }

            if row["metadata"]:
                entry["metadata"] = json.loads(row["metadata"])

            results.append(entry)

        return results

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            delattr(self._local, "conn")

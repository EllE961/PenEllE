"""Vector store implementation with pgvector backend."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    and_,
    func,
    select,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.types import CHAR, JSON, TypeDecorator, TypeEngine

from ..database.models import Base
from ..logging.structured import get_logger

logger = get_logger(__name__)


class GUID(TypeDecorator):
    """Platform-independent GUID type.

    Uses PostgreSQL's UUID type when available, otherwise uses
    CHAR(36), storing as stringified hex values.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PostgresUUID(as_uuid=True))  # type: ignore[no-any-return]
        else:
            return dialect.type_descriptor(CHAR(36))  # type: ignore[no-any-return]

    def process_bind_param(self, value: Optional[Union[UUID, str]], dialect: Any) -> Optional[str]:
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return value  # type: ignore[return-value]
        else:
            if isinstance(value, UUID):
                return str(value)
            else:
                return value

    def process_result_value(
        self, value: Optional[Union[UUID, str]], dialect: Any
    ) -> Optional[UUID]:
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return value  # type: ignore[return-value]
        else:
            if not isinstance(value, UUID):
                return UUID(value)
            else:
                return value


def get_vector_type(dimensions: int = 1024) -> Any:
    """Get the appropriate vector type based on the database dialect."""
    try:
        # Try to use pgvector if available
        return Vector(dimensions)
    except Exception:
        # Fall back to Text for other databases (like SQLite)
        return Text


def get_json_type() -> Any:
    """Get the appropriate JSON type based on the database dialect."""
    # This will be determined at table creation time
    # PostgreSQL will use JSONB, others will use JSON
    return JSONB


class EmbeddingRecord(Base):
    """Embedding database model."""

    __tablename__ = "embeddings"
    __table_args__ = {"extend_existing": True}

    embedding_id: Any = Column(GUID(), primary_key=True, default=uuid4)
    content_id: Any = Column(GUID(), nullable=False, index=True)
    content_type = Column(String(50), nullable=False)
    collection = Column(String(50), nullable=False, index=True)
    embedding: Any = Column(Vector(1024), nullable=False)  # Using pgvector type
    model_name = Column(String(100), nullable=False, index=True)
    dimensions = Column(Integer, nullable=False)
    meta_data = Column("metadata", JSON, nullable=True)  # Use generic JSON type
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


@dataclass
class SearchResult:
    """Search result with metadata."""

    content_id: str
    content_type: str
    score: float
    metadata: Dict[str, Any]
    embedding_id: Optional[str] = None


class Collection:
    """Vector collection configuration."""

    def __init__(
        self,
        name: str,
        dimensions: int,
        distance_metric: str = "cosine",
        index_type: str = "ivfflat",
        index_params: Optional[Dict[str, Any]] = None,
    ):
        """Initialize collection.

        Args:
            name: Collection name
            dimensions: Vector dimensions
            distance_metric: Distance metric (cosine, l2, inner_product)
            index_type: Index type (ivfflat, hnsw)
            index_params: Index-specific parameters
        """
        self.name = name
        self.dimensions = dimensions
        self.distance_metric = distance_metric
        self.index_type = index_type
        self.index_params = index_params or {}

    def get_distance_op(self) -> str:
        """Get SQLAlchemy distance operator."""
        if self.distance_metric == "cosine":
            return "vector_cosine_ops"
        elif self.distance_metric == "l2":
            return "vector_l2_ops"
        elif self.distance_metric == "inner_product":
            return "vector_ip_ops"
        else:
            raise ValueError(f"Unknown distance metric: {self.distance_metric}")


class VectorStore:
    """Vector store with pgvector backend."""

    def __init__(self, session: Union[Session, AsyncSession]):
        """Initialize vector store.

        Args:
            session: Database session
        """
        self.session = session
        self.is_async = isinstance(session, AsyncSession)
        self._collections: Dict[str, Collection] = {}

    def register_collection(self, collection: Collection) -> None:
        """Register a collection configuration.

        Args:
            collection: Collection configuration
        """
        self._collections[collection.name] = collection
        logger.info(
            f"Registered collection {collection.name} "
            f"with {collection.dimensions}D {collection.distance_metric}"
        )

    def get_collection(self, name: str) -> Collection:
        """Get collection configuration.

        Args:
            name: Collection name

        Returns:
            Collection configuration
        """
        if name not in self._collections:
            raise ValueError(f"Unknown collection: {name}")
        return self._collections[name]

    async def add_embeddings(
        self,
        collection: str,
        embeddings: List[List[float]],
        content_ids: List[Union[str, UUID]],
        content_types: List[str],
        model_name: str,
        metadata_list: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """Add embeddings to store.

        Args:
            collection: Collection name
            embeddings: List of embedding vectors
            content_ids: List of content IDs
            content_types: List of content types
            model_name: Model used for embeddings
            metadata_list: Optional metadata for each embedding

        Returns:
            List of embedding IDs
        """
        if not embeddings:
            return []

        # Validate collection
        col_config = self.get_collection(collection)
        dimensions = len(embeddings[0])

        if dimensions > col_config.dimensions:
            raise ValueError(
                f"Embedding dimensions ({dimensions}) exceed "
                f"collection maximum ({col_config.dimensions})"
            )

        # Prepare records
        records = []
        embedding_ids = []

        for i, (embedding, content_id, content_type) in enumerate(
            zip(embeddings, content_ids, content_types)
        ):
            embedding_id = uuid4()
            embedding_ids.append(str(embedding_id))

            # Ensure content_id is UUID
            if isinstance(content_id, str):
                content_id = UUID(content_id)

            record = EmbeddingRecord(
                embedding_id=embedding_id,
                content_id=content_id,
                content_type=content_type,
                collection=collection,
                embedding=embedding,
                model_name=model_name,
                dimensions=dimensions,
                meta_data=metadata_list[i] if metadata_list else None,
            )
            records.append(record)

        # Add to database
        if self.is_async:
            async with self.session.begin():  # type: ignore
                self.session.add_all(records)
        else:
            self.session.add_all(records)
            self.session.commit()

        logger.info(
            f"Added {len(records)} embeddings to collection {collection} "
            f"using model {model_name}"
        )

        return embedding_ids

    async def search(
        self,
        collection: str,
        query_embedding: List[float],
        limit: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """Search for similar embeddings.

        Args:
            collection: Collection name
            query_embedding: Query embedding vector
            limit: Maximum results
            filters: Optional metadata filters
            threshold: Optional similarity threshold

        Returns:
            List of search results
        """
        col_config = self.get_collection(collection)

        # Build base query
        if col_config.distance_metric == "cosine":
            # Cosine similarity (1 - cosine distance)
            distance_expr = EmbeddingRecord.embedding.cosine_distance(query_embedding)
            similarity_expr = 1 - distance_expr
        elif col_config.distance_metric == "l2":
            # Negative L2 distance for similarity
            distance_expr = EmbeddingRecord.embedding.l2_distance(query_embedding)
            similarity_expr = -distance_expr
        elif col_config.distance_metric == "inner_product":
            # Inner product similarity
            similarity_expr = EmbeddingRecord.embedding.inner_product(query_embedding)
            distance_expr = -similarity_expr
        else:
            raise ValueError(f"Unknown distance metric: {col_config.distance_metric}")

        # Build query
        query = (
            select(
                EmbeddingRecord.embedding_id,
                EmbeddingRecord.content_id,
                EmbeddingRecord.content_type,
                EmbeddingRecord.meta_data,
                similarity_expr.label("score"),
            )
            .where(EmbeddingRecord.collection == collection)
            .order_by(distance_expr)
            .limit(limit)
        )

        # Apply filters
        if filters:
            filter_conditions = []

            # Content type filter
            if "content_type" in filters:
                filter_conditions.append(EmbeddingRecord.content_type == filters["content_type"])

            # Metadata filters
            if "metadata" in filters:
                for key, value in filters["metadata"].items():
                    filter_conditions.append(EmbeddingRecord.metadata[key].astext == str(value))

            if filter_conditions:
                query = query.where(and_(*filter_conditions))

        # Apply threshold
        if threshold is not None:
            query = query.where(similarity_expr >= threshold)

        # Execute query
        if self.is_async:
            result = await self.session.execute(query)  # type: ignore
            rows = result.all()
        else:
            rows = self.session.execute(query).all()  # type: ignore

        # Convert to SearchResult
        results = []
        for row in rows:
            results.append(
                SearchResult(
                    embedding_id=str(row.embedding_id),
                    content_id=str(row.content_id),
                    content_type=row.content_type,
                    score=float(row.score),
                    metadata=row.meta_data or {},
                )
            )

        return results

    async def get_embedding(
        self, embedding_id: Union[str, UUID]
    ) -> Optional[Tuple[List[float], Dict[str, Any]]]:
        """Get embedding by ID.

        Args:
            embedding_id: Embedding ID

        Returns:
            Tuple of (embedding, metadata) or None
        """
        if isinstance(embedding_id, str):
            embedding_id = UUID(embedding_id)

        query = select(EmbeddingRecord).where(EmbeddingRecord.embedding_id == embedding_id)

        if self.is_async:
            result = await self.session.execute(query)  # type: ignore
            record = result.scalar_one_or_none()
        else:
            record = self.session.execute(query).scalar_one_or_none()  # type: ignore

        if record:
            return list(record.embedding), record.meta_data or {}
        return None

    async def update_metadata(
        self,
        embedding_id: Union[str, UUID],
        metadata: Dict[str, Any],
        merge: bool = True,
    ) -> None:
        """Update embedding metadata.

        Args:
            embedding_id: Embedding ID
            metadata: New metadata
            merge: Whether to merge with existing metadata
        """
        if isinstance(embedding_id, str):
            embedding_id = UUID(embedding_id)

        query = select(EmbeddingRecord).where(EmbeddingRecord.embedding_id == embedding_id)

        if self.is_async:
            result = await self.session.execute(query)  # type: ignore
            record = result.scalar_one_or_none()
        else:
            record = self.session.execute(query).scalar_one_or_none()  # type: ignore

        if record:
            if merge and record.meta_data:
                record.meta_data = {**record.meta_data, **metadata}
            else:
                record.meta_data = metadata

            if self.is_async:
                await self.session.commit()  # type: ignore
            else:
                self.session.commit()

    async def delete_embeddings(
        self,
        collection: str,
        content_ids: Optional[List[Union[str, UUID]]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Delete embeddings from collection.

        Args:
            collection: Collection name
            content_ids: Optional list of content IDs to delete
            filters: Optional metadata filters

        Returns:
            Number of deleted embeddings
        """
        conditions = [EmbeddingRecord.collection == collection]

        if content_ids:
            # Convert to UUIDs
            uuid_ids = [UUID(cid) if isinstance(cid, str) else cid for cid in content_ids]
            conditions.append(EmbeddingRecord.content_id.in_(uuid_ids))

        if filters and "metadata" in filters:
            for key, value in filters["metadata"].items():
                conditions.append(EmbeddingRecord.meta_data[key].astext == str(value))

        delete_query = EmbeddingRecord.__table__.delete().where(and_(*conditions))

        if self.is_async:
            result = await self.session.execute(delete_query)
            await self.session.commit()  # type: ignore
        else:
            result = self.session.execute(delete_query)
            self.session.commit()

        deleted_count = result.rowcount
        logger.info(f"Deleted {deleted_count} embeddings from collection {collection}")

        return int(deleted_count)

    async def get_collection_stats(self, collection: str) -> Dict[str, Any]:
        """Get collection statistics.

        Args:
            collection: Collection name

        Returns:
            Collection statistics
        """
        # Count query
        count_query = select(func.count(EmbeddingRecord.embedding_id)).where(
            EmbeddingRecord.collection == collection
        )

        # Model distribution query
        model_query = (
            select(
                EmbeddingRecord.model_name, func.count(EmbeddingRecord.embedding_id).label("count")
            )
            .where(EmbeddingRecord.collection == collection)
            .group_by(EmbeddingRecord.model_name)
        )

        # Dimension distribution query
        dim_query = (
            select(
                EmbeddingRecord.dimensions, func.count(EmbeddingRecord.embedding_id).label("count")
            )
            .where(EmbeddingRecord.collection == collection)
            .group_by(EmbeddingRecord.dimensions)
        )

        if self.is_async:
            count_result = await self.session.execute(count_query)  # type: ignore
            total_count = count_result.scalar() or 0

            model_result = await self.session.execute(model_query)  # type: ignore
            model_dist = {row.model_name: row.count for row in model_result}

            dim_result = await self.session.execute(dim_query)  # type: ignore
            dim_dist = {row.dimensions: row.count for row in dim_result}
        else:
            total_count = self.session.execute(count_query).scalar() or 0  # type: ignore

            model_dist = {row.model_name: row.count for row in self.session.execute(model_query)}  # type: ignore

            dim_dist = {row.dimensions: row.count for row in self.session.execute(dim_query)}  # type: ignore

        return {
            "collection": collection,
            "total_embeddings": total_count,
            "model_distribution": model_dist,
            "dimension_distribution": dim_dist,
        }

    async def optimize_index(self, collection: str) -> None:
        """Optimize vector index for collection.

        Args:
            collection: Collection name
        """
        col_config = self.get_collection(collection)

        # Get dimension statistics
        stats = await self.get_collection_stats(collection)

        for dimensions, count in stats["dimension_distribution"].items():
            if count > 1000:  # Only create index for significant data
                index_name = f"idx_{collection}_vector_{dimensions}"

                # Check if index exists
                check_query = text(
                    """
                    SELECT 1 FROM pg_indexes
                    WHERE tablename = 'embeddings'
                    AND indexname = :index_name
                """
                )

                if self.is_async:
                    result = await self.session.execute(check_query, {"index_name": index_name})  # type: ignore
                    exists = result.scalar() is not None
                else:
                    exists = (
                        self.session.execute(check_query, {"index_name": index_name}).scalar()  # type: ignore
                        is not None
                    )

                if not exists:
                    # Create index
                    create_query = text(
                        f"""
                        CREATE INDEX {index_name} ON embeddings
                        USING ivfflat ((embedding::vector({dimensions})) {col_config.get_distance_op()})
                        WHERE collection = :collection AND dimensions = :dimensions
                    """
                    )

                    if self.is_async:
                        await self.session.execute(  # type: ignore
                            create_query, {"collection": collection, "dimensions": dimensions}
                        )
                        await self.session.commit()  # type: ignore
                    else:
                        self.session.execute(
                            create_query, {"collection": collection, "dimensions": dimensions}
                        )
                        self.session.commit()

                    logger.info(
                        f"Created vector index for collection {collection} "
                        f"with {dimensions} dimensions"
                    )

"""Base repository implementation."""

import logging
from abc import ABC
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar, cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database.models import Base

logger = logging.getLogger(__name__)

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(ABC, Generic[ModelType]):
    """Abstract base repository with common CRUD operations."""

    def __init__(self, model: Type[ModelType], session: AsyncSession) -> None:
        """Initialize the repository.

        Args:
            model: The SQLAlchemy model class
            session: The async database session
        """
        self.model = model
        self.session = session

    async def create(self, **kwargs: Any) -> ModelType:
        """Create a new record.

        Args:
            **kwargs: Model field values

        Returns:
            Created model instance

        Raises:
            IntegrityError: If constraints are violated
            SQLAlchemyError: For other database errors
        """
        try:
            # Filter out schema_version as it's not a database field
            filtered_kwargs = {k: v for k, v in kwargs.items() if k != "schema_version"}
            instance = self.model(**filtered_kwargs)
            self.session.add(instance)
            await self.session.flush()
            logger.info(f"Created {self.model.__name__} with id {instance.id}")
            return instance  # type: ignore[no-any-return]
        except IntegrityError as e:
            logger.error(f"Integrity error creating {self.model.__name__}: {e}")
            await self.session.rollback()
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error creating {self.model.__name__}: {e}")
            await self.session.rollback()
            raise

    async def get_by_id(
        self, id: UUID, load_relationships: Optional[List[str]] = None
    ) -> Optional[ModelType]:
        """Get a record by ID.

        Args:
            id: The record ID
            load_relationships: List of relationship names to eagerly load

        Returns:
            Model instance or None if not found
        """
        try:
            query = select(self.model).where(self.model.id == id)

            # Add eager loading for relationships
            if load_relationships:
                for rel in load_relationships:
                    if hasattr(self.model, rel):
                        query = query.options(selectinload(getattr(self.model, rel)))

            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching {self.model.__name__} by id {id}: {e}")
            raise

    async def get_all(
        self, skip: int = 0, limit: int = 100, load_relationships: Optional[List[str]] = None
    ) -> List[ModelType]:
        """Get all records with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            load_relationships: List of relationship names to eagerly load

        Returns:
            List of model instances
        """
        try:
            query = select(self.model).offset(skip).limit(limit)

            # Add eager loading for relationships
            if load_relationships:
                for rel in load_relationships:
                    if hasattr(self.model, rel):
                        query = query.options(selectinload(getattr(self.model, rel)))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching all {self.model.__name__}: {e}")
            raise

    async def update(self, id: UUID, **kwargs: Any) -> Optional[ModelType]:
        """Update a record by ID.

        Args:
            id: The record ID
            **kwargs: Fields to update

        Returns:
            Updated model instance or None if not found
        """
        try:
            # Remove None values and schema_version
            update_data = {
                k: v for k, v in kwargs.items() if v is not None and k != "schema_version"
            }

            if not update_data:
                logger.warning(f"No data to update for {self.model.__name__} {id}")
                return await self.get_by_id(id)

            stmt = (
                sql_update(self.model)
                .where(self.model.id == id)
                .values(**update_data)
                .returning(self.model)
            )

            result = await self.session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated:
                await self.session.flush()
                logger.info(f"Updated {self.model.__name__} {id}")
                return cast(ModelType, updated)
            else:
                logger.warning(f"{self.model.__name__} {id} not found for update")
                return None
        except IntegrityError as e:
            logger.error(f"Integrity error updating {self.model.__name__} {id}: {e}")
            await self.session.rollback()
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error updating {self.model.__name__} {id}: {e}")
            await self.session.rollback()
            raise

    async def delete(self, id: UUID) -> bool:
        """Delete a record by ID.

        Args:
            id: The record ID

        Returns:
            True if deleted, False if not found
        """
        try:
            stmt = delete(self.model).where(self.model.id == id)
            result = await self.session.execute(stmt)
            deleted = result.rowcount > 0

            if deleted:
                await self.session.flush()
                logger.info(f"Deleted {self.model.__name__} {id}")
            else:
                logger.warning(f"{self.model.__name__} {id} not found for deletion")

            return deleted
        except SQLAlchemyError as e:
            logger.error(f"Error deleting {self.model.__name__} {id}: {e}")
            await self.session.rollback()
            raise

    async def count(self, **filters: Any) -> int:
        """Count records matching filters.

        Args:
            **filters: Field filters

        Returns:
            Count of matching records
        """
        try:
            query = select(func.count()).select_from(self.model)

            # Apply filters
            for field, value in filters.items():
                if hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)

            result = await self.session.execute(query)
            return result.scalar() or 0
        except SQLAlchemyError as e:
            logger.error(f"Error counting {self.model.__name__}: {e}")
            raise

    async def exists(self, **filters: Any) -> bool:
        """Check if a record exists matching filters.

        Args:
            **filters: Field filters

        Returns:
            True if exists, False otherwise
        """
        count = await self.count(**filters)
        return count > 0

    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[ModelType]:
        """Create multiple records in a single operation.

        Args:
            items: List of dictionaries with model field values

        Returns:
            List of created model instances
        """
        try:
            # Filter out schema_version from each item
            filtered_items = [
                {k: v for k, v in item.items() if k != "schema_version"} for item in items
            ]
            instances = [self.model(**item) for item in filtered_items]
            self.session.add_all(instances)
            await self.session.flush()

            logger.info(f"Bulk created {len(instances)} {self.model.__name__} records")
            return instances
        except IntegrityError as e:
            logger.error(f"Integrity error in bulk create for {self.model.__name__}: {e}")
            await self.session.rollback()
            raise
        except SQLAlchemyError as e:
            logger.error(f"Database error in bulk create for {self.model.__name__}: {e}")
            await self.session.rollback()
            raise

    async def bulk_update(self, updates: List[Dict[str, Any]]) -> int:
        """Update multiple records in a single operation.

        Args:
            updates: List of dicts with 'id' and fields to update

        Returns:
            Number of records updated
        """
        try:
            if not updates:
                return 0

            # Ensure all updates have an ID
            for update in updates:
                if "id" not in update:
                    raise ValueError("Each update must include an 'id' field")

            stmt = sql_update(self.model)
            result = await self.session.execute(stmt, updates)
            await self.session.flush()

            updated_count = result.rowcount
            logger.info(f"Bulk updated {updated_count} {self.model.__name__} records")
            return updated_count
        except SQLAlchemyError as e:
            logger.error(f"Error in bulk update for {self.model.__name__}: {e}")
            await self.session.rollback()
            raise

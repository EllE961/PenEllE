"""Database connection manager for PenEllE."""

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Generator, Optional

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from src.core.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(
        self,
        database_url: Optional[str] = None,
        async_database_url: Optional[str] = None,
        echo: bool = False,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_pre_ping: bool = True,
        pool_recycle: int = 3600,
    ) -> None:
        """Initialize database manager.

        Args:
            database_url: Synchronous database URL
            async_database_url: Asynchronous database URL
            echo: Whether to log SQL statements
            pool_size: Number of connections to maintain in pool
            max_overflow: Maximum overflow connections allowed
            pool_pre_ping: Test connections before using
            pool_recycle: Recycle connections after this many seconds
        """
        self.database_url = database_url or settings.DATABASE_URL or ""
        self.async_database_url = async_database_url or settings.ASYNC_DATABASE_URL or ""

        # Create synchronous engine
        if not self.database_url:
            raise ValueError("Database URL is required")
        self.engine = create_engine(
            self.database_url,
            echo=echo,
            poolclass=QueuePool,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_pre_ping=pool_pre_ping,
            pool_recycle=pool_recycle,
        )

        # Create asynchronous engine
        # Use NullPool for SQLite to avoid issues
        if not self.async_database_url:
            raise ValueError("Async database URL is required")
        if "sqlite" in self.async_database_url:
            self.async_engine = create_async_engine(
                self.async_database_url,
                echo=echo,
                poolclass=NullPool,
            )
        else:
            self.async_engine = create_async_engine(
                self.async_database_url,
                echo=echo,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_pre_ping=pool_pre_ping,
                pool_recycle=pool_recycle,
            )

        # Create session factories
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.async_engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

        # Add event listeners
        self._setup_event_listeners()

    def _setup_event_listeners(self) -> None:
        """Set up SQLAlchemy event listeners."""

        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
            """Enable foreign keys for SQLite."""
            if self.database_url and "sqlite" in self.database_url:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a synchronous database session.

        Yields:
            Database session
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an asynchronous database session.

        Yields:
            Async database session
        """
        async with self.AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    def close(self) -> None:
        """Close all database connections."""
        self.engine.dispose()
        logger.info("Synchronous database connections closed")

    async def close_async(self) -> None:
        """Close all async database connections."""
        await self.async_engine.dispose()
        logger.info("Asynchronous database connections closed")

    def create_tables(self) -> None:
        """Create all database tables."""
        from src.core.database.models import Base

        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created")

    def drop_tables(self) -> None:
        """Drop all database tables."""
        from src.core.database.models import Base

        Base.metadata.drop_all(bind=self.engine)
        logger.info("Database tables dropped")

    def check_connection(self) -> bool:
        """Check if database connection is working.

        Returns:
            True if connection is successful
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    async def check_async_connection(self) -> bool:
        """Check if async database connection is working.

        Returns:
            True if connection is successful
        """
        try:
            async with self.async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Async database connection check failed: {e}")
            return False


# Global database manager instance - only create if not in test mode
import os  # noqa: E402

db_manager: Optional[DatabaseManager] = None
if os.getenv("TESTING") != "true":
    db_manager = DatabaseManager()


# Dependency injection helpers
def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session.

    Yields:
        Database session
    """
    if db_manager is None:
        raise RuntimeError("Database manager not initialized")
    with db_manager.get_session() as session:
        yield session


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get async database session.

    Yields:
        Async database session
    """
    if db_manager is None:
        raise RuntimeError("Database manager not initialized")
    async with db_manager.get_async_session() as session:
        yield session


# Aliases for compatibility
get_session = get_db
get_async_session = get_async_db


def get_db_engine() -> Optional[Engine]:
    """Get the database engine."""
    return db_manager.engine if db_manager else None

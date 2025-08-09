"""Tests for database connection manager."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.core.database.connection import DatabaseManager, get_async_db, get_db
from src.core.database.models import Run


class TestDatabaseManager:
    """Test DatabaseManager class."""

    def test_create_database_manager(self, test_db_url, test_async_db_url):
        """Test creating a database manager."""
        manager = DatabaseManager(
            database_url=test_db_url,
            async_database_url=test_async_db_url,
        )

        assert manager.database_url == test_db_url
        assert manager.async_database_url == test_async_db_url
        assert manager.engine is not None
        assert manager.async_engine is not None

        manager.close()

    def test_get_session(self, db_manager):
        """Test getting a synchronous session."""
        with db_manager.get_session() as session:
            assert isinstance(session, Session)
            # Test that we can query
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1

    @pytest.mark.asyncio()
    async def test_get_async_session(self, db_manager):
        """Test getting an asynchronous session."""
        async with db_manager.get_async_session() as session:
            assert isinstance(session, AsyncSession)
            # Test that we can query
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1

    def test_create_and_drop_tables(self, test_db_url, test_async_db_url):
        """Test creating and dropping tables."""
        manager = DatabaseManager(
            database_url=test_db_url,
            async_database_url=test_async_db_url,
        )

        # Create tables
        manager.create_tables()

        # Verify tables exist by creating a record
        with manager.get_session() as session:
            run = Run(
                user_id="550e8400-e29b-41d4-a716-446655440000",
                thesis="Test thesis",
                config={},
                pipeline_version="1.0.0",
            )
            session.add(run)
            session.commit()

            # Query the record
            queried_run = session.query(Run).filter_by(id=run.id).first()
            assert queried_run is not None
            assert queried_run.thesis == "Test thesis"

        # Drop tables
        manager.drop_tables()

        # Verify tables don't exist
        with pytest.raises(Exception):
            with manager.get_session() as session:
                session.query(Run).all()

        manager.close()

    def test_check_connection(self, db_manager):
        """Test checking database connection."""
        assert db_manager.check_connection() is True

    @pytest.mark.asyncio()
    async def test_check_async_connection(self, db_manager):
        """Test checking async database connection."""
        assert await db_manager.check_async_connection() is True

    def test_session_rollback_on_error(self, db_manager):
        """Test that session rollbacks on error."""
        with pytest.raises(ValueError):
            with db_manager.get_session() as session:
                run = Run(
                    user_id="550e8400-e29b-41d4-a716-446655440000",
                    thesis="Test thesis",
                    config={},
                    pipeline_version="1.0.0",
                )
                session.add(run)
                # Force an error
                raise ValueError("Test error")

        # Verify no data was committed
        with db_manager.get_session() as session:
            count = session.query(Run).count()
            assert count == 0

    @pytest.mark.asyncio()
    async def test_async_session_rollback_on_error(self, db_manager):
        """Test that async session rollbacks on error."""
        with pytest.raises(ValueError):
            async with db_manager.get_async_session() as session:
                run = Run(
                    user_id="550e8400-e29b-41d4-a716-446655440000",
                    thesis="Test thesis",
                    config={},
                    pipeline_version="1.0.0",
                )
                session.add(run)
                # Force an error
                raise ValueError("Test error")

        # Verify no data was committed
        async with db_manager.get_async_session() as session:
            result = await session.execute(text("SELECT COUNT(*) FROM runs"))
            count = result.scalar()
            assert count == 0


class TestDependencyInjection:
    """Test dependency injection helpers."""

    def test_get_db_dependency(self):
        """Test get_db dependency function."""
        # This would typically be used with FastAPI
        gen = get_db()
        session = next(gen)
        assert isinstance(session, Session)

        # Clean up
        try:
            next(gen)
        except StopIteration:
            pass

    @pytest.mark.asyncio()
    async def test_get_async_db_dependency(self):
        """Test get_async_db dependency function."""
        # This would typically be used with FastAPI
        gen = get_async_db()
        session = await gen.__anext__()
        assert isinstance(session, AsyncSession)

        # Clean up
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass

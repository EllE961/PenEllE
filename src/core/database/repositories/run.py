"""Repository for Run model operations."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database.models import Run
from src.core.database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class RunRepository(BaseRepository[Run]):
    """Repository for Run model with custom queries."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the RunRepository.

        Args:
            session: The async database session
        """
        super().__init__(Run, session)

    async def get_runs_by_status(
        self, status: str, user_id: Optional[UUID] = None, skip: int = 0, limit: int = 100
    ) -> List[Run]:
        """Get runs by status with optional user filter.

        Args:
            status: Run status to filter by
            user_id: Optional user ID filter
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Run instances
        """
        try:
            query = select(Run).where(Run.status == status)

            if user_id:
                query = query.where(Run.user_id == user_id)

            query = query.order_by(Run.created_at.desc()).offset(skip).limit(limit)

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching runs by status {status}: {e}")
            raise

    async def get_user_runs(
        self, user_id: UUID, skip: int = 0, limit: int = 100, include_artifacts: bool = False
    ) -> List[Run]:
        """Get all runs for a specific user.

        Args:
            user_id: The user ID
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_artifacts: Whether to eager load artifacts

        Returns:
            List of Run instances
        """
        try:
            query = (
                select(Run)
                .where(Run.user_id == user_id)
                .order_by(Run.created_at.desc())
                .offset(skip)
                .limit(limit)
            )

            if include_artifacts:
                query = query.options(selectinload(Run.artifacts))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching runs for user {user_id}: {e}")
            raise

    async def get_active_runs(self, user_id: Optional[UUID] = None) -> List[Run]:
        """Get all active (pending or running) runs.

        Args:
            user_id: Optional user ID filter

        Returns:
            List of active Run instances
        """
        try:
            query = select(Run).where(Run.status.in_(["pending", "running"]))

            if user_id:
                query = query.where(Run.user_id == user_id)

            query = query.order_by(Run.created_at.asc())

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching active runs: {e}")
            raise

    async def update_status(
        self, run_id: UUID, status: str, error_message: Optional[str] = None
    ) -> Optional[Run]:
        """Update run status with optional error message.

        Args:
            run_id: The run ID
            status: New status
            error_message: Optional error message for failed status

        Returns:
            Updated Run instance or None if not found
        """
        update_data: Dict[str, Any] = {"status": status}

        if status == "completed":
            update_data["completed_at"] = datetime.now(timezone.utc)
        elif status == "failed" and error_message:
            update_data["error_message"] = error_message
            update_data["completed_at"] = datetime.now(timezone.utc)

        return await self.update(run_id, **update_data)

    async def get_run_with_all_data(self, run_id: UUID) -> Optional[Run]:
        """Get a run with all related data eagerly loaded.

        Args:
            run_id: The run ID

        Returns:
            Run instance with all relationships loaded or None
        """
        try:
            query = (
                select(Run)
                .where(Run.id == run_id)
                .options(
                    selectinload(Run.sources),
                    selectinload(Run.evidence),
                    selectinload(Run.claims),
                    selectinload(Run.quality_metrics),
                    selectinload(Run.artifacts),
                    selectinload(Run.events),
                )
            )

            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching run with all data for {run_id}: {e}")
            raise

    async def get_runs_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        user_id: Optional[UUID] = None,
        status: Optional[str] = None,
    ) -> List[Run]:
        """Get runs within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            user_id: Optional user ID filter
            status: Optional status filter

        Returns:
            List of Run instances
        """
        try:
            conditions = [Run.created_at >= start_date, Run.created_at <= end_date]

            if user_id:
                conditions.append(Run.user_id == user_id)

            if status:
                conditions.append(Run.status == status)

            query = select(Run).where(and_(*conditions)).order_by(Run.created_at.desc())

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching runs by date range: {e}")
            raise

    async def get_run_statistics(self, user_id: Optional[UUID] = None) -> dict:
        """Get statistics about runs.

        Args:
            user_id: Optional user ID filter

        Returns:
            Dictionary with run statistics
        """
        try:
            base_query = select(Run)
            if user_id:
                base_query = base_query.where(Run.user_id == user_id)

            # Count by status
            status_counts = {}
            for status in ["pending", "running", "completed", "failed", "cancelled"]:
                count_query = select(func.count()).select_from(
                    base_query.where(Run.status == status).subquery()
                )
                result = await self.session.execute(count_query)
                status_counts[status] = result.scalar() or 0

            # Total count
            total_query = select(func.count()).select_from(base_query.subquery())
            total_result = await self.session.execute(total_query)
            total = total_result.scalar() or 0

            # Average completion time for successful runs
            completion_time_query = (
                select(func.avg(func.extract("epoch", Run.completed_at - Run.created_at)))
                .select_from(base_query.subquery())
                .where(and_(Run.status == "completed", Run.completed_at.isnot(None)))
            )
            completion_result = await self.session.execute(completion_time_query)
            avg_completion_seconds = completion_result.scalar()

            return {
                "total": total,
                "by_status": status_counts,
                "average_completion_seconds": avg_completion_seconds,
                "success_rate": (status_counts["completed"] / total * 100 if total > 0 else 0),
            }
        except SQLAlchemyError as e:
            logger.error(f"Error calculating run statistics: {e}")
            raise

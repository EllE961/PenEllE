"""Event persistence handler for storing events in database."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select

from src.core.database import get_async_session
from src.core.database.models import EventLog
from src.core.events import Event, EventType
from src.core.logging import get_logger

from .base import BaseEventHandler

logger = get_logger(__name__)


class PersistenceHandler(BaseEventHandler):
    """Handler that persists events to the database."""

    def __init__(self, batch_size: int = 10, flush_interval: float = 5.0):
        """Initialize the persistence handler.

        Args:
            batch_size: Number of events to batch before persisting
            flush_interval: Seconds between automatic flushes
        """
        super().__init__(set(EventType))  # Handle all event types
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._event_buffer: List[Dict[str, Any]] = []
        self._last_flush = datetime.utcnow()

    async def _initialize(self) -> None:
        """Initialize persistence handler."""
        logger.info(f"Persistence handler initialized (batch_size={self.batch_size})")

    async def _shutdown(self) -> None:
        """Cleanup persistence handler."""
        # Flush any remaining events
        if self._event_buffer:
            await self._flush_events()
        logger.info("Persistence handler shutdown")

    async def handle(self, event: Event) -> None:
        """Persist event to database.

        Args:
            event: Event to persist
        """
        try:
            # Convert event to dict
            event_data = event.to_dict() if hasattr(event, "to_dict") else event.payload

            # Add to buffer
            self._event_buffer.append(event_data)

            # Check if we should flush
            should_flush = (
                len(self._event_buffer) >= self.batch_size
                or (datetime.utcnow() - self._last_flush).total_seconds() >= self.flush_interval
            )

            if should_flush:
                await self._flush_events()

        except Exception as e:
            logger.error(f"Failed to persist event {event.id}: {e}")

    async def _flush_events(self) -> None:
        """Flush buffered events to database."""
        if not self._event_buffer:
            return

        events_to_persist = self._event_buffer.copy()
        self._event_buffer.clear()
        self._last_flush = datetime.utcnow()

        try:
            async for session in get_async_session():
                # Create EventLog entries
                event_logs = []
                for event_data in events_to_persist:
                    event_log = EventLog(
                        event_id=event_data["id"],
                        event_type=event_data["type"],
                        run_id=event_data["run_id"],
                        stage=event_data.get("stage"),
                        timestamp=datetime.fromisoformat(event_data["timestamp"]),
                        payload=event_data,
                        metadata=event_data.get("metadata", {}),
                    )
                    event_logs.append(event_log)

                # Bulk insert
                session.add_all(event_logs)
                await session.commit()

                logger.debug(f"Persisted {len(event_logs)} events to database")

        except Exception as e:
            logger.error(f"Failed to flush events to database: {e}")
            # Re-add events to buffer for retry
            self._event_buffer.extend(events_to_persist)

    async def query_events(
        self,
        run_id: Optional[str] = None,
        event_types: Optional[List[EventType]] = None,
        stage: Optional[str] = None,
        from_timestamp: Optional[datetime] = None,
        to_timestamp: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query events from database.

        Args:
            run_id: Filter by run ID
            event_types: Filter by event types
            stage: Filter by stage
            from_timestamp: Start timestamp
            to_timestamp: End timestamp
            limit: Maximum results

        Returns:
            List of event dictionaries
        """
        try:
            async for session in get_async_session():
                # Build query
                query = select(EventLog)

                # Apply filters
                conditions = []
                if run_id:
                    conditions.append(EventLog.run_id == run_id)
                if event_types:
                    conditions.append(EventLog.event_type.in_([e.value for e in event_types]))
                if stage:
                    conditions.append(EventLog.stage == stage)
                if from_timestamp:
                    conditions.append(EventLog.timestamp >= from_timestamp)
                if to_timestamp:
                    conditions.append(EventLog.timestamp <= to_timestamp)

                if conditions:
                    query = query.where(and_(*conditions))

                # Order by timestamp and apply limit
                query = query.order_by(EventLog.timestamp.desc()).limit(limit)

                # Execute query
                result = await session.execute(query)
                event_logs = result.scalars().all()

                # Convert to dictionaries
                return [dict(log.payload) for log in event_logs]

        except Exception as e:
            logger.error(f"Failed to query events: {e}")
            return []

        # This should never be reached due to async generator, but mypy needs it
        return []

    async def get_run_events(self, run_id: str) -> List[Dict[str, Any]]:
        """Get all events for a specific run.

        Args:
            run_id: Pipeline run ID

        Returns:
            List of event dictionaries ordered by timestamp
        """
        return await self.query_events(run_id=run_id, limit=1000)

    async def get_latest_events(
        self, event_type: EventType, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get latest events of a specific type.

        Args:
            event_type: Event type to query
            limit: Maximum results

        Returns:
            List of event dictionaries
        """
        return await self.query_events(event_types=[event_type], limit=limit)

    async def cleanup_old_events(self, retention_days: int = 30) -> int:
        """Delete events older than retention period.

        Args:
            retention_days: Number of days to retain events

        Returns:
            Number of events deleted
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

            async for session in get_async_session():
                # Delete old events
                result = await session.execute(
                    EventLog.__table__.delete().where(EventLog.timestamp < cutoff_date)
                )
                await session.commit()

                deleted_count = result.rowcount
                logger.info(f"Deleted {deleted_count} events older than {retention_days} days")
                return deleted_count or 0

        except Exception as e:
            logger.error(f"Failed to cleanup old events: {e}")
            return 0

        # This should never be reached due to async generator, but mypy needs it
        return 0

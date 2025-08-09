"""Event bus implementation using Redis Streams.

This module provides an async event bus with:
- Publish/subscribe pattern
- Event persistence
- Retry logic for failed handlers
- Event replay capability
"""

import asyncio
import json
import uuid
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Set, Union

import redis.asyncio as redis
from redis.exceptions import RedisError

from src.core.config import get_config_loader
from src.core.logging import get_logger

logger = get_logger(__name__)


class EventBusError(Exception):
    """Base exception for event bus errors."""

    pass


class HandlerError(EventBusError):
    """Exception raised when an event handler fails."""

    pass


class Event:
    """Base event class."""

    def __init__(self, event_type: str, payload: Dict[str, Any], event_id: Optional[str] = None):
        self.id = event_id or str(uuid.uuid4())
        self.type = event_type
        self.timestamp = datetime.utcnow()
        self.payload = payload

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        event = cls(event_type=data["type"], payload=data["payload"], event_id=data["id"])
        event.timestamp = datetime.fromisoformat(data["timestamp"])
        return event


class EventHandler:
    """Wrapper for event handlers with metadata."""

    def __init__(
        self,
        handler_id: str,
        handler: Callable,
        event_types: Set[str],
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.id = handler_id
        self.handler = handler
        self.event_types = event_types
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.is_active = True

    async def handle(self, event: Event) -> Any:
        """Execute the handler with retry logic."""
        if not self.is_active:
            return

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(self.handler):
                    return await self.handler(event)
                else:
                    return self.handler(event)
            except Exception as e:
                last_error = e
                logger.error(f"Handler {self.id} failed on attempt {attempt + 1}: {e}")

                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))

        raise HandlerError(
            f"Handler {self.id} failed after {self.max_retries + 1} attempts"
        ) from last_error


class EventBus:
    """Async event bus using Redis Streams."""

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        stream_key: str = "penelle:events",
        consumer_group: str = "penelle-consumers",
        max_stream_length: int = 10000,
    ):
        """Initialize the event bus.

        Args:
            redis_client: Redis async client instance
            stream_key: Redis stream key for events
            consumer_group: Consumer group name
            max_stream_length: Maximum number of events to keep in stream
        """
        self.redis = redis_client
        self.stream_key = stream_key
        self.consumer_group = consumer_group
        self.consumer_name = f"{consumer_group}-{uuid.uuid4().hex[:8]}"
        self.max_stream_length = max_stream_length

        self._handlers: Dict[str, EventHandler] = {}
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to Redis if not already connected."""
        if self.redis is None:
            config = get_config_loader().load_config("deployment")
            redis_url = config.get("redis", {}).get("url", "redis://localhost:6379")
            self.redis = await redis.from_url(redis_url, decode_responses=True)

        # Create consumer group if it doesn't exist
        try:
            await self.redis.xgroup_create(self.stream_key, self.consumer_group, id="0")
            logger.info(f"Created consumer group: {self.consumer_group}")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            self.redis = None

    async def publish(self, event: Event) -> str:
        """Publish an event to the stream.

        Args:
            event: Event to publish

        Returns:
            Event ID

        Raises:
            EventBusError: If publishing fails
        """
        try:
            if not self.redis:
                await self.connect()

            # Add event to stream with automatic trimming
            event_data = json.dumps(event.to_dict())
            assert self.redis is not None  # Guaranteed by connect() call above
            stream_id = await self.redis.xadd(
                self.stream_key,
                {"event": event_data},
                maxlen=self.max_stream_length,
                approximate=True,
            )

            logger.debug(f"Published event {event.id} of type {event.type} to stream {stream_id}")
            return str(stream_id)

        except RedisError as e:
            logger.error(f"Failed to publish event: {e}")
            raise EventBusError(f"Failed to publish event: {e}") from e

    def subscribe(
        self,
        event_types: Union[str, List[str]],
        handler: Callable,
        handler_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """Subscribe a handler to event types.

        Args:
            event_types: Event type(s) to subscribe to
            handler: Async or sync callable to handle events
            handler_id: Optional handler ID
            max_retries: Maximum retry attempts for failed handlers

        Returns:
            Handler ID
        """
        if isinstance(event_types, str):
            event_types = [event_types]

        handler_id = handler_id or f"handler-{uuid.uuid4().hex[:8]}"

        handler_wrapper = EventHandler(
            handler_id=handler_id,
            handler=handler,
            event_types=set(event_types),
            max_retries=max_retries,
        )

        self._handlers[handler_id] = handler_wrapper
        logger.info(f"Subscribed handler {handler_id} to events: {event_types}")

        return handler_id

    def unsubscribe(self, handler_id: str) -> bool:
        """Unsubscribe a handler.

        Args:
            handler_id: Handler ID to unsubscribe

        Returns:
            True if handler was found and removed
        """
        if handler_id in self._handlers:
            self._handlers[handler_id].is_active = False
            del self._handlers[handler_id]
            logger.info(f"Unsubscribed handler: {handler_id}")
            return True
        return False

    async def start(self) -> None:
        """Start consuming events from the stream."""
        if self._running:
            return

        self._running = True

        if not self.redis:
            await self.connect()

        # Start consumer task
        consumer_task = asyncio.create_task(self._consume_events())
        self._tasks.add(consumer_task)
        consumer_task.add_done_callback(self._tasks.discard)

        logger.info(f"Started event bus consumer: {self.consumer_name}")

    async def stop(self) -> None:
        """Stop consuming events."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        await self.disconnect()
        logger.info("Stopped event bus")

    async def _consume_events(self) -> None:
        """Main consumer loop."""
        while self._running:
            try:
                # Read new messages from stream
                assert self.redis is not None  # Guaranteed by start()
                messages = await self.redis.xreadgroup(
                    self.consumer_group,
                    self.consumer_name,
                    {self.stream_key: ">"},
                    count=10,
                    block=1000,  # Block for 1 second
                )

                if not messages:
                    continue

                for stream, stream_messages in messages:
                    for message_id, data in stream_messages:
                        await self._process_message(message_id, data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in event consumer: {e}")
                await asyncio.sleep(1)

    async def _process_message(self, message_id: str, data: Dict[str, Any]) -> None:
        """Process a single message from the stream."""
        try:
            # Parse event
            event_data = json.loads(data["event"])
            event = Event.from_dict(event_data)

            # Find matching handlers
            matching_handlers = [
                handler
                for handler in self._handlers.values()
                if event.type in handler.event_types and handler.is_active
            ]

            if not matching_handlers:
                logger.debug(f"No handlers for event type: {event.type}")
                assert self.redis is not None  # Guaranteed by _consume_events
                await self.redis.xack(self.stream_key, self.consumer_group, message_id)
                return

            # Execute handlers concurrently
            tasks = []
            for handler in matching_handlers:
                task = asyncio.create_task(self._execute_handler(handler, event))
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Check for failures
            failures = [r for r in results if isinstance(r, Exception)]
            if failures:
                logger.error(f"Some handlers failed for event {event.id}: {failures}")
                # Could implement dead letter queue here

            # Acknowledge message
            assert self.redis is not None  # Guaranteed by _consume_events
            await self.redis.xack(self.stream_key, self.consumer_group, message_id)

        except Exception as e:
            logger.error(f"Failed to process message {message_id}: {e}")

    async def _execute_handler(self, handler: EventHandler, event: Event) -> None:
        """Execute a handler with error handling."""
        try:
            await handler.handle(event)
        except Exception as e:
            logger.error(f"Handler {handler.id} failed for event {event.id}: {e}")
            raise

    async def replay_events(
        self,
        from_timestamp: datetime,
        event_types: Optional[List[str]] = None,
        handler: Optional[Callable] = None,
    ) -> int:
        """Replay events from a specific timestamp.

        Args:
            from_timestamp: Start timestamp for replay
            event_types: Optional list of event types to replay
            handler: Optional handler for replayed events

        Returns:
            Number of events replayed
        """
        if not self.redis:
            await self.connect()

        # Convert timestamp to Redis stream ID format
        start_id = f"{int(from_timestamp.timestamp() * 1000)}-0"

        count = 0
        last_id = start_id

        while True:
            # Read events in batches
            assert self.redis is not None  # Guaranteed by connect() check in replay_events
            messages = await self.redis.xrange(self.stream_key, min=last_id, max="+", count=100)

            if not messages:
                break

            for message_id, data in messages:
                try:
                    event_data = json.loads(data["event"])
                    event = Event.from_dict(event_data)

                    # Filter by event types if specified
                    if event_types and event.type not in event_types:
                        continue

                    # Execute handler if provided
                    if handler:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)

                    count += 1

                except Exception as e:
                    logger.error(f"Error replaying event from message {message_id}: {e}")

                last_id = message_id

            # If we got less than 100 messages, we've reached the end
            if len(messages) < 100:
                break

        logger.info(f"Replayed {count} events from {from_timestamp}")
        return count

    async def get_event_stats(self) -> Dict[str, Any]:
        """Get statistics about the event stream.

        Returns:
            Dictionary with stream statistics
        """
        if not self.redis:
            await self.connect()

        assert self.redis is not None  # Guaranteed by connect() call above
        info = await self.redis.xinfo_stream(self.stream_key)

        return {
            "length": info["length"],
            "first_entry": info.get("first-entry"),
            "last_entry": info.get("last-entry"),
            "consumer_groups": info.get("groups", 0),
            "max_length": self.max_stream_length,
        }


# Global event bus instance
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """Get the global event bus instance.

    Returns:
        EventBus instance
    """
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# Decorator for event handlers
def event_handler(event_types: Union[str, List[str]], handler_id: Optional[str] = None) -> Callable:
    """Decorator to register a function as an event handler.

    Args:
        event_types: Event type(s) to handle
        handler_id: Optional handler ID

    Example:
        @event_handler("user.created")
        async def handle_user_created(event: Event):
            print(f"User created: {event.payload}")
    """

    def decorator(func: Callable) -> Callable:
        # Register handler on first call
        registered = False

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal registered
            if not registered:
                bus = get_event_bus()
                bus.subscribe(event_types, func, handler_id)
                registered = True
            return await func(*args, **kwargs)

        return wrapper

    return decorator

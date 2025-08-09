"""Base handler class for event processing."""

from abc import ABC, abstractmethod
from typing import Any, Set

from src.core.events import Event, EventType
from src.core.logging import get_logger

logger = get_logger(__name__)


class BaseEventHandler(ABC):
    """Abstract base class for event handlers."""

    def __init__(self, event_types: Set[EventType]):
        """Initialize the handler.

        Args:
            event_types: Set of event types this handler processes
        """
        self.event_types = event_types
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize handler resources."""
        if not self._initialized:
            await self._initialize()
            self._initialized = True

    async def shutdown(self) -> None:
        """Cleanup handler resources."""
        if self._initialized:
            await self._shutdown()
            self._initialized = False

    @abstractmethod
    async def _initialize(self) -> None:
        """Handler-specific initialization."""
        pass

    @abstractmethod
    async def _shutdown(self) -> None:
        """Handler-specific cleanup."""
        pass

    @abstractmethod
    async def handle(self, event: Event) -> Any:
        """Process an event.

        Args:
            event: Event to process

        Returns:
            Handler-specific result
        """
        pass

    def should_handle(self, event: Event) -> bool:
        """Check if this handler should process the event.

        Args:
            event: Event to check

        Returns:
            True if handler should process the event
        """
        return event.type in self.event_types

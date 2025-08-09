"""WebSocket handler for real-time event streaming."""

import asyncio
import json
import weakref
from datetime import datetime
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

from src.core.events import Event, EventType, deserialize_event
from src.core.logging import get_logger

from .base import BaseEventHandler

logger = get_logger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for event streaming."""

    def __init__(self) -> None:
        """Initialize the WebSocket manager."""
        # Use weakref to prevent memory leaks
        self._connections: Dict[str, weakref.WeakSet[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: Optional[str] = None) -> None:
        """Connect a new WebSocket client.

        Args:
            websocket: WebSocket connection
            run_id: Optional run ID to subscribe to specific run events
        """
        await websocket.accept()

        async with self._lock:
            # Subscribe to global events or run-specific events
            key = run_id or "__global__"
            if key not in self._connections:
                self._connections[key] = weakref.WeakSet()
            self._connections[key].add(websocket)

        logger.info(f"WebSocket client connected (run_id={run_id})")

    async def disconnect(self, websocket: WebSocket, run_id: Optional[str] = None) -> None:
        """Disconnect a WebSocket client.

        Args:
            websocket: WebSocket connection
            run_id: Run ID if subscribed to specific run
        """
        async with self._lock:
            key = run_id or "__global__"
            if key in self._connections:
                self._connections[key].discard(websocket)
                # Clean up empty sets
                if not self._connections[key]:
                    del self._connections[key]

        logger.info(f"WebSocket client disconnected (run_id={run_id})")

    async def broadcast(self, message: Dict[str, Any], run_id: Optional[str] = None) -> None:
        """Broadcast message to connected clients.

        Args:
            message: Message to broadcast
            run_id: Send to run-specific subscribers only
        """
        # Get relevant connections
        keys = []
        if run_id:
            keys.append(run_id)
        keys.append("__global__")  # Always send to global subscribers

        # Collect all websockets to send to
        websockets: Set[WebSocket] = set()
        async with self._lock:
            for key in keys:
                if key in self._connections:
                    websockets.update(self._connections[key])

        if not websockets:
            return

        # Send to all connections
        message_text = json.dumps(message)
        disconnected = []

        for websocket in websockets:
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                logger.debug(f"Failed to send to websocket: {e}")
                disconnected.append(websocket)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for key, connections in self._connections.items():
                    for ws in disconnected:
                        connections.discard(ws)

    async def send_to_run(self, run_id: str, message: Dict[str, Any]) -> None:
        """Send message to subscribers of a specific run.

        Args:
            run_id: Run ID
            message: Message to send
        """
        await self.broadcast(message, run_id)

    def get_connection_count(self) -> Dict[str, int]:
        """Get count of connections per run ID.

        Returns:
            Dictionary of run_id to connection count
        """
        counts = {}
        for key, connections in self._connections.items():
            counts[key] = len(connections)
        return counts


# Global WebSocket manager instance
_websocket_manager = WebSocketManager()


def get_websocket_manager() -> WebSocketManager:
    """Get the global WebSocket manager instance."""
    return _websocket_manager


class WebSocketHandler(BaseEventHandler):
    """Handler that streams events to WebSocket clients."""

    def __init__(self, manager: Optional[WebSocketManager] = None):
        """Initialize the WebSocket handler.

        Args:
            manager: WebSocket manager instance
        """
        super().__init__(set(EventType))  # Handle all event types
        self.manager = manager or get_websocket_manager()

    async def _initialize(self) -> None:
        """Initialize WebSocket handler."""
        logger.info("WebSocket handler initialized")

    async def _shutdown(self) -> None:
        """Cleanup WebSocket handler."""
        logger.info("WebSocket handler shutdown")

    async def handle(self, event: Event) -> None:
        """Stream event to WebSocket clients.

        Args:
            event: Event to stream
        """
        try:
            # Deserialize to get typed event
            event_data = event.to_dict() if hasattr(event, "to_dict") else event.payload
            typed_event = deserialize_event(event_data)

            # Build WebSocket message
            message = self._build_message(typed_event)

            # Broadcast to relevant clients
            await self.manager.broadcast(message, typed_event.run_id)

        except Exception as e:
            logger.error(f"Failed to stream event {event.id}: {e}")

    def _build_message(self, event: Any) -> Dict[str, Any]:
        """Build WebSocket message from event.

        Args:
            event: Typed event instance

        Returns:
            Message dictionary
        """
        # Base message structure
        message: Dict[str, Any] = {
            "type": "event",
            "timestamp": datetime.utcnow().isoformat(),
            "event": {
                "id": event.id,
                "type": event.type,
                "timestamp": event.timestamp.isoformat(),
                "run_id": event.run_id,
            },
        }

        # Add stage if present
        if hasattr(event, "stage") and event.stage:
            message["event"]["stage"] = event.stage

        # Add event-specific data based on type
        event_type = EventType(event.type)

        if event_type == EventType.RUN_STARTED:
            message["event"]["topic"] = event.topic
            message["event"]["user_id"] = event.user_id

        elif event_type == EventType.RUN_COMPLETED:
            message["event"]["duration_seconds"] = event.duration_seconds
            message["event"]["metrics"] = event.metrics

        elif event_type in [EventType.RUN_FAILED, EventType.STAGE_FAILED]:
            message["event"]["error_message"] = event.error_message
            message["event"]["error_type"] = event.error_type

        elif event_type == EventType.STAGE_STARTED:
            message["event"]["retry_count"] = event.retry_count

        elif event_type == EventType.STAGE_COMPLETED:
            message["event"]["duration_seconds"] = event.duration_seconds
            message["event"]["outputs"] = event.outputs

        elif event_type == EventType.SOURCE_FOUND:
            message["event"]["title"] = event.title
            message["event"]["quality_score"] = event.quality_score

        elif event_type == EventType.QUALITY_CHECK_FAILED:
            message["event"]["check_name"] = event.check_name
            message["event"]["score"] = event.score
            message["event"]["failures"] = event.failures

        elif event_type == EventType.ERROR_OCCURRED:
            message["event"]["severity"] = event.severity
            message["event"]["error_message"] = event.error_message

        # Add metadata if present
        if hasattr(event, "metadata") and event.metadata:
            message["event"]["metadata"] = event.metadata

        return message

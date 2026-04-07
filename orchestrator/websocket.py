"""
WebSocket connection manager for real-time notifications.
"""
from typing import Set
import json
import asyncio

from fastapi import WebSocket

from orchestrator.config import log


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages."""

    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.add(websocket)
        log.info("WebSocket connected. Total connections: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        self.active_connections.discard(websocket)
        log.info("WebSocket disconnected. Total connections: %d", len(self.active_connections))

    async def broadcast(self, message: dict) -> None:
        """Broadcast a message to all connected clients.

        Failed sends are gracefully handled and the connection is removed.
        """
        if not self.active_connections:
            log.debug("[WS] No connections to broadcast to: %s", message)
            return

        # Skip logging for log_line events — logging would trigger another broadcast, causing infinite loop
        if message.get("type") != "log_line":
            log.debug("[WS] Broadcasting to %d clients: %s", len(self.active_connections), message.get("type"))
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                log.warning("Failed to send to WebSocket client: %s", e)
                disconnected.add(connection)

        # Clean up failed connections
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_type(self, event_type: str, **kwargs) -> None:
        """Convenience method to broadcast an event with type and payload."""
        message = {"type": event_type, **kwargs}
        await self.broadcast(message)


# Global singleton
manager = ConnectionManager()

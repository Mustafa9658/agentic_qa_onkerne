"""
WebSocket Connection Manager

Manages WebSocket connections and broadcasts messages.
Uses singleton pattern like other services in the codebase.
"""
from typing import Set
from fastapi import WebSocket
import logging
import json

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Singleton WebSocket manager"""
    _instance = None
    _connections: Set[WebSocket] = set()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._connections = set()
        return cls._instance
    
    async def connect(self, websocket: WebSocket):
        """Add a new WebSocket connection"""
        await websocket.accept()
        self._connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self._connections)}")
    
    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        self._connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self._connections)}")
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self._connections:
            return
        
        message_json = json.dumps(message)
        disconnected = set()
        
        for connection in self._connections:
            try:
                await connection.send_text(message_json)
            except Exception as e:
                logger.error(f"Error sending WebSocket message: {e}")
                disconnected.add(connection)
        
        # Remove disconnected clients
        for connection in disconnected:
            self._connections.discard(connection)
    
    async def send_to_connection(self, websocket: WebSocket, message: dict):
        """Send message to specific connection"""
        try:
            message_json = json.dumps(message)
            await websocket.send_text(message_json)
        except Exception as e:
            logger.error(f"Error sending WebSocket message: {e}")
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self._connections)


# Global instance
websocket_manager = WebSocketManager()


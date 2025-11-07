"""
WebSocket Route

Handles WebSocket connections for real-time updates.
"""
from fastapi import WebSocket, WebSocketDisconnect
import logging
import json

from api.services.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await websocket_manager.connect(websocket)
    
    try:
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
                
                # Handle ping/pong
                if message.get("type") == "ping":
                    await websocket_manager.send_to_connection(
                        websocket,
                        {"type": "pong"}
                    )
                
                # Handle test subscription
                elif message.get("type") == "subscribe_test":
                    test_id = message.get("test_id")
                    logger.info(f"Client subscribed to test: {test_id}")
                    # You can implement subscription logic here if needed
                    await websocket_manager.send_to_connection(
                        websocket,
                        {"type": "subscribed", "test_id": test_id}
                    )
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {data}")
                
    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket_manager.disconnect(websocket)


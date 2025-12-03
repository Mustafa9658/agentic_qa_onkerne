"""
WebSocket Routes

Real-time WebSocket endpoint for streaming browser automation updates.
"""
import logging
import json
import asyncio
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from qa_agent.workflow import create_qa_workflow
from qa_agent.state import create_initial_state
from qa_agent.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections"""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept and store WebSocket connection"""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"WebSocket client {client_id} connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, client_id: str):
        """Remove WebSocket connection"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"WebSocket client {client_id} disconnected. Total connections: {len(self.active_connections)}")

    async def send_message(self, client_id: str, message: dict):
        """Send message to specific client"""
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {client_id}: {e}")
                self.disconnect(client_id)


manager = ConnectionManager()


async def stream_workflow_updates(websocket: WebSocket, client_id: str, task: str, start_url: Optional[str], max_steps: int):
    """
    Stream workflow updates in real-time

    Sends updates for:
    - Workflow state changes
    - Browser actions
    - Verification results
    - Screenshot captures
    - Final report
    """
    try:
        # Send initial status
        await manager.send_message(client_id, {
            "type": "status",
            "status": "initializing",
            "message": "Starting QA automation workflow..."
        })

        # Create initial state
        initial_state = create_initial_state(
            task=task,
            start_url=start_url,
            max_steps=max_steps
        )

        # Send workflow started event
        await manager.send_message(client_id, {
            "type": "workflow_started",
            "task": task,
            "start_url": start_url,
            "max_steps": max_steps
        })

        # Get workflow instance
        workflow = create_qa_workflow()

        # Stream workflow execution
        step_count = 0
        async for event in workflow.astream(initial_state, config={"recursion_limit": 200}):
            step_count += 1

            # Extract event data
            node_name = list(event.keys())[0] if event else "unknown"
            node_data = event.get(node_name, {})

            # Send node execution update
            await manager.send_message(client_id, {
                "type": "node_update",
                "step": step_count,
                "node": node_name,
                "data": {
                    "step_count": node_data.get("step_count", 0),
                    "completed": node_data.get("completed", False),
                    "current_state": node_data.get("current_state", ""),
                    "verification_status": node_data.get("verification_status"),
                }
            })

            # If INIT node completed, send browser URL for API mode
            if node_name == "init":
                browser_session_id = node_data.get("browser_session_id")
                if browser_session_id:
                    try:
                        from qa_agent.utils.session_registry import get_session
                        from qa_agent.utils.settings_manager import get_settings_manager
                        
                        session = get_session(browser_session_id)
                        if session:
                            settings_manager = get_settings_manager()
                            browser_config = settings_manager.get_browser_config_raw()
                            connection_type = browser_config.get("connection_type", "localhost")
                            
                            browser_url = None
                            if connection_type == "api":
                                browser_url = getattr(session, '_browser_live_view_url', None)
                                if browser_url:
                                    logger.info(f"Sending browser URL to frontend: {browser_url[:50]}...")
                                    await manager.send_message(client_id, {
                                        "type": "browser_url",
                                        "browser_url": browser_url,
                                        "connection_type": connection_type,
                                        "session_id": browser_session_id[:16] + "..."
                                    })
                                else:
                                    logger.warning("No browser_live_view_url available in API mode")
                            elif connection_type == "localhost":
                                # For localhost, send localhost URL
                                await manager.send_message(client_id, {
                                    "type": "browser_url",
                                    "browser_url": "http://localhost:8080",
                                    "connection_type": connection_type
                                })
                    except Exception as e:
                        logger.warning(f"Could not send browser URL: {e}", exc_info=True)

            # Send browser action if available
            if "action" in node_data and node_data["action"]:
                await manager.send_message(client_id, {
                    "type": "browser_action",
                    "step": step_count,
                    "action": node_data["action"],
                    "result": node_data.get("action_result")
                })

            # Send verification result
            if "verification_status" in node_data:
                await manager.send_message(client_id, {
                    "type": "verification",
                    "step": step_count,
                    "status": node_data["verification_status"],
                    "details": node_data.get("verification_details", "")
                })

            # Send report if workflow completed
            if node_data.get("completed"):
                await manager.send_message(client_id, {
                    "type": "workflow_completed",
                    "report": node_data.get("report"),
                    "step_count": node_data.get("step_count", 0),
                    "verification_status": node_data.get("verification_status")
                })
                break

            # Small delay to prevent overwhelming the client
            await asyncio.sleep(0.1)

        # Send final status
        await manager.send_message(client_id, {
            "type": "status",
            "status": "completed",
            "message": "Workflow execution completed"
        })

    except Exception as e:
        logger.error(f"Error streaming workflow for client {client_id}: {e}")
        await manager.send_message(client_id, {
            "type": "error",
            "error": str(e),
            "message": "An error occurred during workflow execution"
        })


@router.websocket("/ws/automation")
async def websocket_automation_endpoint(
    websocket: WebSocket,
    client_id: str = Query(..., description="Unique client identifier"),
    task: str = Query(..., description="Task description"),
    start_url: Optional[str] = Query(None, description="Starting URL"),
    max_steps: int = Query(50, description="Maximum steps")
):
    """
    WebSocket endpoint for real-time browser automation streaming

    Usage:
        ws://localhost:8000/api/v1/ws/automation?client_id=123&task=test&start_url=https://example.com

    Events sent to client:
        - status: General status updates
        - workflow_started: Workflow initialization
        - node_update: Node execution updates
        - browser_action: Browser actions performed
        - verification: Verification results
        - workflow_completed: Final report
        - error: Error messages
    """
    await manager.connect(websocket, client_id)

    try:
        # Start streaming workflow updates
        await stream_workflow_updates(websocket, client_id, task, start_url, max_steps)

        # Keep connection alive and listen for client messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)

                # Handle client messages
                if message.get("type") == "ping":
                    await manager.send_message(client_id, {"type": "pong"})
                elif message.get("type") == "stop":
                    logger.info(f"Client {client_id} requested stop")
                    await manager.send_message(client_id, {
                        "type": "status",
                        "status": "stopped",
                        "message": "Workflow stopped by user"
                    })
                    break

            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        manager.disconnect(client_id)


@router.websocket("/ws")
async def simple_websocket_endpoint(websocket: WebSocket):
    """
    Simple WebSocket endpoint for general real-time updates.
    
    This endpoint accepts connections without requiring query parameters.
    Used by the frontend for general notifications and test updates.
    
    Usage:
        ws://localhost:8000/api/v1/ws
    """
    import uuid
    client_id = str(uuid.uuid4())[:8]
    
    await manager.connect(websocket, client_id)
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connected",
            "client_id": client_id
        })
        
        # Keep connection alive and listen for client messages
        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle ping/pong for keepalive
                if message.get("type") == "ping":
                    await manager.send_message(client_id, {"type": "pong"})
                
                # Handle subscribe to test
                elif message.get("type") == "subscribe_test":
                    test_id = message.get("test_id")
                    await manager.send_message(client_id, {
                        "type": "subscribed",
                        "test_id": test_id,
                        "message": f"Subscribed to test {test_id}"
                    })
                
                # Handle disconnect request
                elif message.get("type") == "disconnect":
                    break
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in WebSocket for client {client_id}: {e}")
                await manager.send_message(client_id, {
                    "type": "error",
                    "message": str(e)
                })
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket client {client_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        manager.disconnect(client_id)


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket server status"""
    return {
        "active_connections": len(manager.active_connections),
        "connected_clients": list(manager.active_connections.keys())
    }

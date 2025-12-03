"""
Browser Stream Routes

WebSocket endpoint for proxying live browser view from Docker container.
"""
import logging
import asyncio
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter()


class BrowserStreamManager:
    """Manages browser stream connections"""

    def __init__(self):
        self.active_streams: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept WebSocket connection"""
        await websocket.accept()
        self.active_streams[client_id] = websocket
        logger.info(f"Browser stream client {client_id} connected. Total: {len(self.active_streams)}")

    def disconnect(self, client_id: str):
        """Remove WebSocket connection"""
        if client_id in self.active_streams:
            del self.active_streams[client_id]
            logger.info(f"Browser stream client {client_id} disconnected. Total: {len(self.active_streams)}")


stream_manager = BrowserStreamManager()


@router.websocket("/ws/browser-stream")
async def browser_stream_websocket(
    websocket: WebSocket,
    client_id: str = Query(..., description="Unique client identifier"),
    browser_url: str = Query("http://localhost:8080", description="Browser view URL")
):
    """
    WebSocket endpoint for streaming live browser view

    This endpoint proxies the browser view from the Docker container (localhost:8080)
    and streams it to the frontend via WebSocket.

    Usage:
        ws://localhost:8000/api/v1/ws/browser-stream?client_id=123&browser_url=http://localhost:8080

    The frontend should use this to display the live browser automation view.
    """
    await stream_manager.connect(websocket, client_id)

    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "message": "Browser stream connected",
            "browser_url": browser_url
        })

        # Keep connection alive and listen for client messages
        while True:
            try:
                # Receive messages from client
                data = await websocket.receive_json()

                # Handle ping/pong for keepalive
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                # Handle browser URL update request
                elif data.get("type") == "update_url":
                    new_url = data.get("url")
                    await websocket.send_json({
                        "type": "url_updated",
                        "url": new_url
                    })

                # Handle disconnect request
                elif data.get("type") == "disconnect":
                    break

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error in browser stream for client {client_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })

    except WebSocketDisconnect:
        logger.info(f"Browser stream client {client_id} disconnected normally")
    except Exception as e:
        logger.error(f"Browser stream error for client {client_id}: {e}")
    finally:
        stream_manager.disconnect(client_id)


@router.post("/browser/init-persistent")
async def init_persistent_browser():
    """
    Initialize a persistent browser session for the frontend browser view.
    
    This endpoint creates a browser session that stays alive for the browser view iframe.
    The session is managed by the session registry and can be reused across test executions.
    
    Returns:
        Session information including session_id and browser_url
    """
    logger.info("=" * 80)
    logger.info("=== INIT-PERSISTENT ENDPOINT CALLED ===")
    logger.info("=" * 80)
    try:
        from qa_agent.utils.browser_manager import create_browser_session
        from qa_agent.utils.settings_manager import get_settings_manager
        
        logger.info("=== Starting persistent browser session initialization ===")
        
        # Get browser configuration to determine connection type
        settings_manager = get_settings_manager()
        browser_config = settings_manager.get_browser_config_raw()
        connection_type = browser_config.get("connection_type", "localhost")
        
        logger.info(f"Connection type: {connection_type}")
        logger.info(f"Browser config keys: {list(browser_config.keys())}")
        logger.info(f"API key present: {bool(browser_config.get('api_key'))}")
        logger.info(f"API endpoint: {browser_config.get('api_endpoint', 'not set')}")
        if browser_config.get('api_key'):
            masked_key = browser_config['api_key'][:4] + "..." + browser_config['api_key'][-4:] if len(browser_config['api_key']) > 8 else "***"
            logger.info(f"API key (masked): {masked_key}")
        
        # Create a persistent browser session (no start_url - just initialize)
        # Returns: (session_id, session, browser_live_view_url)
        logger.info("Calling create_browser_session()...")
        try:
            result = await create_browser_session(start_url=None)
            logger.info(f"create_browser_session() returned, result type: {type(result)}, length: {len(result) if hasattr(result, '__len__') else 'N/A'}")
        except Exception as create_error:
            logger.error(f"create_browser_session() raised exception: {create_error}", exc_info=True)
            raise  # Re-raise to be caught by outer try/except
        
        # Handle both old format (2 values) and new format (3 values)
        if isinstance(result, tuple) and len(result) == 3:
            session_id, session, browser_live_view_url = result
            logger.info(f"Got 3-value return: session_id={session_id[:16]}..., browser_live_view_url={browser_live_view_url}")
        elif isinstance(result, tuple) and len(result) == 2:
            session_id, session = result
            browser_live_view_url = None
            logger.info(f"Got 2-value return: session_id={session_id[:16]}..., browser_live_view_url=None")
        else:
            logger.error(f"Unexpected return format from create_browser_session: {result}")
            raise ValueError(f"Unexpected return format from create_browser_session: {type(result)}")
        
        logger.info(f"Persistent browser session initialized: {session_id[:16]}...")
        
        # Mark this session as persistent (for API mode only)
        # This allows test execution to reuse the same browser instance, preserving cookies/login state
        if connection_type == "api":
            from qa_agent.utils.session_registry import set_persistent_session
            set_persistent_session(session_id)
            logger.info(f"Marked session {session_id[:16]}... as persistent (will be reused for test execution)")
        
        # Determine browser URL based on connection type
        if connection_type == "api":
            # For cloud API, use the browser_live_view_url from OnKernel API response
            if browser_live_view_url:
                browser_url = browser_live_view_url
                logger.info(f"Using OnKernel cloud browser live view URL: {browser_url}")
            else:
                # Fallback: try to get from session attribute
                browser_url = getattr(session, '_browser_live_view_url', None)
                if browser_url:
                    logger.info(f"Using browser live view URL from session: {browser_url}")
                else:
                    logger.warning("No browser_live_view_url available - browser view may not work")
                    browser_url = None  # Don't provide invalid URL
        else:
            browser_url = "http://localhost:8080"
            logger.info(f"Using localhost browser URL: {browser_url}")
        
        return {
            "success": True,
            "session_id": session_id,
            "browser_url": browser_url,
            "connection_type": connection_type,
            "message": "Persistent browser session initialized"
        }
    except Exception as e:
        logger.error(f"=== ERROR initializing persistent browser session ===", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        logger.error(f"Error message: {str(e)}")
        logger.error(f"Full traceback:", exc_info=True)
        
        # Get connection type for error response
        try:
            from qa_agent.utils.settings_manager import get_settings_manager
            settings_manager = get_settings_manager()
            browser_config = settings_manager.get_browser_config_raw()
            connection_type = browser_config.get("connection_type", "localhost")
        except:
            connection_type = "unknown"
        
        # Return error with details - don't return success=false with localhost URL
        # This will help frontend understand the issue
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
            "connection_type": connection_type,
            "browser_url": None,  # Don't provide a URL if initialization failed
            "message": f"Browser session initialization failed: {str(e)}"
        }


@router.get("/browser/persistent-url")
async def get_persistent_browser_url():
    """
    Get the browser live view URL from the persistent session (if available).
    
    This endpoint is used by the frontend to get the correct browser URL for test execution.
    In API mode, it returns the cloud browser URL from the persistent session.
    In localhost mode, it returns the localhost URL.
    
    Returns:
        Browser URL for the persistent session, or localhost fallback
    """
    try:
        from qa_agent.utils.session_registry import get_persistent_session, get_persistent_session_id
        from qa_agent.utils.settings_manager import get_settings_manager
        
        settings_manager = get_settings_manager()
        browser_config = settings_manager.get_browser_config_raw()
        connection_type = browser_config.get("connection_type", "localhost")
        
        logger.info(f"Getting persistent browser URL for connection type: {connection_type}")
        
        if connection_type == "api":
            persistent_session = get_persistent_session()
            persistent_session_id = get_persistent_session_id()
            
            if persistent_session and persistent_session_id:
                browser_live_view_url = getattr(persistent_session, '_browser_live_view_url', None)
                if browser_live_view_url:
                    logger.info(f"Found persistent session browser URL: {browser_live_view_url[:50]}...")
                    return {
                        "success": True,
                        "browser_url": browser_live_view_url,
                        "connection_type": connection_type,
                        "session_id": persistent_session_id[:16] + "..."
                    }
                else:
                    logger.warning(f"Persistent session {persistent_session_id[:16]}... exists but no browser_live_view_url")
            
            # In API mode, if no persistent session, return None (don't fallback to localhost)
            logger.warning("No persistent session available in API mode - browser session will be created by workflow")
            return {
                "success": False,
                "browser_url": None,  # Don't provide localhost fallback in API mode
                "connection_type": connection_type,
                "message": "No persistent session available. Browser session will be created when workflow starts."
            }
        
        # Only fallback to localhost for localhost mode
        if connection_type == "localhost":
            browser_url = "http://localhost:8080"
            logger.info(f"Using localhost browser URL: {browser_url}")
            return {
                "success": True,
                "browser_url": browser_url,
                "connection_type": connection_type
            }
        
        # Should not reach here, but just in case
        logger.error(f"Unknown connection type: {connection_type}")
        return {
            "success": False,
            "browser_url": None,
            "connection_type": connection_type,
            "error": f"Unknown connection type: {connection_type}"
        }
    except Exception as e:
        logger.error(f"Error getting persistent browser URL: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "browser_url": "http://localhost:8080",  # Safe fallback
            "connection_type": "unknown"
        }


@router.post("/browser/test-api-connection")
async def test_onkernel_api_connection():
    """
    Test OnKernel API connection - useful for debugging
    
    Returns:
        Test results including API response
    """
    try:
        from qa_agent.utils.settings_manager import get_settings_manager
        from qa_agent.browser.onkernel_api import OnKernelAPIClient, OnKernelAPIError, OnKernelAPIAuthError
        
        settings_manager = get_settings_manager()
        browser_config = settings_manager.get_browser_config_raw()
        connection_type = browser_config.get("connection_type", "localhost")
        
        if connection_type != "api":
            return {
                "success": False,
                "error": "Connection type is not 'api'. Current type: " + connection_type,
                "connection_type": connection_type
            }
        
        api_key = browser_config.get("api_key")
        api_endpoint = browser_config.get("api_endpoint", "https://api.onkernel.com")
        
        if not api_key:
            return {
                "success": False,
                "error": "API key is not configured",
                "connection_type": connection_type
            }
        
        try:
            client = OnKernelAPIClient(api_key=api_key, api_endpoint=api_endpoint)
            session_data = await client.create_browser_session(headless=False)
            
            return {
                "success": True,
                "connection_type": connection_type,
                "api_endpoint": api_endpoint,
                "session_data": {
                    "cdp_ws_url": session_data.get("cdp_ws_url", "Not found"),
                    "browser_live_view_url": session_data.get("browser_live_view_url", "Not found"),
                    "session_id": session_data.get("session_id", "Not found"),
                    "raw_response_keys": list(session_data.get("raw_response", {}).keys()) if session_data.get("raw_response") else []
                },
                "message": "API connection successful"
            }
        except OnKernelAPIAuthError as e:
            return {
                "success": False,
                "error": f"Authentication failed: {str(e)}",
                "connection_type": connection_type,
                "api_endpoint": api_endpoint
            }
        except OnKernelAPIError as e:
            return {
                "success": False,
                "error": f"API error: {str(e)}",
                "connection_type": connection_type,
                "api_endpoint": api_endpoint
            }
    except Exception as e:
        logger.error(f"Error testing API connection: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.get("/browser/status")
async def browser_status():
    """Get browser stream status"""
    try:
        # Check if browser container is accessible
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get("http://localhost:8080")
                browser_accessible = response.status_code == 200
            except:
                browser_accessible = False

        return {
            "browser_accessible": browser_accessible,
            "browser_url": "http://localhost:8080",
            "cdp_url": "http://localhost:9222",
            "active_streams": len(stream_manager.active_streams),
            "connected_clients": list(stream_manager.active_streams.keys())
        }
    except Exception as e:
        return {
            "error": str(e),
            "browser_accessible": False
        }


@router.get("/browser/health")
async def browser_health():
    """Check browser container health"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Check browser view port
            try:
                browser_response = await client.get("http://localhost:8080")
                browser_status = "healthy" if browser_response.status_code == 200 else "unhealthy"
            except Exception as e:
                browser_status = f"unreachable: {e}"

            # Check CDP port
            try:
                cdp_response = await client.get("http://localhost:9222/json/version")
                cdp_data = cdp_response.json() if cdp_response.status_code == 200 else None
                cdp_status = "healthy" if cdp_response.status_code == 200 else "unhealthy"
            except Exception as e:
                cdp_data = None
                cdp_status = f"unreachable: {e}"

            return {
                "browser_view": {
                    "url": "http://localhost:8080",
                    "status": browser_status
                },
                "cdp": {
                    "url": "http://localhost:9222",
                    "status": cdp_status,
                    "data": cdp_data
                }
            }
    except Exception as e:
        return {
            "error": str(e)
        }


@router.post("/browser/viewport")
async def set_browser_viewport(width: int, height: int):
    """
    Dynamically resize browser viewport using CDP
    
    Args:
        width: Viewport width in pixels
        height: Viewport height in pixels
    
    Returns:
        Success status
    """
    try:
        from qa_agent.utils.session_registry import _SESSION_REGISTRY
        from qa_agent.browser.session import BrowserSession
        
        # Try to get active browser session from registry
        browser_session: BrowserSession | None = None
        
        # Get the first active browser session
        for session_id, session in _SESSION_REGISTRY.items():
            if isinstance(session, BrowserSession) and session.agent_focus:
                browser_session = session
                break
        
        if browser_session and browser_session.agent_focus:
            # Use existing session to set viewport
            try:
                await browser_session._cdp_set_viewport(width, height)
                logger.info(f"Viewport resized to {width}x{height} via existing session")
                return {
                    "success": True,
                    "message": f"Viewport resized to {width}x{height}",
                    "method": "existing_session"
                }
            except Exception as e:
                logger.warning(f"Failed to resize via session, trying direct CDP: {e}")
        
        # Fallback: Use direct CDP connection
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Get list of targets (tabs/pages)
            targets_response = await client.get("http://localhost:9222/json")
            targets = targets_response.json()
            
            if not targets:
                return {"error": "No browser targets found", "success": False}
            
            # Use the first page target
            target = next((t for t in targets if t.get("type") == "page"), targets[0])
            target_id = target.get("id")
            
            if not target_id:
                return {"error": "No valid target ID found", "success": False}
            
            # Get WebSocket debugger URL for direct CDP connection
            ws_url = target.get("webSocketDebuggerUrl")
            
            if ws_url:
                # Use websockets library to send CDP command
                try:
                    import websockets
                    async with websockets.connect(ws_url.replace("ws://", "ws://").replace("http://", "ws://")) as ws:
                        # Create session
                        session_msg = {
                            "id": 1,
                            "method": "Target.attachToTarget",
                            "params": {"targetId": target_id, "flatten": True}
                        }
                        await ws.send(str(session_msg).replace("'", '"'))
                        session_response = await ws.recv()
                        
                        # Extract session ID from response
                        import json
                        session_data = json.loads(session_response)
                        cdp_session_id = session_data.get("result", {}).get("sessionId")
                        
                        if cdp_session_id:
                            # Send viewport resize command
                            viewport_msg = {
                                "id": 2,
                                "method": "Emulation.setDeviceMetricsOverride",
                                "params": {
                                    "width": width,
                                    "height": height,
                                    "deviceScaleFactor": 1.0,
                                    "mobile": False
                                },
                                "sessionId": cdp_session_id
                            }
                            await ws.send(json.dumps(viewport_msg))
                            response = await ws.recv()
                            
                            logger.info(f"Viewport resized to {width}x{height} via direct CDP")
                            return {
                                "success": True,
                                "message": f"Viewport resized to {width}x{height}",
                                "method": "direct_cdp"
                            }
                except ImportError:
                    logger.warning("websockets library not available, skipping direct CDP")
                except Exception as e:
                    logger.error(f"Error in direct CDP connection: {e}")
            
            # If all else fails, return success (iframe will resize, browser viewport may not)
            logger.info(f"Viewport resize requested: {width}x{height} (iframe will resize)")
            return {
                "success": True,
                "message": f"Viewport resize requested: {width}x{height}",
                "method": "iframe_only",
                "note": "Browser viewport may remain fixed; iframe will resize"
            }
            
    except Exception as e:
        logger.error(f"Error setting browser viewport: {e}")
        return {
            "error": str(e),
            "success": False
        }

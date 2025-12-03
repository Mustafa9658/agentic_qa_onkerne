"""
OnKernel API Client

Client for connecting to OnKernel cloud browser service via API.
Creates browser sessions and returns CDP WebSocket URLs for connection.
"""
import logging
from typing import Optional, Dict, Any
import httpx
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


class OnKernelAPIError(Exception):
    """Exception raised when OnKernel API operations fail."""
    pass


class OnKernelAPIAuthError(OnKernelAPIError):
    """Exception raised when OnKernel API authentication fails."""
    pass


class OnKernelAPIClient:
    """
    Client for interacting with OnKernel cloud browser API.
    
    Creates browser sessions and manages connections to OnKernel's cloud browser service.
    """
    
    def __init__(self, api_key: str, api_endpoint: str = "https://api.onkernel.com"):
        """
        Initialize OnKernel API client
        
        Args:
            api_key: OnKernel API key for authentication
            api_endpoint: OnKernel API endpoint URL (default: https://api.onkernel.com)
        """
        if not api_key or not api_key.strip():
            raise ValueError("API key is required")
        if not api_endpoint or not api_endpoint.strip():
            raise ValueError("API endpoint is required")
        
        self.api_key = api_key.strip()
        self.api_endpoint = api_endpoint.rstrip('/')
        
        # Try X-API-Key header first (common for many APIs), fallback to Bearer token
        # OnKernel might use either format - we'll try X-API-Key first
        self._headers = {
            "X-API-Key": self.api_key,  # Try this format first (common for cloud browser APIs)
            "Content-Type": "application/json",
        }
        # Also prepare Bearer token format as fallback
        self._headers_bearer = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        logger.info(f"OnKernelAPIClient initialized with endpoint: {self.api_endpoint}")
    
    async def create_browser_session(self, **kwargs) -> Dict[str, Any]:
        """
        Create a new browser session via OnKernel API
        
        Args:
            **kwargs: Additional parameters for browser session creation
                - headless: bool (optional)
                - timeout: int (optional)
                - Other OnKernel API parameters
        
        Returns:
            Dict containing:
                - cdp_ws_url: CDP WebSocket URL for connecting to the browser
                - session_id: Session identifier
                - Other session metadata
        
        Raises:
            OnKernelAPIAuthError: If authentication fails
            OnKernelAPIError: If API request fails
        """
        # Prepare request payload
        payload: Dict[str, Any] = {}
        if "headless" in kwargs:
            payload["headless"] = kwargs["headless"]
        if "timeout" in kwargs:
            payload["timeout"] = kwargs["timeout"]
        
        # OnKernel API endpoint for creating browser sessions
        # Try multiple possible endpoint paths
        # Common patterns: /browsers, /api/v1/browsers, /browsers/create
        possible_endpoints = [
            "/browsers",
            "/api/v1/browsers",
            "/browsers/create",
            "/api/browsers",
        ]
        
        # Try X-API-Key header first, then Bearer token if that fails
        headers_to_try = [self._headers, self._headers_bearer]
        
        last_error = None
        
        logger.info(f"Creating OnKernel browser session via API: {self.api_endpoint}")
        logger.info(f"Request payload: {payload if payload else 'None'}")
        
        for endpoint_path in possible_endpoints:
            create_url = urljoin(self.api_endpoint, endpoint_path)
            
            for headers in headers_to_try:
                try:
                    logger.info(f"Trying endpoint: {create_url} with headers: {list(headers.keys())}")
                    
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            create_url,
                            headers=headers,
                            json=payload if payload else None,
                        )
                        
                        # Log full response for debugging
                        logger.info(f"API Response Status: {response.status_code}")
                        logger.info(f"API Response Headers: {dict(response.headers)}")
                        response_text = response.text
                        logger.info(f"API Response Body (first 2000 chars): {response_text[:2000]}")
                        
                        if response.status_code == 401 or response.status_code == 403:
                            error_body = response_text[:1000] if response_text else "Unknown error"
                            logger.warning(f"Authentication failed with {endpoint_path} and {list(headers.keys())}. Response: {error_body}")
                            last_error = OnKernelAPIAuthError(
                                f"Authentication failed: {response.status_code}. "
                                f"Response: {error_body}. "
                                "Please check your OnKernel API key."
                            )
                            continue  # Try next auth method or endpoint
                        
                        if response.status_code != 200 and response.status_code != 201:
                            error_text = response_text[:1000] if response_text else "Unknown error"
                            logger.warning(f"Request failed with {endpoint_path}. Status: {response.status_code}, Error: {error_text}")
                            last_error = OnKernelAPIError(
                                f"Failed to create browser session: {response.status_code}. "
                                f"Error: {error_text}"
                            )
                            continue  # Try next endpoint
                        
                        # Success! Parse response
                        try:
                            response_data = response.json()
                            logger.info(f"Success! Parsed JSON Response: {response_data}")
                        except Exception as e:
                            logger.error(f"Failed to parse JSON response: {e}. Raw: {response_text[:500]}")
                            last_error = OnKernelAPIError(f"Invalid JSON response from API: {str(e)}. Response: {response_text[:500]}")
                            continue
                        
                        # Extract CDP WebSocket URL from response
                        cdp_ws_url = (
                            response_data.get("cdp_ws_url") or 
                            response_data.get("cdpUrl") or 
                            response_data.get("cdp_url") or
                            response_data.get("ws_url") or
                            response_data.get("websocket_url") or
                            response_data.get("websocketUrl") or
                            response_data.get("cdp_endpoint") or
                            response_data.get("endpoint") or
                            response_data.get("ws_endpoint")
                        )
                        
                        # Extract browser live view URL (for visual browser view)
                        browser_live_view_url = (
                            response_data.get("browser_live_view_url") or
                            response_data.get("live_view_url") or
                            response_data.get("view_url") or
                            response_data.get("browser_view_url") or
                            response_data.get("web_url")
                        )
                        
                        if not cdp_ws_url:
                            # Try alternative response formats (nested objects)
                            if "browser" in response_data:
                                browser_data = response_data["browser"]
                                cdp_ws_url = (
                                    browser_data.get("cdp_ws_url") or 
                                    browser_data.get("cdpUrl") or
                                    browser_data.get("cdp_url") or
                                    browser_data.get("ws_url")
                                )
                                if not browser_live_view_url:
                                    browser_live_view_url = (
                                        browser_data.get("browser_live_view_url") or
                                        browser_data.get("live_view_url") or
                                        browser_data.get("view_url")
                                    )
                            
                            if "data" in response_data:
                                data = response_data["data"]
                                cdp_ws_url = (
                                    data.get("cdp_ws_url") or 
                                    data.get("cdpUrl") or
                                    data.get("cdp_url") or
                                    data.get("ws_url")
                                )
                                if not browser_live_view_url:
                                    browser_live_view_url = (
                                        data.get("browser_live_view_url") or
                                        data.get("live_view_url") or
                                        data.get("view_url")
                                    )
                        
                        if cdp_ws_url:
                            session_id = response_data.get("session_id") or response_data.get("id") or response_data.get("browser_id")
                            logger.info(f"Successfully created OnKernel browser session: {session_id} via {endpoint_path}")
                            logger.info(f"CDP WebSocket URL: {cdp_ws_url[:80]}...")
                            if browser_live_view_url:
                                logger.info(f"Browser live view URL: {browser_live_view_url}")
                            else:
                                logger.warning("No browser_live_view_url found in response - browser view may not be available")
                            
                            return {
                                "cdp_ws_url": cdp_ws_url,
                                "browser_live_view_url": browser_live_view_url,  # Add live view URL
                                "session_id": session_id,
                                "raw_response": response_data,
                            }
                        else:
                            logger.error(f"CDP URL not found in response. Available keys: {list(response_data.keys())}")
                            last_error = OnKernelAPIError(
                                "API response does not contain CDP WebSocket URL. "
                                f"Response structure: {response_data}. "
                                "Please check OnKernel API documentation for correct response format."
                            )
                            continue
                            
                except httpx.TimeoutException:
                    logger.warning(f"Timeout with {endpoint_path}")
                    last_error = OnKernelAPIError("Request to OnKernel API timed out")
                    continue
                except httpx.RequestError as e:
                    logger.warning(f"Request error with {endpoint_path}: {str(e)}")
                    last_error = OnKernelAPIError(f"Failed to connect to OnKernel API: {str(e)}")
                    continue
                except (OnKernelAPIAuthError, OnKernelAPIError) as e:
                    # Re-raise these immediately as they're already formatted
                    raise
                except Exception as e:
                    logger.warning(f"Unexpected error with {endpoint_path}: {str(e)}")
                    last_error = OnKernelAPIError(f"Unexpected error creating browser session: {str(e)}")
                    continue
        
        # If we get here, all attempts failed
        if last_error:
            raise last_error
        raise OnKernelAPIError("Failed to create browser session after trying all endpoint and authentication combinations")
    
    async def close_browser_session(self, session_id: str) -> None:
        """
        Close a browser session
        
        Args:
            session_id: Session identifier to close
            
        Raises:
            OnKernelAPIError: If closing session fails
        """
        if not session_id:
            return
        
        # OnKernel API endpoint for closing browser sessions
        close_url = urljoin(self.api_endpoint, f"/browsers/{session_id}")
        
        logger.info(f"Closing OnKernel browser session: {session_id}")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(close_url, headers=self._headers)
                
                if response.status_code == 404:
                    logger.warning(f"Browser session {session_id} not found (may already be closed)")
                    return
                
                if response.status_code not in [200, 204]:
                    error_text = response.text[:500] if response.text else "Unknown error"
                    logger.warning(
                        f"Failed to close browser session: {response.status_code}. "
                        f"Error: {error_text}"
                    )
                else:
                    logger.info(f"Successfully closed OnKernel browser session: {session_id}")
                    
        except httpx.TimeoutException:
            logger.warning(f"Timeout closing browser session {session_id}")
        except Exception as e:
            logger.warning(f"Error closing browser session {session_id}: {str(e)}")


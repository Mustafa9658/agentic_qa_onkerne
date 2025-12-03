"""
Browser Session Lifecycle Manager

Manages browser session creation and cleanup for kernel-image CDP connection.
Supports both localhost and OnKernel API connection modes.
"""
import logging
from typing import Optional
import httpx
from uuid_extensions import uuid7str

from qa_agent.browser.session import BrowserSession
from qa_agent.browser.profile import BrowserProfile
from qa_agent.config import settings
from qa_agent.utils.session_registry import register_session, unregister_session
from qa_agent.utils.settings_manager import get_settings_manager
from qa_agent.browser.onkernel_api import OnKernelAPIClient, OnKernelAPIError, OnKernelAPIAuthError

logger = logging.getLogger(__name__)


async def create_browser_session(start_url: Optional[str] = None) -> tuple[str, BrowserSession, Optional[str]]:
	"""
	Create and initialize browser session connected to kernel-image CDP or OnKernel API

	Supports two connection modes:
	- localhost: Connects to local OnKernel browser instance via CDP
	- api: Creates browser session via OnKernel cloud API

	Args:
		start_url: Optional initial URL to navigate to

	Returns:
		Tuple of (session_id, BrowserSession instance)
	"""
	# Get browser configuration from SettingsManager
	settings_manager = get_settings_manager()
	browser_config = settings_manager.get_browser_config_raw()
	connection_type = browser_config.get("connection_type", "localhost")
	
	logger.info(f"=== Creating browser session ===")
	logger.info(f"Connection type: {connection_type}")
	logger.info(f"Browser config keys: {list(browser_config.keys())}")
	logger.info(f"API key present: {bool(browser_config.get('api_key'))}")
	logger.info(f"API endpoint: {browser_config.get('api_endpoint', 'not set')}")

	# Generate unique session ID
	session_id = uuid7str()

	cdp_url: Optional[str] = None
	browser_live_view_url: Optional[str] = None  # Store live view URL for API mode
	
	if connection_type == "api":
		# Use OnKernel API to create browser session
		logger.info("Using OnKernel API to create browser session")
		
		api_key = browser_config.get("api_key")
		api_endpoint = browser_config.get("api_endpoint", "https://api.onkernel.com")
		
		if not api_key:
			raise ValueError(
				"OnKernel API key is required for API connection type. "
				"Please configure it in browser settings."
			)
		
		try:
			client = OnKernelAPIClient(api_key=api_key, api_endpoint=api_endpoint)
			session_data = await client.create_browser_session(headless=settings.headless)
			cdp_url = session_data["cdp_ws_url"]
			browser_live_view_url = session_data.get("browser_live_view_url")  # Get live view URL if available
			logger.info(f"Got CDP WebSocket URL from OnKernel API: {cdp_url[:50]}...")
			if browser_live_view_url:
				logger.info(f"Got browser live view URL: {browser_live_view_url}")
			else:
				logger.warning("No browser_live_view_url in API response - browser view may not be available")
		except OnKernelAPIAuthError as e:
			logger.error(f"OnKernel API authentication failed: {e}")
			raise ValueError(
				f"Failed to authenticate with OnKernel API: {str(e)}. "
				"Please check your API key in browser settings."
			)
		except OnKernelAPIError as e:
			logger.error(f"OnKernel API error: {e}")
			raise ValueError(f"Failed to create browser session via OnKernel API: {str(e)}")
		except Exception as e:
			logger.error(f"Unexpected error creating browser session via API: {e}", exc_info=True)
			raise ValueError(f"Unexpected error: {str(e)}")
	
	else:
		# Use localhost CDP connection (default)
		logger.info("Using localhost CDP connection")
		
		kernel_cdp_host = browser_config.get("kernel_cdp_host", settings.kernel_cdp_host)
		kernel_cdp_port = browser_config.get("kernel_cdp_port", settings.kernel_cdp_port)
		
		# Get WebSocket debugger URL from kernel-image HTTP endpoint
		http_url = f"http://{kernel_cdp_host}:{kernel_cdp_port}"
		logger.info(f"Querying CDP endpoint at: {http_url}")

		try:
			async with httpx.AsyncClient(timeout=10.0) as client:
				response = await client.get(f"{http_url}/json/version")
				response.raise_for_status()
				version_data = response.json()
				cdp_url = version_data["webSocketDebuggerUrl"]
				logger.info(f"Got WebSocket URL: {cdp_url}")
		except httpx.TimeoutException:
			raise ValueError(
				f"Timeout connecting to local OnKernel browser at {http_url}. "
				"Please ensure the browser is running."
			)
		except httpx.RequestError as e:
			raise ValueError(
				f"Failed to connect to local OnKernel browser at {http_url}: {str(e)}. "
				"Please ensure the browser is running and accessible."
			)
		except Exception as e:
			logger.error(f"Error querying CDP endpoint: {e}", exc_info=True)
			raise ValueError(f"Failed to get CDP URL: {str(e)}")
	
	if not cdp_url:
		raise ValueError("Failed to obtain CDP WebSocket URL")

	# Create browser profile configured for CDP connection (local or API)
	profile = BrowserProfile(
		cdp_url=cdp_url,  # Connect via CDP (from localhost or API)
		is_local=(connection_type == "localhost"),  # Local if localhost, remote if API
		headless=settings.headless,
		minimum_wait_page_load_time=0.5,
		wait_for_network_idle_page_load_time=1.0,
		wait_between_actions=0.5,
		auto_download_pdfs=True,
		highlight_elements=True,
		dom_highlight_elements=True,
		paint_order_filtering=True,
	)

	# Create browser session
	session = BrowserSession(
		id=session_id,
		browser_profile=profile,
	)

	# Start session (connects via CDP)
	logger.info(f"Starting browser session (connecting via CDP)...")
	try:
		await session.start()
		connection_source = "localhost" if connection_type == "localhost" else "OnKernel API"
		logger.info(f"Browser session {session_id} connected via {connection_source} successfully")
	except Exception as start_error:
		logger.error(f"Failed to start browser session: {start_error}", exc_info=True)
		raise ValueError(f"Failed to start browser session: {str(start_error)}") from start_error

	# Register session in registry for state serializability
	register_session(session_id, session)
	
	# Store browser live view URL in session metadata if available (for API mode)
	# We'll store it as a custom attribute on the session object
	if browser_live_view_url:
		# Store it in a way that can be retrieved later
		# Using a private attribute that won't interfere with BrowserSession
		setattr(session, '_browser_live_view_url', browser_live_view_url)
		logger.info(f"Stored browser live view URL in session: {browser_live_view_url}")

	# Navigate to start URL if provided
	if start_url:
		logger.info(f"Navigating to start URL: {start_url}")
		await session.navigate_to(start_url)
		logger.info(f"Successfully navigated to: {start_url}")

	return session_id, session, browser_live_view_url  # Return live view URL as third value


async def cleanup_browser_session(session_id: Optional[str]) -> None:
	"""
	Clean up browser session and clear persistent session marker if needed.
	
	Args:
		session_id: Session identifier to clean up
	"""
	if not session_id:
		return

	from qa_agent.utils.session_registry import get_session, is_persistent_session, clear_persistent_session

	session = get_session(session_id)
	if session:
		try:
			logger.info(f"Cleaning up browser session: {session_id}")
			
			# Clear persistent session marker if this is the persistent session
			if is_persistent_session(session_id):
				logger.info(f"Clearing persistent session marker for {session_id[:16]}...")
				clear_persistent_session()
			
			await session.stop()
			unregister_session(session_id)
			logger.info(f"Browser session {session_id} cleaned up successfully")
		except Exception as e:
			logger.error(f"Error cleaning up browser session {session_id}: {e}", exc_info=True)
	else:
		logger.warning(f"Browser session {session_id} not found in registry")

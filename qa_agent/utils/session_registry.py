"""
Browser Session Registry

Manages browser session instances to keep state serializable for LangGraph.
State stores session_id (string), this registry maps IDs to actual BrowserSession objects.

Also manages persistent browser sessions for API mode (similar to how localhost mode
reuses the same browser instance).
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Global session registry - maps session_id -> BrowserSession
_SESSION_REGISTRY: Dict[str, any] = {}

# Global persistent session ID (for Live Preview in API mode)
# This allows test execution to reuse the same browser instance, preserving cookies/login state
_PERSISTENT_SESSION_ID: Optional[str] = None


def register_session(session_id: str, session: any) -> None:
	"""
	Register a browser session instance

	Args:
		session_id: Unique session identifier
		session: BrowserSession instance
	"""
	_SESSION_REGISTRY[session_id] = session
	logger.info(f"Registered browser session: {session_id}")


def get_session(session_id: str) -> Optional[any]:
	"""
	Retrieve a browser session by ID

	Args:
		session_id: Session identifier

	Returns:
		BrowserSession instance or None if not found
	"""
	session = _SESSION_REGISTRY.get(session_id)
	if session is None:
		logger.warning(f"Browser session not found: {session_id}")
	return session


def unregister_session(session_id: str) -> None:
	"""
	Unregister and remove a browser session

	Args:
		session_id: Session identifier to remove
	"""
	if session_id in _SESSION_REGISTRY:
		del _SESSION_REGISTRY[session_id]
		logger.info(f"Unregistered browser session: {session_id}")
	else:
		logger.warning(f"Attempted to unregister non-existent session: {session_id}")


def list_sessions() -> list[str]:
	"""Get list of all registered session IDs"""
	return list(_SESSION_REGISTRY.keys())


def session_count() -> int:
	"""Get count of active sessions"""
	return len(_SESSION_REGISTRY)


def set_persistent_session(session_id: str) -> None:
	"""
	Mark a session as the persistent session (for Live Preview in API mode).
	
	This allows test execution to reuse the same browser instance, preserving
	cookies, login state, and other browser data - similar to how localhost mode
	reuses the same browser process.
	
	Args:
		session_id: Session identifier to mark as persistent
	"""
	global _PERSISTENT_SESSION_ID
	if session_id not in _SESSION_REGISTRY:
		logger.warning(f"Cannot set persistent session {session_id}: session not in registry")
		return
	_PERSISTENT_SESSION_ID = session_id
	logger.info(f"Set persistent session: {session_id[:16]}...")


def get_persistent_session_id() -> Optional[str]:
	"""
	Get the persistent session ID if available.
	
	Returns:
		Persistent session ID or None if not set
	"""
	return _PERSISTENT_SESSION_ID


def get_persistent_session() -> Optional[any]:
	"""
	Get the persistent browser session if available.
	
	This is used by init_node to reuse the browser session created during
	Live Preview, ensuring cookies and login state persist across test executions.
	
	Returns:
		BrowserSession instance or None if not available
	"""
	persistent_id = get_persistent_session_id()
	if not persistent_id:
		return None
	
	session = get_session(persistent_id)
	if session is None:
		logger.warning(f"Persistent session {persistent_id[:16]}... not found in registry, clearing marker")
		clear_persistent_session()
		return None
	
	return session


def clear_persistent_session() -> None:
	"""
	Clear the persistent session marker.
	
	This should be called when the persistent session is closed or invalidated.
	"""
	global _PERSISTENT_SESSION_ID
	_PERSISTENT_SESSION_ID = None
	logger.info("Cleared persistent session marker")


def is_persistent_session(session_id: str) -> bool:
	"""
	Check if a session ID is the persistent session.
	
	Args:
		session_id: Session identifier to check
		
	Returns:
		True if this is the persistent session, False otherwise
	"""
	return _PERSISTENT_SESSION_ID == session_id

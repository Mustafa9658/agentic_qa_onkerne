"""
In-Memory Settings Storage

Stores application settings in a dictionary.
"""
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Global settings dictionary
_SETTINGS: dict = {
    "api_url": "http://localhost:8000",
    "websocket_url": "ws://localhost:8000/ws",
    "browser_timeout": 30,
    "screenshot_interval": 5,
    "recording_enabled": True,
    "auto_retry_failed_tests": True,
    "max_retry_attempts": 3,
    "notification_enabled": True,
    "email_notifications": False,
    "webhook_url": None,
}


def get_settings() -> dict:
    """Get all settings"""
    return _SETTINGS.copy()  # Return copy to prevent external modification


def update_settings(**updates) -> dict:
    """Update settings"""
    _SETTINGS.update(updates)
    logger.info(f"Settings updated: {list(updates.keys())}")
    return _SETTINGS.copy()


def get_setting(key: str, default=None):
    """Get a specific setting"""
    return _SETTINGS.get(key, default)


def reset_settings():
    """Reset settings to defaults"""
    global _SETTINGS
    _SETTINGS = {
        "api_url": "http://localhost:8000",
        "websocket_url": "ws://localhost:8000/ws",
        "browser_timeout": 30,
        "screenshot_interval": 5,
        "recording_enabled": True,
        "auto_retry_failed_tests": True,
        "max_retry_attempts": 3,
        "notification_enabled": True,
        "email_notifications": False,
        "webhook_url": None,
    }
    logger.info("Settings reset to defaults")


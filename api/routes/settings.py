"""
Settings API Routes

Uses in-memory storage for settings.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import logging

from api.storage.settings_storage import (
    get_settings,
    update_settings,
    reset_settings,
)

logger = logging.getLogger(__name__)
router = APIRouter()


class SettingsRequest(BaseModel):
    """Request model for updating settings"""
    api_url: Optional[str] = None
    websocket_url: Optional[str] = None
    browser_timeout: Optional[int] = None
    screenshot_interval: Optional[int] = None
    recording_enabled: Optional[bool] = None
    auto_retry_failed_tests: Optional[bool] = None
    max_retry_attempts: Optional[int] = None
    notification_enabled: Optional[bool] = None
    email_notifications: Optional[bool] = None
    webhook_url: Optional[str] = None


@router.get("/settings")
async def get_settings_endpoint():
    """Get current settings"""
    return {"settings": get_settings()}


@router.put("/settings")
async def update_settings_endpoint(settings: SettingsRequest):
    """Update settings"""
    # Convert Pydantic model to dict, filtering None values
    updates = {k: v for k, v in settings.dict().items() if v is not None}
    updated_settings = update_settings(**updates)
    return {"settings": updated_settings}


@router.post("/settings/reset")
async def reset_settings_endpoint():
    """Reset settings to defaults"""
    reset_settings()
    return {"settings": get_settings(), "message": "Settings reset to defaults"}


"""
Settings Routes

API endpoints for managing runtime configuration settings.
"""
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from qa_agent.utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic Models
class LLMSettingsRequest(BaseModel):
    """Request model for updating LLM settings"""
    provider: Optional[str] = Field(None, description="LLM provider (openai, anthropic, gemini)")
    model: Optional[str] = Field(None, description="Model name")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Temperature (0.0-2.0)")
    
    @field_validator('provider')
    @classmethod
    def validate_provider(cls, v):
        if v is not None:
            v_lower = v.lower()
            valid_providers = ["openai", "anthropic", "gemini"]
            if v_lower not in valid_providers:
                raise ValueError(f"Provider must be one of {valid_providers}")
            return v_lower
        return v


class FallbackSettingsRequest(BaseModel):
    """Request model for updating Gemini fallback settings"""
    gemini_computer_use_model: Optional[str] = Field(None, description="Gemini model for fallback advisor")
    fallback_trigger_repetition: Optional[int] = Field(None, ge=0, description="Trigger after N repetitions")
    fallback_trigger_failures: Optional[int] = Field(None, ge=0, description="Trigger after N failures")
    fallback_trigger_same_page_steps: Optional[int] = Field(None, ge=0, description="Trigger after N same-page steps")


class LLMSettingsResponse(BaseModel):
    """Response model for LLM settings"""
    provider: str
    model: str
    temperature: float


class FallbackSettingsResponse(BaseModel):
    """Response model for fallback settings"""
    gemini_computer_use_model: str
    fallback_trigger_repetition: int
    fallback_trigger_failures: int
    fallback_trigger_same_page_steps: int


class SettingsResponse(BaseModel):
    """Response model for all settings"""
    llm_settings: LLMSettingsResponse
    fallback_settings: FallbackSettingsResponse


class AvailableModelsResponse(BaseModel):
    """Response model for available models"""
    provider: str
    models: List[str]


@router.get("/settings", response_model=SettingsResponse)
async def get_all_settings():
    """
    Get all runtime settings
    
    Returns:
        Current LLM and fallback settings
    """
    try:
        manager = get_settings_manager()
        all_settings = manager.get_all_settings()
        
        return SettingsResponse(
            llm_settings=LLMSettingsResponse(**all_settings["llm_settings"]),
            fallback_settings=FallbackSettingsResponse(**all_settings["fallback_settings"]),
        )
    except Exception as e:
        logger.error(f"Error getting settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class LLMSettingsFullResponse(BaseModel):
    """Full response model for LLM settings with all fields"""
    settings: Dict[str, Any]
    available_models: Dict[str, List[str]]


@router.get("/settings/llm")
async def get_llm_settings():
    """
    Get current LLM settings with all configuration and available models
    
    Returns:
        Current LLM configuration including provider, model, temperature, fallback settings, and available models
    """
    try:
        manager = get_settings_manager()
        llm_config = manager.get_llm_config()
        fallback_config = manager.get_fallback_config()
        
        # Combine all settings with proper field names
        all_settings = {
            "llm_provider": llm_config.get("provider", "openai"),
            "llm_model": llm_config.get("model", "gpt-4o-mini"),
            "llm_temperature": llm_config.get("temperature", 0.7),
            "enable_gemini_fallback": True,  # Always enabled, controlled by thresholds
            "gemini_computer_use_model": fallback_config.get("gemini_computer_use_model", "gemini-2.5-flash"),
            "fallback_trigger_repetition": fallback_config.get("fallback_trigger_repetition", 2),
            "fallback_trigger_failures": fallback_config.get("fallback_trigger_failures", 2),
            "fallback_trigger_same_page_steps": fallback_config.get("fallback_trigger_same_page_steps", 10),
        }
        
        # Get all available models
        available_models = {}
        for provider in ["openai", "anthropic", "gemini"]:
            try:
                available_models[provider] = manager.get_available_models(provider)
            except:
                available_models[provider] = []
        
        # Get available fallback models
        available_fallback_models = manager.get_available_fallback_models()
        
        return {
            "settings": all_settings,
            "available_models": available_models,
            "available_fallback_models": available_fallback_models
        }
    except Exception as e:
        logger.error(f"Error getting LLM settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/llm")
async def update_llm_settings(request: Dict[str, Any]):
    """
    Update LLM settings (accepts full settings object from frontend)
    
    Args:
        request: Full LLM settings object with all fields
        
    Returns:
        Updated LLM settings
    """
    try:
        manager = get_settings_manager()
        
        # Update LLM settings
        provider = request.get("llm_provider") or request.get("provider")
        model = request.get("llm_model") or request.get("model")
        temperature = request.get("llm_temperature") or request.get("temperature")
        
        if provider or model or temperature is not None:
            updated_llm = manager.update_llm_settings(
                provider=provider,
                model=model,
                temperature=temperature,
            )
        else:
            updated_llm = manager.get_llm_config()
        
        # Update fallback settings
        gemini_computer_use_model = request.get("gemini_computer_use_model")
        fallback_trigger_repetition = request.get("fallback_trigger_repetition")
        fallback_trigger_failures = request.get("fallback_trigger_failures")
        fallback_trigger_same_page_steps = request.get("fallback_trigger_same_page_steps")
        
        if any([gemini_computer_use_model is not None,
                fallback_trigger_repetition is not None, 
                fallback_trigger_failures is not None, 
                fallback_trigger_same_page_steps is not None]):
            manager.update_fallback_settings(
                gemini_computer_use_model=gemini_computer_use_model,
                fallback_trigger_repetition=fallback_trigger_repetition,
                fallback_trigger_failures=fallback_trigger_failures,
                fallback_trigger_same_page_steps=fallback_trigger_same_page_steps,
            )
        
        # Return updated settings in the format frontend expects
        fallback_config = manager.get_fallback_config()
        return {
            "llm_provider": updated_llm.get("provider", "openai"),
            "llm_model": updated_llm.get("model", "gpt-4o-mini"),
            "llm_temperature": updated_llm.get("temperature", 0.7),
            "enable_gemini_fallback": request.get("enable_gemini_fallback", True),
            "gemini_computer_use_model": fallback_config.get("gemini_computer_use_model", "gemini-2.5-flash"),
            "fallback_trigger_repetition": fallback_config.get("fallback_trigger_repetition", 2),
            "fallback_trigger_failures": fallback_config.get("fallback_trigger_failures", 2),
            "fallback_trigger_same_page_steps": fallback_config.get("fallback_trigger_same_page_steps", 10),
        }
    except ValueError as e:
        logger.warning(f"Invalid LLM settings update: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating LLM settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/settings/fallback", response_model=FallbackSettingsResponse)
async def update_fallback_settings(request: FallbackSettingsRequest):
    """
    Update Gemini fallback settings
    
    Args:
        request: Fallback settings to update
        
    Returns:
        Updated fallback settings
    """
    try:
        manager = get_settings_manager()
        updated = manager.update_fallback_settings(
            gemini_computer_use_model=request.gemini_computer_use_model,
            fallback_trigger_repetition=request.fallback_trigger_repetition,
            fallback_trigger_failures=request.fallback_trigger_failures,
            fallback_trigger_same_page_steps=request.fallback_trigger_same_page_steps,
        )
        return FallbackSettingsResponse(**updated)
    except ValueError as e:
        logger.warning(f"Invalid fallback settings update: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating fallback settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings/llm/models", response_model=AvailableModelsResponse)
async def get_available_models(provider: str = Query(..., description="LLM provider (openai, anthropic, gemini)")):
    """
    Get available models for a provider
    
    Args:
        provider: LLM provider name
        
    Returns:
        List of available models for the provider
    """
    try:
        manager = get_settings_manager()
        models = manager.get_available_models(provider)
        return AvailableModelsResponse(provider=provider.lower(), models=models)
    except ValueError as e:
        logger.warning(f"Invalid provider: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error getting available models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


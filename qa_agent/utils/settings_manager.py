"""
Runtime Settings Manager

Manages runtime configuration settings that can be updated via API.
Uses in-memory storage for session-based configuration.
"""
import logging
from typing import Dict, Any, Optional, List
from qa_agent.config import settings
from qa_agent.utils.singleton import singleton

logger = logging.getLogger(__name__)


# Available models per provider
AVAILABLE_MODELS = {
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1-mini",
        "gpt-4.1",
    ],
    "anthropic": [
        "claude-3-5-sonnet-20241022",  # Claude Sonnet 4.5
        "claude-3-5-haiku-20241022",   # Claude Haiku 4.5
    ],
    "gemini": [
        "gemini-2.5-flash",      # Latest Flash (recommended)
        "gemini-2.0-flash-exp",  # Experimental Flash
        "gemini-pro",            # Legacy Pro
    ],
}

# Available Gemini models for fallback advisor (multimodal/vision models)
AVAILABLE_FALLBACK_MODELS = [
    "gemini-2.5-flash",      # Latest Flash (recommended, fast, cost-effective)
    "gemini-2.0-flash-exp",  # Experimental Flash
    "gemini-1.5-pro",        # Pro model (better quality, slower)
    "gemini-1.5-flash",      # Legacy Flash (still available in some regions)
    "gemini-pro",            # Legacy Pro
]


@singleton
class SettingsManager:
    """
    Singleton class for managing runtime settings.
    
    Stores LLM configuration and Gemini fallback thresholds in memory.
    Settings persist for the current runtime session only.
    """
    
    def __init__(self):
        """Initialize settings manager with defaults from config.py"""
        # Validate and set default model
        default_provider = settings.llm_provider.lower()
        default_model = settings.llm_model
        
        # Ensure default model is in the available models list
        if default_provider in AVAILABLE_MODELS:
            if default_model not in AVAILABLE_MODELS[default_provider]:
                # Use first available model if default is not valid
                default_model = AVAILABLE_MODELS[default_provider][0]
                logger.warning(
                    f"Default model '{settings.llm_model}' not in available models for '{default_provider}'. "
                    f"Using '{default_model}' instead."
                )
        else:
            # Fallback to openai if provider is invalid
            default_provider = "openai"
            default_model = AVAILABLE_MODELS["openai"][0]
            logger.warning(
                f"Invalid provider '{settings.llm_provider}'. Using 'openai' with model '{default_model}'."
            )
        
        # LLM Configuration
        self._llm_settings: Dict[str, Any] = {
            "provider": default_provider,
            "model": default_model,
            "temperature": settings.llm_temperature,
        }
        
        # API keys (from config, not exposed via API)
        self._api_keys: Dict[str, Optional[str]] = {
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "gemini": settings.gemini_api_key,
        }
        
        # Gemini Fallback Settings
        self._fallback_settings: Dict[str, Any] = {
            "gemini_computer_use_model": settings.gemini_computer_use_model,
            "fallback_trigger_repetition": settings.fallback_trigger_repetition,
            "fallback_trigger_failures": settings.fallback_trigger_failures,
            "fallback_trigger_same_page_steps": settings.fallback_trigger_same_page_steps,
        }
        
        # Browser Settings (OnKernel connection)
        self._browser_settings: Dict[str, Any] = {
            "connection_type": "localhost",  # "localhost" or "api"
            "kernel_cdp_host": settings.kernel_cdp_host,
            "kernel_cdp_port": settings.kernel_cdp_port,
            "api_key": settings.kernel_api_key,  # OnKernel API key (optional, only for API mode)
            "api_endpoint": settings.kernel_api_endpoint,  # OnKernel API endpoint (default: https://api.onkernel.com)
        }
        
        logger.info("SettingsManager initialized with defaults from config")
    
    def get_llm_config(self) -> Dict[str, Any]:
        """
        Get current LLM configuration
        
        Returns:
            Dict with provider, model, and temperature
        """
        return self._llm_settings.copy()
    
    def get_fallback_config(self) -> Dict[str, Any]:
        """
        Get current Gemini fallback configuration
        
        Returns:
            Dict with fallback trigger thresholds
        """
        return self._fallback_settings.copy()
    
    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for a provider
        
        Args:
            provider: Provider name (openai, anthropic, gemini)
            
        Returns:
            API key or None if not set
        """
        return self._api_keys.get(provider.lower())
    
    def update_llm_settings(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Update LLM settings
        
        Args:
            provider: LLM provider (openai, anthropic, gemini)
            model: Model name
            temperature: Temperature value (0.0-2.0)
            
        Returns:
            Updated LLM settings dict
            
        Raises:
            ValueError: If provider/model combination is invalid
        """
        if provider is not None:
            provider_lower = provider.lower()
            if provider_lower not in AVAILABLE_MODELS:
                raise ValueError(f"Invalid provider: {provider}. Must be one of {list(AVAILABLE_MODELS.keys())}")
            self._llm_settings["provider"] = provider_lower
            
            # If model is not provided, use first available model for provider
            if model is None:
                model = AVAILABLE_MODELS[provider_lower][0]
        
        if model is not None:
            current_provider = self._llm_settings.get("provider", "openai")
            if model not in AVAILABLE_MODELS.get(current_provider, []):
                raise ValueError(
                    f"Invalid model '{model}' for provider '{current_provider}'. "
                    f"Available models: {AVAILABLE_MODELS.get(current_provider, [])}"
                )
            self._llm_settings["model"] = model
        
        if temperature is not None:
            if not 0.0 <= temperature <= 2.0:
                raise ValueError("Temperature must be between 0.0 and 2.0")
            self._llm_settings["temperature"] = float(temperature)
        
        logger.info(f"Updated LLM settings: {self._llm_settings}")
        return self.get_llm_config()
    
    def update_fallback_settings(
        self,
        gemini_computer_use_model: Optional[str] = None,
        fallback_trigger_repetition: Optional[int] = None,
        fallback_trigger_failures: Optional[int] = None,
        fallback_trigger_same_page_steps: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Update Gemini fallback settings
        
        Args:
            gemini_computer_use_model: Model name for Gemini fallback advisor
            fallback_trigger_repetition: Trigger after N repetitions
            fallback_trigger_failures: Trigger after N failures
            fallback_trigger_same_page_steps: Trigger after N same-page steps
            
        Returns:
            Updated fallback settings dict
        """
        if gemini_computer_use_model is not None:
            if gemini_computer_use_model not in AVAILABLE_FALLBACK_MODELS:
                raise ValueError(
                    f"Invalid fallback model '{gemini_computer_use_model}'. "
                    f"Available models: {AVAILABLE_FALLBACK_MODELS}"
                )
            self._fallback_settings["gemini_computer_use_model"] = gemini_computer_use_model
        
        if fallback_trigger_repetition is not None:
            if fallback_trigger_repetition < 0:
                raise ValueError("fallback_trigger_repetition must be >= 0")
            self._fallback_settings["fallback_trigger_repetition"] = int(fallback_trigger_repetition)
        
        if fallback_trigger_failures is not None:
            if fallback_trigger_failures < 0:
                raise ValueError("fallback_trigger_failures must be >= 0")
            self._fallback_settings["fallback_trigger_failures"] = int(fallback_trigger_failures)
        
        if fallback_trigger_same_page_steps is not None:
            if fallback_trigger_same_page_steps < 0:
                raise ValueError("fallback_trigger_same_page_steps must be >= 0")
            self._fallback_settings["fallback_trigger_same_page_steps"] = int(fallback_trigger_same_page_steps)
        
        logger.info(f"Updated fallback settings: {self._fallback_settings}")
        return self.get_fallback_config()
    
    def get_available_fallback_models(self) -> List[str]:
        """
        Get available Gemini models for fallback advisor
        
        Returns:
            List of available fallback model names
        """
        return AVAILABLE_FALLBACK_MODELS.copy()
    
    def get_available_models(self, provider: str) -> List[str]:
        """
        Get available models for a provider
        
        Args:
            provider: Provider name (openai, anthropic, gemini)
            
        Returns:
            List of available model names
        """
        provider_lower = provider.lower()
        if provider_lower not in AVAILABLE_MODELS:
            raise ValueError(f"Invalid provider: {provider}. Must be one of {list(AVAILABLE_MODELS.keys())}")
        return AVAILABLE_MODELS[provider_lower].copy()
    
    def get_browser_config(self) -> Dict[str, Any]:
        """
        Get current browser configuration
        
        Returns:
            Dict with connection_type, kernel_cdp_host, kernel_cdp_port, api_key, api_endpoint
        """
        # Return copy without exposing API key in full (mask it)
        config = self._browser_settings.copy()
        if config.get("api_key"):
            config["api_key"] = "***" + config["api_key"][-4:] if len(config["api_key"]) > 4 else "***"
        return config
    
    def get_browser_config_raw(self) -> Dict[str, Any]:
        """
        Get current browser configuration with full API key (for internal use)
        
        Returns:
            Dict with all browser settings including unmasked API key
        """
        return self._browser_settings.copy()
    
    def update_browser_settings(
        self,
        connection_type: Optional[str] = None,
        kernel_cdp_host: Optional[str] = None,
        kernel_cdp_port: Optional[int] = None,
        api_key: Optional[str] = None,
        api_endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update browser settings
        
        Args:
            connection_type: "localhost" or "api" (default: "localhost")
            kernel_cdp_host: Host for localhost mode (default: "localhost")
            kernel_cdp_port: Port for localhost mode (default: 9222)
            api_key: OnKernel API key (required for API mode)
            api_endpoint: OnKernel API endpoint URL (optional, defaults to standard endpoint)
            
        Returns:
            Updated browser settings dict (with masked API key)
            
        Raises:
            ValueError: If settings are invalid
        """
        if connection_type is not None:
            connection_type_lower = connection_type.lower()
            if connection_type_lower not in ["localhost", "api"]:
                raise ValueError(f"Invalid connection_type: {connection_type}. Must be 'localhost' or 'api'")
            self._browser_settings["connection_type"] = connection_type_lower
            
            # If switching to API mode, validate API key is provided
            if connection_type_lower == "api" and api_key is None and not self._browser_settings.get("api_key"):
                raise ValueError("API key is required when using API connection type")
        
        if kernel_cdp_host is not None:
            if not kernel_cdp_host.strip():
                raise ValueError("kernel_cdp_host cannot be empty")
            self._browser_settings["kernel_cdp_host"] = kernel_cdp_host.strip()
        
        if kernel_cdp_port is not None:
            if not (1 <= kernel_cdp_port <= 65535):
                raise ValueError("kernel_cdp_port must be between 1 and 65535")
            self._browser_settings["kernel_cdp_port"] = int(kernel_cdp_port)
        
        if api_key is not None:
            if not api_key.strip():
                raise ValueError("api_key cannot be empty")
            self._browser_settings["api_key"] = api_key.strip()
        
        if api_endpoint is not None:
            endpoint = api_endpoint.strip()
            if endpoint:
                # Basic URL validation
                if not (endpoint.startswith("http://") or endpoint.startswith("https://")):
                    raise ValueError("api_endpoint must be a valid HTTP/HTTPS URL")
            self._browser_settings["api_endpoint"] = endpoint
        
        logger.info(f"Updated browser settings: connection_type={self._browser_settings['connection_type']}")
        return self.get_browser_config()
    
    def get_all_settings(self) -> Dict[str, Any]:
        """
        Get all runtime settings (for API response)
        
        Returns:
            Dict with llm_settings, fallback_settings, and browser_settings
        """
        return {
            "llm_settings": self.get_llm_config(),
            "fallback_settings": self.get_fallback_config(),
            "browser_settings": self.get_browser_config(),
        }


# Global instance accessor
def get_settings_manager() -> SettingsManager:
    """Get the singleton SettingsManager instance"""
    return SettingsManager()


"""
LLM Integration for QA Agent

Supports multiple LLM providers: OpenAI, Anthropic, and Gemini.
Uses LangChain's chat model classes for each provider.
"""
import logging
from typing import Optional, Union, Any
from qa_agent.config import settings
from qa_agent.utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


def get_structured_output_method(provider: Optional[str] = None) -> Optional[str]:
    """
    Get the appropriate structured output method for the given provider.
    
    This ensures consistent provider-specific method selection across all LLM calls.
    Default behavior maintains OpenAI compatibility (backward compatible).
    
    Args:
        provider: Provider name (openai, anthropic, gemini). If None, uses current runtime settings.
        
    Returns:
        Method string for with_structured_output(), or None to use LangChain default.
        - OpenAI: "function_calling" (OpenAI's native function calling)
        - Anthropic: "tool_use" (Anthropic's tool use format)
        - Gemini: "json_mode" (Gemini's JSON mode - required for complex union schemas)
        
    Note:
        Gemini requires "json_mode" for complex schemas with union types (like ActionModel).
        Using None or "function_calling" with Gemini causes validation errors with empty objects.
    """
    if provider is None:
        settings_manager = get_settings_manager()
        llm_config = settings_manager.get_llm_config()
        provider = llm_config.get("provider", "openai")
    
    provider_lower = provider.lower()
    
    if provider_lower == "openai":
        return "function_calling"  # OpenAI uses function calling
    elif provider_lower == "anthropic":
        return "tool_use"  # Anthropic uses tool_use
    elif provider_lower == "gemini":
        # Gemini requires json_mode for complex union schemas (like ActionModel)
        # function_calling doesn't work well with union types in Gemini
        return "json_mode"
    else:
        # Default fallback to OpenAI method for backward compatibility
        logger.warning(f"Unknown provider '{provider}', defaulting to 'function_calling'")
        return "function_calling"


def get_llm(
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    api_key: Optional[str] = None,
    provider: Optional[str] = None,
) -> Union[Any, Any, Any]:  # ChatOpenAI | ChatAnthropic | ChatGoogleGenerativeAI
    """
    Get an initialized LLM instance based on provider
    
    Args:
        model: Model name (defaults to runtime settings or config)
        temperature: Temperature setting (defaults to runtime settings or config)
        api_key: API key for the provider (defaults to runtime settings or config)
        provider: LLM provider (openai, anthropic, gemini) (defaults to runtime settings or config)
        
    Returns:
        Initialized LLM instance (ChatOpenAI, ChatAnthropic, or ChatGoogleGenerativeAI)
    """
    # Get runtime settings manager
    settings_manager = get_settings_manager()
    llm_config = settings_manager.get_llm_config()
    
    # Use provided params or fallback to runtime settings, then config defaults
    provider_name = provider or llm_config.get("provider") or settings.llm_provider
    model_name = model or llm_config.get("model") or settings.llm_model
    temp = temperature if temperature is not None else llm_config.get("temperature") or settings.llm_temperature
    
    # Get API key from provided, runtime settings, or config
    if api_key:
        key = api_key
    else:
        key = settings_manager.get_api_key(provider_name)
        if not key:
            # Fallback to config
            if provider_name == "openai":
                key = settings.openai_api_key
            elif provider_name == "anthropic":
                key = settings.anthropic_api_key
            elif provider_name == "gemini":
                key = settings.gemini_api_key
    
    if not key:
        raise ValueError(
            f"{provider_name.capitalize()} API key not found. "
            f"Set {provider_name.upper()}_API_KEY environment variable or configure in settings."
        )
    
    provider_lower = provider_name.lower()
    
    # Initialize appropriate LLM based on provider
    if provider_lower == "openai":
        from langchain_openai import ChatOpenAI
        logger.info(f"Initializing ChatOpenAI with model: {model_name}, temperature: {temp}")
        return ChatOpenAI(
            model=model_name,
            temperature=temp,
            api_key=key,
        )
    
    elif provider_lower == "anthropic":
        from langchain_anthropic import ChatAnthropic
        logger.info(f"Initializing ChatAnthropic with model: {model_name}, temperature: {temp}")
        return ChatAnthropic(
            model=model_name,
            temperature=temp,
            api_key=key,
        )
    
    elif provider_lower == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            # Fallback to alternative import path
            try:
                from langchain_google_vertexai import ChatVertexAI
                logger.warning("Using ChatVertexAI instead of ChatGoogleGenerativeAI")
                return ChatVertexAI(
                    model=model_name,
                    temperature=temp,
                )
            except ImportError:
                raise ImportError(
                    "langchain-google-genai package not installed. "
                    "Install it with: pip install langchain-google-genai"
                )
        logger.info(f"Initializing ChatGoogleGenerativeAI with model: {model_name}, temperature: {temp}")
        return ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temp,
            google_api_key=key,
        )
    
    else:
        raise ValueError(
            f"Unsupported provider: {provider_name}. "
            "Supported providers: openai, anthropic, gemini"
        )


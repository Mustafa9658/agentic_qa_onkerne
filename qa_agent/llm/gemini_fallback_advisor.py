"""
Gemini Fallback Advisor

Uses Gemini vision models (gemini-1.5-flash) to analyze screenshots and provide
diagnosis + recovery plan to help the main OpenAI agent when stuck.

The model analyzes screenshots to understand UI context and provide actionable advice.
"""
import logging
import base64
import json
import re
from typing import Optional, Dict, Any, List
from qa_agent.config import settings

logger = logging.getLogger(__name__)


class GeminiFallbackAdvisor:
    """
    Advisor service that uses Gemini vision models to analyze screenshots
    and provide recovery suggestions to the main agent.
    
    Uses gemini-1.5-flash for fast, cost-effective screenshot analysis.
    The model has excellent vision capabilities for understanding UI context.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Gemini Fallback Advisor
        
        Args:
            api_key: Gemini API key (defaults to settings.gemini_api_key)
        """
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = settings.gemini_computer_use_model
        
        if not self.api_key:
            raise ValueError(
                "Gemini API key not found. "
                "Set GEMINI_API_KEY environment variable or configure in settings."
            )
        
        # Initialize Google Generative AI client
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            
            # Try to get the model - handle different naming formats
            # Note: Model names don't include -latest suffix in the API
            # Latest models: gemini-2.5-flash, gemini-2.0-flash-exp, gemini-1.5-pro
            try:
                self.client = genai.GenerativeModel(self.model_name)
            except Exception as e:
                # If model name fails, try common alternatives
                error_msg = str(e)
                logger.warning(f"Model {self.model_name} failed ({error_msg[:100]}), trying alternatives...")
                
                # Updated list based on current available models (as of 2025)
                # Note: gemini-1.5-flash was retired Sept 2025
                alternative_names = [
                    "gemini-2.5-flash",      # Latest Flash (recommended)
                    "gemini-2.0-flash-exp",  # Experimental Flash
                    "gemini-1.5-pro",        # Pro model (still available)
                    "gemini-pro",            # Legacy Pro
                    "gemini-1.5-flash",      # Retired but might still work in some regions
                ]
                
                for alt_name in alternative_names:
                    if alt_name == self.model_name:
                        continue  # Skip if it's the same as what we already tried
                    try:
                        test_client = genai.GenerativeModel(alt_name)
                        # If we get here, model exists
                        self.client = test_client
                        logger.info(f"✅ Using alternative model: {alt_name} (original: {self.model_name})")
                        self.model_name = alt_name
                        break
                    except Exception as alt_e:
                        logger.debug(f"  Alternative {alt_name} also failed: {str(alt_e)[:50]}")
                        continue
                else:
                    # If all alternatives fail, try to list available models
                    try:
                        available = [m.name for m in genai.list_models() 
                                    if 'generateContent' in m.supported_generation_methods]
                        available_str = ', '.join(available[:5])  # Show first 5
                        logger.error(f"Available models: {available_str}...")
                    except:
                        pass
                    
                    # Raise error with helpful message
                    raise ValueError(
                        f"Could not initialize any Gemini model. "
                        f"Tried: {self.model_name} and {len(alternative_names)} alternatives. "
                        f"Original error: {error_msg}. "
                        f"Please check your API key and model availability."
                    )
        except ImportError:
            raise ImportError(
                "google-generativeai package required. "
                "Install with: pip install google-generativeai"
            )
    
    async def analyze_and_advise(
        self,
        task: str,
        screenshot_b64: str,
        current_url: str,
        recent_actions: List[Dict[str, Any]],
        browser_state_summary: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Analyze screenshot and provide diagnosis + recovery plan
        
        This is NOT executing actions - just providing advice to the main agent.
        
        Args:
            task: Original user task
            screenshot_b64: Base64 encoded screenshot (no data: prefix)
            current_url: Current page URL
            recent_actions: Recent actions that may have failed/repeated
            browser_state_summary: Browser state summary for context
            
        Returns:
            Dict with:
            {
                "diagnosis": "Why agent is stuck",
                "recovery_plan": ["suggestion1", "suggestion2", ...],
                "suggested_actions": [{"action": "click", "reason": "...", ...}, ...],
                "confidence": 0.85
            }
        """
        # Format context for Gemini
        history_text = self._format_recent_actions(recent_actions)
        browser_context = self._format_browser_state(browser_state_summary)
        
        # Build prompt for Gemini vision model
        # We're asking it to ANALYZE and ADVISE, not execute
        prompt = f"""You are an expert web automation advisor. An automation agent is stuck and needs your help.

TASK: {task}
CURRENT URL: {current_url}

RECENT ACTIONS (that may have failed/repeated):
{history_text}

BROWSER STATE:
{browser_context}

Please analyze the screenshot and provide:
1. DIAGNOSIS: Why is the agent stuck? What's the problem?
2. RECOVERY PLAN: Specific suggestions to help the agent progress
3. SUGGESTED ACTIONS: What actions should the agent try next? (with reasons)

The agent has access to these actions: click, input, scroll, navigate, wait, extract, etc.
The agent uses element indices (like click index 123) to interact with elements.

Respond in JSON format:
{{
    "diagnosis": "Clear explanation of why agent is stuck",
    "recovery_plan": ["suggestion1", "suggestion2", ...],
    "suggested_actions": [
        {{
            "action": "click",
            "description": "Click on the submit button",
            "reason": "The form is filled but not submitted",
            "element_hint": "Look for button with text 'Submit' or index near 4500"
        }},
        ...
    ],
    "confidence": 0.85
}}"""

        try:
            # Prepare content with screenshot
            # For Gemini API, images need to be passed as Part objects
            import google.generativeai as genai
            
            # Create content parts - text and image
            # Gemini vision models (like gemini-1.5-flash) handle screenshots natively
            content_parts = [
                prompt,
                {
                    "mime_type": "image/png",
                    "data": screenshot_b64  # Base64 string without data: prefix
                }
            ]
            
            # Call Gemini vision model (gemini-1.5-flash)
            # This model has excellent vision capabilities for analyzing screenshots
            # and understanding UI context. It's fast, cost-effective, and available on free tier.
            # Perfect for fallback advisor use case: analyze screenshot and provide advice.
            response = await self.client.generate_content_async(
                contents=content_parts,
            )
            
            # Parse response
            response_text = ""
            if response.candidates and response.candidates[0].content:
                parts = response.candidates[0].content.parts
                for part in parts:
                    if hasattr(part, 'text'):
                        response_text += part.text
            
            # Extract JSON from response
            advice = self._parse_response(response_text)
            
            logger.info(f"✅ Gemini Fallback Advisor: {advice.get('diagnosis', 'Unknown')[:100]}")
            logger.info(f"   Recovery plan: {len(advice.get('recovery_plan', []))} suggestions")
            
            return advice
            
        except Exception as e:
            logger.error(f"❌ Gemini Fallback Advisor failed: {e}")
            return {
                "diagnosis": f"Fallback analysis failed: {str(e)}",
                "recovery_plan": [],
                "suggested_actions": [],
                "confidence": 0.0,
                "error": str(e)
            }
    
    def _format_recent_actions(self, actions: List[Dict[str, Any]]) -> str:
        """Format recent actions for prompt"""
        if not actions:
            return "No recent actions"
        
        formatted = []
        for i, action in enumerate(actions[-5:], 1):  # Last 5 actions
            action_type = action.get("action", "unknown")
            action_params = action.get("params", {})
            result = action.get("result", {})
            status = result.get("status", "unknown") if isinstance(result, dict) else str(result)
            error = result.get("error") if isinstance(result, dict) else None
            
            line = f"{i}. {action_type}({action_params}) -> {status}"
            if error:
                line += f" [ERROR: {error}]"
            formatted.append(line)
        
        return "\n".join(formatted)
    
    def _format_browser_state(self, state: Optional[Dict[str, Any]]) -> str:
        """Format browser state summary for prompt"""
        if not state:
            return "No browser state available"
        
        return f"""
URL: {state.get('url', 'Unknown')}
Title: {state.get('title', 'Unknown')}
Element Count: {state.get('element_count', 0)}
Visible Elements: {state.get('visible_elements', 0)}
"""
    
    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse Gemini response (expecting JSON)"""
        # Try to extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Fallback: return structured response from text
        return {
            "diagnosis": response_text[:500],  # First 500 chars
            "recovery_plan": [],
            "suggested_actions": [],
            "confidence": 0.5
        }
    
    def format_advice_for_prompt(self, advice: Dict[str, Any]) -> str:
        """
        Format Gemini advice for inclusion in OpenAI agent prompt
        
        This adds the advice to the agent's context so it can use it.
        """
        diagnosis = advice.get("diagnosis", "")
        recovery_plan = advice.get("recovery_plan", [])
        suggested_actions = advice.get("suggested_actions", [])
        confidence = advice.get("confidence", 0.0)
        
        formatted = f"""
<fallback_advisor_analysis>
The agent appears to be stuck. A fallback advisor (Gemini Computer Use) analyzed the current screenshot and provided the following analysis:

DIAGNOSIS:
{diagnosis}

RECOVERY PLAN:
"""
        for i, suggestion in enumerate(recovery_plan, 1):
            formatted += f"{i}. {suggestion}\n"
        
        formatted += "\nSUGGESTED ACTIONS:\n"
        for i, action in enumerate(suggested_actions, 1):
            action_type = action.get("action", "unknown")
            description = action.get("description", "")
            reason = action.get("reason", "")
            element_hint = action.get("element_hint", "")
            
            formatted += f"{i}. {action_type.upper()}: {description}\n"
            formatted += f"   Reason: {reason}\n"
            if element_hint:
                formatted += f"   Hint: {element_hint}\n"
        
        formatted += f"\nConfidence: {confidence:.0%}\n"
        formatted += "</fallback_advisor_analysis>\n"
        formatted += "\nUse this analysis to help plan your next actions. The advisor's suggestions are recommendations - you should still analyze the browser_state and make your own decisions.\n"
        
        return formatted


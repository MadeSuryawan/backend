"""
AI configuration module for Gemini API integration.

This module provides AI model configuration, safety settings, and generation
configuration for the Google Gemini API integration.
"""

from google.genai.types import (
    GenerateContentConfig,
    GoogleSearch,
    HarmBlockThreshold,
    HarmCategory,
    SafetySetting,
    Tool,
)

from app.configs.settings import settings

# AI Model Configuration
GEMINI_MODEL = "gemini-2.5-flash-lite"

# Type aliases for safety configuration
Harm = HarmCategory
Block = HarmBlockThreshold

# Safety threshold mapping
SAFETY_THRESHOLD_MAP: dict[str, HarmBlockThreshold] = {
    "none": HarmBlockThreshold.BLOCK_NONE,
    "low": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    "medium": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    "high": HarmBlockThreshold.BLOCK_ONLY_HIGH,
}


def get_safety_settings(threshold: str = "medium") -> list[SafetySetting]:
    """
    Get safety settings based on configured threshold.

    Args:
        threshold: Safety threshold level (none, low, medium, high)

    Returns:
        List of SafetySetting objects configured with the specified threshold

    Example:
        >>> settings = get_safety_settings("high")
        >>> len(settings)
        4

    """
    block_threshold = SAFETY_THRESHOLD_MAP.get(threshold, HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE)
    return [
        SafetySetting(
            category=Harm.HARM_CATEGORY_HARASSMENT,
            threshold=block_threshold,
        ),
        SafetySetting(
            category=Harm.HARM_CATEGORY_HATE_SPEECH,
            threshold=block_threshold,
        ),
        SafetySetting(
            category=Harm.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=block_threshold,
        ),
        SafetySetting(
            category=Harm.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=block_threshold,
        ),
    ]


# Tools: Explicitly enable only what needed (Google Search)
SEARCH_TOOL = [Tool(google_search=GoogleSearch())]


def get_generation_config(threshold: str | None = None) -> GenerateContentConfig:
    """
    Get generation config with optional custom safety threshold.

    Args:
        threshold: Optional safety threshold override (none, low, medium, high).
                  If not provided, uses the value from settings.

    Returns:
        GenerateContentConfig configured with specified safety settings

    Example:
        >>> config = get_generation_config("high")
        >>> config.temperature
        0.7

    """
    safety_threshold = threshold or settings.AI_SAFETY_THRESHOLD
    return GenerateContentConfig(
        temperature=0.7,
        top_p=0.8,
        top_k=40,
        max_output_tokens=8192,  # 4096 * 2
        safety_settings=get_safety_settings(safety_threshold),
        tools=SEARCH_TOOL,
    )


# Default generation config using settings from configuration
GENERATION_CONFIG = get_generation_config()

# Safety settings based on default threshold
SAFETY_SETTINGS = get_safety_settings(settings.AI_SAFETY_THRESHOLD)

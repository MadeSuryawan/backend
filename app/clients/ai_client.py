from json import JSONDecodeError
from json.decoder import JSONDecoder
from logging import getLogger
from re import DOTALL, search
from typing import Any

from google.genai import Client
from google.genai.types import (
    Content,
    ContentListUnion,
    ContentListUnionDict,
    GenerateContentResponse,
    Part,
)

# from pydantic import ValidationError
from app.configs.settings import (
    GEMINI_MODEL,
    GENERATION_CONFIG,
    SAFETY_SETTINGS,
    file_logger,
    settings,
)
from app.decorators import with_retry
from app.errors import (
    AiAuthenticationError,
    AIClientError,
    AiError,
    AIGenerationError,
    AiNetworkError,
    AiQuotaExceededError,
)

# from app.managers import cache_manager
# from app.schemas.ai import Itinerary

logger = file_logger(getLogger(__name__))

RETRIABLE_EXCEPTIONS = (AiNetworkError, AiQuotaExceededError, AIGenerationError, AiError)


def validate_response(response: GenerateContentResponse) -> str:
    """
    Validate and extract text from API response.

    Args:
        response: The response object from the API.

    Returns:
        The extracted text from the response.

    Raises:
        AIGenerationError: If response is empty or invalid.

    """
    if response and response.text:
        return response.text

    msg = "Empty response from Gemini API"
    raise AIGenerationError(msg)


class AiClient:
    """
    Async client for Google's Gemini API with caching and error handling.

    Attributes:
        client: The Google GenAI AsyncClient instance.
        model_name: The name of the Gemini model to use.
    """

    def __init__(self) -> None:
        """Initialize the AI client with API credentials."""
        self._model = GEMINI_MODEL
        self._config = GENERATION_CONFIG
        self._safety_settings = SAFETY_SETTINGS
        self._max_retries = settings.AI_MAX_RETRIES
        self._retry_delay = settings.AI_RETRY_DELAY
        self._backoff_factor = settings.AI_BACKOFF_FACTOR
        self._timeout = settings.AI_REQUEST_TIMEOUT

        try:
            self._client = Client(api_key=settings.GEMINI_API_KEY).aio
        except Exception as e:
            logger.exception(
                "Failed to initialize Gemini client, missing or invalid API key?",
            )
            msg = "Failed to initialize Gemini client"
            raise AIClientError(detail=msg) from e

        logger.info(f"AIClient initialized with model: {self._model}")
        # return self._client

    async def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        """
        Parse JSON response from model.

        Args:
            response_text: The raw response text from the model.

        Returns:
            Parsed JSON dictionary.

        Raises:
            AIGenerationError: If JSON parsing fails.

        """
        logger.debug(f"Raw response text: {response_text}")
        # 1. Regex to extract content strictly within ```json ... ``` blocks if present.
        #    This is safer than simple stripping if the AI puts text before AND after.
        code_block_match = search(r"```(?:json)?\s*(.*?)```", response_text, DOTALL)
        if code_block_match:
            text_to_parse = code_block_match.group(1).strip()
        else:
            text_to_parse = response_text.strip()

        # 2. Find the absolute starting point of the JSON structure
        start_index = text_to_parse.find("{")
        if start_index == -1:
            msg = "No JSON object found in response."
            logger.exception(msg)
            raise ValueError(msg)

        text_to_parse = text_to_parse[start_index:]

        # 3. raw_decode parses strictly one object and ignores trailing data
        try:
            obj, _ = JSONDecoder().raw_decode(text_to_parse)
            return obj  # type: ignore[no-any-return]
        except JSONDecodeError as e:
            msg = f"Failed to parse JSON response. {e}"
            logger.exception("json_decode_error")
            raise AIGenerationError(detail=msg) from e

    # async def generate_itinerary(
    #     self,
    #     user_preferences: dict[str, Any],
    #     *,
    #     force_refresh: bool = False,
    # ) -> Itinerary:
    #     """
    #     Generate a personalized travel itinerary based on user preferences.

    #     Args:
    #         user_preferences: Dictionary containing user preferences (destination, dates, interests, etc.)
    #         force_refresh: Whether to bypass the cache.

    #     Returns:
    #         Itinerary: A structured itinerary object.

    #     Raises:
    #         AiError: If generation fails.
    #     """
    #     if not self._client:
    #         msg = "AI client is not initialized."
    #         raise AiAuthenticationError(msg)

    #     # Create a cache key based on sorted preferences
    #     prefs_str = dumps(user_preferences, sort_keys=True)
    #     cache_key = f"itinerary:{hash(prefs_str)}"

    #     if not force_refresh:
    #         cached_data = await cache_manager.get(cache_key)
    #         if cached_data:
    #             try:
    #                 # cached_data is already deserialized (dict)
    #                 if isinstance(cached_data, dict):
    #                     return Itinerary.model_validate(cached_data)
    #                 logger.warning(f"Cached data has unexpected type: {type(cached_data)}")
    #             except ValidationError as e:
    #                 logger.warning(f"Failed to validate cached itinerary: {e}")
    #                 # Proceed to generate

    #     prompt = self._construct_itinerary_prompt(user_preferences)

    #     try:
    #         response = await self._client.models.generate_content(
    #             model=self._model,
    #             contents=prompt,
    #             config=GenerateContentConfig(
    #                 response_mime_type="application/json",
    #                 response_schema=Itinerary,
    #                 temperature=0.7,
    #             ),
    #         )

    #         if not response.parsed:
    #             msg = "Failed to parse itinerary response."
    #             raise AiResponseError(msg)

    #         itinerary = response.parsed

    #         # Ensure it's the correct type
    #         if not isinstance(itinerary, Itinerary):
    #             if isinstance(itinerary, dict):
    #                 itinerary = Itinerary.model_validate(itinerary)
    #             else:
    #                 try:
    #                     itinerary = Itinerary.model_validate(itinerary)
    #                 except Exception as e:
    #                     msg = f"Received unexpected type from AI: {type(itinerary)}"
    #                     raise AiResponseError(msg) from e

    #         # Cache the result
    #         await cache_manager.set(
    #             cache_key,
    #             itinerary.model_dump(),
    #             ttl=3600 * 24,  # Cache for 24 hours
    #         )

    #         return itinerary

    #     except Exception as e:
    #         self._handle_exception(e)
    #         raise  # Should be unreachable due to _handle_exception raising

    async def chat(self, message: str, history: list[Content]) -> dict[str, str]:
        """
        Handle chat interactions.

        Expects history in format: [{'role': 'user', 'parts': [{'text': '...'}]}, ...]

        """
        contents = history if history else []
        contents.append(
            Content(role="user", parts=[Part(text=message)]),
        )

        # 1. Prepare the system instruction
        # system_instruction = "You are Aero, a friendly and helpful travel agent assistant."

        # 2. Prepare contents (History + New Message)
        # The SDK expects 'contents' to be a list of messages including the history
        # contents = []

        # Convert simple frontend history to SDK format if necessary
        # Assuming frontend sends: [{'role': 'user', 'content': 'hi'}]
        # We need SDK format: Content(role='user', parts=[Part(text='hi')])

        # for msg in history:
        #     role = "user" if msg.get("role") in ["user", "human"] else "model"
        #     text_content = msg.get("content", "")
        #     contents.append(Content(role=role, parts=[Part(text=text_content)]))

        system_instruction = (
            "You are a friendly customer service assistant for a Bali travel agency called BaliBlissed."
            "You MUST reply with a SINGLE valid JSON object in this format: "
            '{"response": "your markdown formatted message here"}. '
            "Do not output multiple JSON objects. Do not add explanations outside the JSON."
        )
        self._config.system_instruction = system_instruction
        self._config.response_mime_type = "application/json"
        # Higher temp for creativity, 0.4 for itinerary for more factual responses
        self._config.temperature = 0.7

        # Append the current new user message
        contents.append(Content(role="user", parts=[Part(text=message)]))

        response = await self._generate_content(contents)

        return await self._parse_json_response(validate_response(response))

    def _construct_itinerary_prompt(self, preferences: dict[str, str]) -> str:
        """Construct a detailed prompt for itinerary generation."""
        destination = preferences.get("destination", "Bali")
        duration = preferences.get("duration", "5 days")
        interests = preferences.get("interests", [])
        budget = preferences.get("budget", "medium")
        travelers = preferences.get("travelers", "couple")

        return (
            f"Plan a {duration} trip to {destination} for a {travelers}. "
            f"Interests: {', '.join(interests)}. "
            f"Budget: {budget}. "
            "Please provide a detailed day-by-day itinerary with activities, "
            "locations, and practical travel tips."
        )

    def _handle_exception(self, e: Exception) -> None:
        """Map generic exceptions to specific AiError."""
        error_msg = str(e)
        logger.exception(f"AI Error: {error_msg}", exc_info=True)

        # Check for specific Google API errors
        if "401" in error_msg or "unauthenticated" in error_msg.lower():
            detail = f"Authentication failed: {error_msg}"
            raise AiAuthenticationError(detail=detail) from e
        elif "429" in error_msg or "quota" in error_msg.lower():
            detail = f"Quota exceeded: {error_msg}"
            raise AiQuotaExceededError(detail=detail) from e
        elif "connection" in error_msg.lower():
            detail = f"Network error: {error_msg}"
            raise AiNetworkError(detail=detail) from e
        else:
            detail = f"An unexpected error occurred: {error_msg}"
            raise AiError(detail=detail) from e

    @with_retry(
        max_retries=settings.AI_MAX_RETRIES,
        base_delay=settings.AI_RETRY_DELAY,
        max_delay=settings.AI_REQUEST_TIMEOUT,
        exec_retry=RETRIABLE_EXCEPTIONS,
    )
    async def _generate_content(
        self,
        contents: ContentListUnion | ContentListUnionDict,
    ) -> GenerateContentResponse:
        """
        Generate content from a custom prompt.

        This is a low-level method for generating content with custom prompts
        and configurations. For specific use cases, prefer the higher-level
        methods like generate_itinerary, process_query, etc.

        Args:
            contents: The contents to send to the model.

        Returns:
            The generated text response.

        Raises:
            AIGenerationError: If content generation fails.

        """

        return await self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=self._config,
        )


ai_client = AiClient()


def get_ai_client() -> AiClient:
    return ai_client

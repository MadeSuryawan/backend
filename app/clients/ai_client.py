from json import JSONDecodeError
from json.decoder import JSONDecoder
from logging import getLogger
from re import DOTALL, search
from typing import Any, cast

from google.genai import Client
from google.genai.client import AsyncClient
from google.genai.errors import ClientError
from google.genai.types import (
    ContentListUnion,
    ContentListUnionDict,
    GenerateContentConfig,
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
from app.errors.ai import ContactAnalysisError
from app.managers.circuit_breaker import ai_circuit_breaker
from app.schemas.ai.chatbot import ChatResponse
from app.schemas.email import AnalysisFormat, ContactAnalysisResponse

# from app.managers import cache_manager
# from app.schemas.ai import Itinerary

logger = file_logger(getLogger(__name__))

RETRIABLE_EXCEPTIONS = (
    AiNetworkError,
    AiQuotaExceededError,
    AIGenerationError,
    AiError,
    ContactAnalysisError,
    ClientError,
    TypeError,
)

RespType = type[ChatResponse] | type[AnalysisFormat] | type[ContactAnalysisResponse]


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
        self._circuit_breaker = ai_circuit_breaker

        try:
            self._client = Client(api_key=settings.GEMINI_API_KEY).aio
        except Exception as e:
            logger.exception(
                "Failed to initialize Gemini client, missing or invalid API key?",
            )
            msg = "Failed to initialize Gemini client"
            raise AIClientError(detail=msg) from e

        logger.info(f"AIClient initialized with model: {self._model}")

    @property
    def client(self) -> AsyncClient:
        """Get the AI client instance."""
        return self._client

    @with_retry(
        max_retries=settings.AI_MAX_RETRIES,
        base_delay=settings.AI_RETRY_DELAY,
        max_delay=settings.AI_REQUEST_TIMEOUT,
        exec_retry=RETRIABLE_EXCEPTIONS,
    )
    async def _generate_content(
        self,
        contents: ContentListUnion | ContentListUnionDict,
        config: GenerateContentConfig,
    ) -> object:
        """
        Generate content from a custom prompt.

        This is a low-level method for generating content with custom prompts
        and configurations. For specific use cases, prefer the higher-level
        methods like generate_itinerary, process_query, etc.

        Args:
            contents: The contents to send to the model.
            config: The configuration for the content generation.

        Returns:
            The generated text response.

        Raises:
            AIGenerationError: If content generation fails.

        """
        response = await self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        if response and not response.text:
            msg = "Empty response from Gemini API"
            raise AIGenerationError(detail=msg)
        # Validate response schema. (Defensive programming)
        schema = config.response_schema
        # If schema is a Class (like Pydantic model), use isinstance check
        if isinstance(schema, type) and not isinstance(response.parsed, schema):
            msg = f"Unexpected response type: {type(response.parsed)}, expected {schema}"
            raise AIGenerationError(detail=msg)
        return response.parsed

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
        logger.debug(f"{type(response_text)=}")
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

    async def do_service(
        self,
        contents: ContentListUnion | ContentListUnionDict,
        system_instruction: str,
        resp_type: RespType,
        temperature: float = 0.7,
    ) -> object:
        """
        Generate content with AI using circuit breaker protection.

        This is the main method for interacting with the AI model.
        It includes circuit breaker protection to prevent cascading failures.

        Args:
            contents: The contents to send to the model.
            system_instruction: The system instruction for the content generation.
            resp_type: The type of the response.
            temperature: The temperature for the content generation.

        Returns:
            The response object matching resp_type.

        Raises:
            CircuitBreakerError: If the circuit breaker is open.
            AIGenerationError: If content generation fails.
        """
        config = GenerateContentConfig(
            top_p=self._config.top_p,
            top_k=self._config.top_k,
            max_output_tokens=self._config.max_output_tokens,
            safety_settings=self._config.safety_settings,
            tools=self._config.tools,
            response_mime_type="application/json",
            system_instruction=system_instruction,
            response_schema=resp_type,
            temperature=temperature,
        )

        try:
            if self._circuit_breaker:
                result = await self._circuit_breaker.call(
                    self._generate_content,
                    contents,
                    config,
                )
            else:
                result = await self._generate_content(contents, config)

            return cast(resp_type, result)
        except Exception:
            logger.exception("AI content generation failed")
            raise

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

    async def close(self) -> None:
        try:
            logger.info("Closing AI client")
            await self.client.aclose()
        except Exception:
            logger.exception("Failed to close AI client", exc_info=True)
        else:
            logger.info("AI client closed successfully")

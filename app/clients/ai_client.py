# app/clients/ai_client.py

from logging import getLogger
from typing import cast

from google.genai import Client
from google.genai.client import AsyncClient
from google.genai.errors import ClientError
from google.genai.types import (
    ContentListUnion,
    ContentListUnionDict,
    GenerateContentConfig,
)
from httpx import RemoteProtocolError, TimeoutException

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
    AiError,
    AIGenerationError,
    AiNetworkError,
    AiQuotaExceededError,
)
from app.errors.ai import ContactAnalysisError, ItineraryGenerationError
from app.managers.circuit_breaker import ai_circuit_breaker
from app.schemas.ai.chatbot import ChatResponse
from app.schemas.ai.itinerary import ConversionResponse, ItineraryResponse
from app.schemas.email import AnalysisFormat, ContactAnalysisResponse

# from app.managers import cache_manager
# from app.schemas.ai import Itinerary

logger = file_logger(getLogger(__name__))

# Network-related exceptions that should be caught and converted
NETWORK_EXCEPTIONS = (
    RemoteProtocolError,
    TimeoutException,
    ConnectionError,
    OSError,
)

RETRIABLE_EXCEPTIONS = (
    AiNetworkError,
    AiQuotaExceededError,
    AIGenerationError,
    AiError,
    ContactAnalysisError,
    ClientError,
    TypeError,
    ItineraryGenerationError,
)

RespType = (
    type[ChatResponse]
    | type[AnalysisFormat]
    | type[ContactAnalysisResponse]
    | type[ItineraryResponse]
    | type[ConversionResponse]
)


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
            # msg = "Failed to initialize Gemini client"
            # raise AIClientError(detail=msg) from e
            self._handle_exception(e)

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
            # response_schema={
            #     "type": "object",
            #     "properties": {
            #         "answer": {"type": "string"},
            #     },
            #     "required": ["answer"],
            # },
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
        except NETWORK_EXCEPTIONS as e:
            # Convert network errors to AiNetworkError for proper handling
            error_msg = str(e)
            logger.exception(f"AI network error: {error_msg}")
            detail = f"AI service temporarily unavailable: {error_msg}"
            raise AiNetworkError(detail=detail) from e
        except AiError:
            # Already our custom error, just re-raise
            raise
        except Exception as e:
            # Convert unknown exceptions to AiError for proper handling
            logger.exception("AI content generation failed")
            self._handle_exception(e)

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

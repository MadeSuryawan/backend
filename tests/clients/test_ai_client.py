from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_mock.plugin import MockerFixture

from app.clients.ai_client import AiClient
from app.configs import settings
from app.errors import AiQuotaExceededError
from app.schemas.ai import Activity, DayPlan, Itinerary


@pytest.fixture
def mock_settings(mocker: MockerFixture) -> None:
    mocker.patch.object(settings, "GEMINI_API_KEY", "fake-api-key")


@pytest.fixture
def mock_cache_manager(mocker: MockerFixture) -> None:
    mock = mocker.patch("app.clients.ai_client.cache_manager")
    mock.get = AsyncMock()
    mock.set = AsyncMock()
    return mock


@pytest.fixture
def ai_client_instance(mock_settings: None, mock_cache_manager: None) -> AiClient:
    with patch("google.genai.Client") as mock_client:
        mock_aio_client = AsyncMock()
        mock_client.return_value.aio = mock_aio_client
        client = AiClient()
        # Explicitly set client to mock, in case __init__ logic was skipped or different
        client.client = mock_aio_client
        return client


@pytest.mark.asyncio
async def test_generate_itinerary_success(
    ai_client_instance: AiClient,
    mock_cache_manager: None,
) -> None:
    # Setup mock response
    mock_itinerary = Itinerary(
        trip_title="Bali Trip",
        destination="Bali",
        duration_days=5,
        overview="A great trip",
        daily_plans=[
            DayPlan(
                day=1,
                title="Arrival",
                activities=[Activity(time="09:00", description="Arrive", location="Airport")],
            ),
        ],
    )

    mock_response = MagicMock()
    mock_response.parsed = mock_itinerary
    ai_client_instance.client.models.generate_content.return_value = mock_response

    # Mock cache miss
    mock_cache_manager.get.return_value = None

    user_prefs = {"destination": "Bali", "duration": "5 days"}
    result = await ai_client_instance.generate_itinerary(user_prefs)

    assert result == mock_itinerary
    ai_client_instance.client.models.generate_content.assert_called_once()
    mock_cache_manager.set.assert_called_once()


@pytest.mark.asyncio
async def test_generate_itinerary_cache_hit(
    ai_client_instance: AiClient,
    mock_cache_manager: None,
) -> None:
    mock_itinerary_dict = {
        "trip_title": "Bali Trip",
        "destination": "Bali",
        "duration_days": 5,
        "overview": "A great trip",
        "daily_plans": [
            {
                "day": 1,
                "title": "Arrival",
                "activities": [
                    {"time": "09:00", "description": "Arrive", "location": "Airport", "tips": None},
                ],
            },
        ],
        "estimated_cost": None,
    }

    # Mock cache hit
    mock_cache_manager.get.return_value = mock_itinerary_dict

    user_prefs = {"destination": "Bali", "duration": "5 days"}
    result = await ai_client_instance.generate_itinerary(user_prefs)

    assert result.trip_title == "Bali Trip"
    ai_client_instance.client.models.generate_content.assert_not_called()


from tenacity import RetryError


@pytest.mark.asyncio
async def test_generate_itinerary_api_error(
    ai_client_instance: AiClient, mock_cache_manager: None
) -> None:
    mock_cache_manager.get.return_value = None
    ai_client_instance.client.models.generate_content.side_effect = Exception("429 Quota exceeded")

    user_prefs = {"destination": "Bali"}

    # Since retries are enabled, it will eventually raise RetryError wrapping the actual error
    with pytest.raises(RetryError) as exc_info:
        await ai_client_instance.generate_itinerary(user_prefs)

    # Verify the underlying error was AiQuotaExceededError
    assert isinstance(exc_info.value.last_attempt.exception(), AiQuotaExceededError)


@pytest.mark.asyncio
async def test_chat_success(ai_client_instance: AiClient) -> None:
    mock_response = MagicMock()
    mock_response.text = "Hello! How can I help you?"
    ai_client_instance.client.models.generate_content.return_value = mock_response

    response = await ai_client_instance.chat("Hi")

    assert response == "Hello! How can I help you?"
    ai_client_instance.client.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_chat_empty_response(ai_client_instance: AiClient) -> None:
    mock_response = MagicMock()
    mock_response.text = None
    ai_client_instance.client.models.generate_content.return_value = mock_response

    response = await ai_client_instance.chat("Hi")

    assert response == "I'm sorry, I couldn't generate a response."


@pytest.mark.asyncio
async def test_initialization_no_api_key(mocker: MockerFixture) -> None:
    mocker.patch.object(settings, "GEMINI_API_KEY", None)
    client = AiClient()
    assert client.client is None

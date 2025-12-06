from google.genai.types import Content

from app.clients.ai_client import AiClient
from app.schemas.ai.chatbot import ChatRequest, ChatResponse


async def chat_with_ai(request: ChatRequest, client: AiClient) -> ChatResponse:
    """Process a chat request and return an itinerary."""

    history = [Content(**h.model_dump()) for h in request.history]

    response_text = await client.chat(request.query, history)
    return ChatResponse(answer=response_text)

from google.genai.types import Content

from app.clients.ai_client import AiClient
from app.schemas.ai.chatbot import ChatRequest, ChatResponse


async def chat_with_ai(chat: ChatRequest, client: AiClient) -> ChatResponse:
    """Chat to agent."""

    history = [Content(**h.model_dump()) for h in chat.history]
    return await client.chat(chat.query, history)

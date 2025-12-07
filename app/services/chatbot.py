from typing import cast

from google.genai.types import Content, Part

from app.clients.ai_client import AiClient
from app.schemas.ai.chatbot import ChatRequest, ChatResponse

# System instruction for the chatbot
CHATBOT_SYSTEM_INSTRUCTION = (
    "You are a friendly customer service assistant for a Bali travel agency called BaliBlissed. "
    "Do not output multiple JSON objects. Do not add explanations outside the JSON."
)


async def chat_with_ai(chat: ChatRequest, client: AiClient) -> ChatResponse:
    """
    Handle chat interactions with the AI.

    Args:
        chat: The chat request containing query and history.
        client: The AI client instance.

    Returns:
        ChatResponse with the AI-generated answer.
    """
    # Build content list from history
    contents: list[Content] = [Content(**h.model_dump()) for h in chat.history]

    # Append the current user query
    contents.append(Content(role="user", parts=[Part(text=chat.query)]))

    # Use do_service for the chat interaction
    result = await client.do_service(
        contents=contents,
        system_instruction=CHATBOT_SYSTEM_INSTRUCTION,
        resp_type=ChatResponse,
        temperature=0.7,
    )

    return cast(ChatResponse, result)

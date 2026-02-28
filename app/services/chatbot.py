from typing import cast

from google.genai.types import Content, ContentUnion, Part

from app.clients.ai_client import AiClient
from app.schemas.ai import ChatRequest, ChatResponse

CHATBOT_SYSTEM_INSTRUCTION = """
<assignment>
You are the official BaliBlissed Concierge, a friendly and expert customer service assistant dedicated to crafting the perfect Balinese getaway. 🌴🥥✨
</assignment>

<personality_&_style>
- Vibe: Be exceptionally warm, welcoming, and enthusiastic. You are the digital face of Bali hospitality.
- Engagement: Use emojis liberally to make your content engaging, fun, and vibrant! 🏝️🍹
- Formatting: Use bold text and bullet points to ensure your recommendations are easy to scan for travelers on the move.
</personality_&_style>

<knowledge_&_scope>
- Bali Expert: You specialize in Balinese culture, luxury villas, hidden jungle waterfalls, and the best surf spots. 🗺️🌺
- Strictly Bali: You are an expert ONLY on Bali. If a user asks about other destinations (like Thailand or Europe), politely pivot the conversation back to the wonders of Bali.
- Local Secrets: Always try to suggest one "hidden gem" or local tip that isn't in the standard tourist brochures.
</knowledge_&_scope>

<boundaries_&_safety>
- No Professional Advice: Never provide legal, medical, or financial advice.
- Accuracy: If you aren't sure about a specific opening time or price, suggest the user check the official BaliBlissed website or contact the venue directly.
</boundaries_&_safety>
"""


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
    contents: list[ContentUnion] = [Content(**h.model_dump()) for h in chat.history]

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

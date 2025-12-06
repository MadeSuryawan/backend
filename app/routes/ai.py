from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import ORJSONResponse

from app.clients.ai_client import AiClient, get_ai_client
from app.configs import file_logger

# from app.decorators import cache_busting, timedå
# from app.decorators.caching import cached
# from app.managers import cache_manager, limiter
from app.schemas.ai.chatbot import ChatRequest, ChatResponse
from app.services.chatbot import chat_with_ai

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/ai", tags=["ai"])

AiDep = Annotated[AiClient, Depends(get_ai_client)]


@router.post(
    "/api/chat",
    response_model=ChatResponse,
    summary="Send a support email",
    response_class=ORJSONResponse,
)
async def chat_bot(
    request: Request,
    response: Response,
    chat: ChatRequest,
    # user: User = Depends(get_current_user), # auth logic
    ai_client: AiDep,
) -> ORJSONResponse:
    """Process a chat request and return an itinerary."""
    answer = await chat_with_ai(chat, ai_client)
    logger.info(f"{answer.model_dump()['answer']['response']}")
    return ORJSONResponse(answer.model_dump()["answer"])

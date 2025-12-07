from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse
from starlette.responses import Response

from app.clients.ai_client import AiClient
from app.configs import file_logger
from app.decorators import timed
from app.managers import limiter
from app.schemas.ai.chatbot import ChatRequest, ChatResponse
from app.services.chatbot import chat_with_ai

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_client_state(request: Request) -> AiClient:
    return request.app.state.ai_client


AiDep = Annotated[AiClient, Depends(get_ai_client_state)]


@router.post(
    "/chat",
    response_class=ORJSONResponse,
    response_model=ChatResponse,
)
@limiter.limit("10/minute")
@timed("/ai/chat")
async def chat_bot(
    request: Request,
    response: Response,
    chat: ChatRequest,
    # user: User = Depends(get_current_user), # auth logic
    ai_client: AiDep,
) -> ORJSONResponse:
    """Chat to agent."""
    answer = await chat_with_ai(chat, ai_client)
    return ORJSONResponse(answer.model_dump())

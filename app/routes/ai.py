from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse
from starlette.responses import Response

from app.clients.ai_client import AiClient
from app.clients.email_client import EmailClient
from app.configs import file_logger
from app.decorators import timed
from app.managers import limiter
from app.schemas.ai.chatbot import ChatRequest, ChatResponse
from app.schemas.email import ContactAnalysisResponse, EmailInquiry
from app.services.chatbot import chat_with_ai
from app.services.email_inquiry import analyze_contact, confirmation_message

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_client_state(request: Request) -> AiClient:
    return request.app.state.ai_client


AiDep = Annotated[AiClient, Depends(get_ai_client_state)]


def get_email_client() -> EmailClient:
    return EmailClient()


EmailDep = Annotated[EmailClient, Depends(get_email_client)]


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


@router.post(
    "/email-inquiry/",
    response_class=ORJSONResponse,
    response_model=ContactAnalysisResponse,
)
@limiter.limit("5/hour")
@timed("/ai/email-inquiry")
async def email_inquiry_confirmation_message(
    request: Request,
    response: Response,
    email_inquiry: EmailInquiry,
    # user: User = Depends(get_current_user), # auth logic
    ai_client: AiDep,
    email_client: EmailDep,
) -> ORJSONResponse:
    """
    Send a travel inquiry email.

    Rate Limited: 5 requests per hour to prevent spam.
    """

    body = await analyze_contact(request, email_inquiry, ai_client)

    await email_client.send_email(
        subject=email_inquiry.subject,
        body=body,
        reply_to=email_inquiry.email,
        is_html=True,
    )
    contact_analysis = await confirmation_message(email_inquiry, ai_client, email_sent=True)
    return ORJSONResponse(content=contact_analysis.model_dump())

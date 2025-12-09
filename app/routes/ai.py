from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import ORJSONResponse
from starlette.responses import Response

from app.clients.ai_client import AiClient
from app.clients.email_client import EmailClient
from app.configs import file_logger
from app.decorators import cached, timed
from app.managers import cache_manager, limiter
from app.schemas.ai.chatbot import ChatRequest, ChatResponse
from app.schemas.ai.itinerary import (
    ItineraryRequest,
    ItineraryResult,
)
from app.schemas.email import ContactAnalysisResponse, EmailInquiry
from app.services.chatbot import chat_with_ai
from app.services.email_inquiry import analyze_contact, confirmation_message
from app.services.itinerary import generate_itinerary

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_client_state(request: Request) -> AiClient:
    return request.app.state.ai_client


AiDep = Annotated[AiClient, Depends(get_ai_client_state)]


def get_email_client() -> EmailClient:
    return EmailClient()


EmailDep = Annotated[EmailClient, Depends(get_email_client)]


def itinerary_key_builder(itinerary_req: ItineraryRequest) -> str:
    duration = itinerary_req.duration
    interests = ", ".join(itinerary_req.interests)
    budget = itinerary_req.budget
    return f"itinerary_{duration}_{interests}_{budget}"


@router.post(
    "/chat",
    response_class=ORJSONResponse,
    summary="Chat to agent",
    response_model=ChatResponse,
)
@timed("/ai/chat")
@limiter.limit("10/minute")
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
    summary="Send a travel inquiry email",
    response_model=ContactAnalysisResponse,
)
@timed("/ai/email-inquiry")
@limiter.limit("5/hour")
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


@router.post(
    "/itinerary",
    response_class=ORJSONResponse,
    summary="Generate an itinerary",
    response_model=ItineraryResult,
)
@timed("/ai/itinerary")
# @limiter.limit("5/hour")
@cached(
    cache_manager,
    ttl=3600,
    key_builder=lambda itinerary_req, **kw: itinerary_key_builder(itinerary_req),
    namespace="itinerary",
    response_model=ItineraryResult,
)
async def itinerary(
    request: Request,
    response: Response,
    itinerary_req: ItineraryRequest,
    # user: User = Depends(get_current_user), # auth logic
    ai_client: AiDep,
) -> ORJSONResponse:
    """
    Generate an itinerary based on the itinerary request.

    Rate Limited: 5 requests per hour for fair usage.
    """
    itinerary = await generate_itinerary(request, itinerary_req, ai_client)
    return ORJSONResponse(content=itinerary.model_dump())

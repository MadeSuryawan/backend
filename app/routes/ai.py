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
    ItineraryMD,
    ItineraryRequestMD,
    ItineraryRequestTXT,
    ItineraryTXT,
)
from app.schemas.email import ContactAnalysisResponse, EmailInquiry
from app.services.chatbot import chat_with_ai
from app.services.email_inquiry import analyze_contact, confirmation_message
from app.services.itinerary import ai_convert_txt, generate_itinerary

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/ai", tags=["ai"])


def get_ai_client_state(request: Request) -> AiClient:
    return request.app.state.ai_client


AiDep = Annotated[AiClient, Depends(get_ai_client_state)]


def get_email_client() -> EmailClient:
    return EmailClient()


EmailDep = Annotated[EmailClient, Depends(get_email_client)]


def itinerary_md_key(itinerary_req: ItineraryRequestMD) -> str:
    duration = itinerary_req.duration
    interests = ", ".join(itinerary_req.interests)
    budget = itinerary_req.budget
    return f"itinerary_{duration}_{interests}_{budget}"


def itinerary_txt_key(itinerary_req: ItineraryRequestTXT) -> str:
    user_name = itinerary_req.user_name
    md_id = itinerary_req.md_id
    return f"itinerary_{user_name}_{md_id}"


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
    "/itinerary-md",
    summary="Generate an itinerary",
    response_model=ItineraryMD,
    response_class=ORJSONResponse,
)
@timed("/ai/itinerary-md")
@limiter.limit("5/hour")
@cached(
    cache_manager,
    ttl=3600,
    key_builder=lambda itinerary_req, **kw: itinerary_md_key(itinerary_req),
    namespace="itinerary-md",
    response_model=ItineraryMD,
)
async def itinerary(
    request: Request,
    response: Response,
    itinerary_req: ItineraryRequestMD,
    # user: User = Depends(get_current_user), # auth logic
    ai_client: AiDep,
) -> ItineraryMD:
    """
    Generate an itinerary based on the itinerary request.

    Rate Limited: 5 requests per hour for fair usage.
    """
    return await generate_itinerary(request, itinerary_req, ai_client)


# this endpoint needs database implementation.
@router.post(
    "/itinerary-txt",
    response_class=ORJSONResponse,
    summary="Generate an itinerary",
    response_model=ItineraryTXT,
    include_in_schema=False,  # False for now, needs database implementation.
)
@timed("/ai/itinerary-txt")
@limiter.limit("5/hour")
@cached(
    cache_manager,
    ttl=3600,
    key_builder=lambda itinerary_md, **kw: itinerary_md_key(itinerary_md),
    namespace="itinerary-txt",
    response_model=ItineraryTXT,
)
async def itinerary_txt(
    request: Request,
    response: Response,
    itinerary_md: ItineraryRequestTXT,
    # user: User = Depends(get_current_user), # auth logic
    ai_client: AiDep,
) -> ItineraryTXT:
    """
    Convert an itinerary markdown to a text file.

    Rate Limited: 5 requests per hour for fair usage.

    """
    return await ai_convert_txt(request, itinerary_md, ai_client)

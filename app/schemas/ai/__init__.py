# app/schemas/ai/__init__.py

from app.schemas.ai.chatbot import ChatMessage, ChatRequest, ChatResponse
from app.schemas.ai.email import AnalysisFormat, ContactAnalysisResponse, EmailInquiry
from app.schemas.ai.itinerary import (
    ItineraryMD,
    ItineraryRequestMD,
    ItineraryRequestTXT,
    ItineraryTXT,
)

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "AnalysisFormat",
    "ContactAnalysisResponse",
    "EmailInquiry",
    "ItineraryMD",
    "ItineraryRequestMD",
    "ItineraryRequestTXT",
    "ItineraryTXT",
]

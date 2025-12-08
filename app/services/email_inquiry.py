from logging import getLogger
from typing import cast

from fastapi import Request
from pydantic import ValidationError

from app.clients.ai_client import AiClient
from app.configs import file_logger
from app.schemas.email import AnalysisFormat, ContactAnalysisResponse, EmailInquiry

logger = file_logger(getLogger(__name__))


def contact_analysis_prompt(name: str, message: str) -> str:
    """
    Create a prompt for contact inquiry analysis.

    Args: message: The contact message to analyze.

    Returns: A formatted prompt string for analysis.
    """

    return f"""
            Analyze the following customer inquiry for a Bali travel service company.
            Provide a structured analysis in JSON format.

            **Customer Message:** "{message}"

            Please analyze and provide:
            1. **Name**: {name}
            2. **Summary**: A brief 1-3 sentence summary of the inquiry
            3. **Category**: Classify into one of these categories:
            - "Booking Inquiry" - Questions about reservations, availability
            - "Itinerary Planning" - Requests for travel planning assistance
            - "General Information" - Questions about Bali, services, policies
            - "Support Request" - Issues, complaints, or assistance needed
            - "Pricing Inquiry" - Questions about costs, packages, pricing
            - "Feedback" - Reviews, testimonials, suggestions

            4. **Urgency**: Rate as "High", "Medium", or "Low"
            5. **Suggested Response**: A professional, helpful response template
            6. **Required Action**: What the team should do next
            7. **Keywords**: Key topics mentioned in the {message}

            Respond ONLY with a valid JSON object in this exact format:
            {{
                "name": {name},
                "summary": "Brief summary here",
                "category": "Category name",
                "urgency": "Urgency level",
                "suggested_reply": "Professional response template",
                "required_action": "Next steps for the team",
                "keywords": ["keyword1", "keyword2", "keyword3"]
            }}
            """


async def analyze_contact(
    request: Request,
    email_inquiry: EmailInquiry,
    ai_client: AiClient,
) -> str:
    """
    Analyze contact inquiry using Google Gemini AI.

    Args:
        request: The contact inquiry request containing name, email, and message.
        email_inquiry: The contact inquiry request containing name, email, and message.
        ai_client: The AI client instance.

    Returns:
        AI-generated analysis of the contact inquiry.

    """
    host = request.client.host if request.client else "unknown"
    logger.info(f"Analyzing email inquiry for {email_inquiry.name} from ip {host}")
    content = contact_analysis_prompt(email_inquiry.name, email_inquiry.message)
    system_prompt = "You are a travel assistant for Bali travel service company."
    response = await ai_client.do_service(content, system_prompt, AnalysisFormat)
    response = cast(AnalysisFormat, response)
    try:
        analysis = AnalysisFormat.model_validate(response, from_attributes=True)
        return create_body(email_inquiry, analysis)

    except ValidationError:
        logger.warning("Contact inquiry analysis validation failed, using default AnalysisFormat")
        return create_body(email_inquiry, AnalysisFormat(name=email_inquiry.name))


def create_body(request: EmailInquiry, analysis: AnalysisFormat) -> str:
    """Create a body for the email."""
    return f"""
    <div style="font-family: sans-serif; line-height: 1.6;">
      <h2>New BaliBlissed Inquiry</h2>
      <p><strong>Name:</strong> {request.name}</p>
      <p><strong>Email:</strong> <a href="mailto:{request.email}">{request.email}</a></p>
      <hr>
      <h3>Message:</h3>
      <p style="white-space: pre-wrap;">{request.message}</p>
      <hr>
      <h3>AI Analysis:</h3>
      <ul>
        <li><strong>Summary:</strong> {analysis.summary}</li>
        <li><strong>Category:</strong> {analysis.category}</li>
        <li><strong>Urgency:</strong> {analysis.urgency}</li>
        <li><strong>Suggested Reply:</strong> {analysis.suggested_reply}</li>
        <li><strong>Required Action:</strong> {analysis.required_action}</li>
        <li><strong>Keywords:</strong> {analysis.keywords}</li>
      </ul>
    </div>
    """


async def confirmation_message(
    request: EmailInquiry,
    ai_client: AiClient,
    *,
    email_sent: bool,
) -> ContactAnalysisResponse:
    """
    Create a confirmation message for the contact inquiry.

    Args:
        request: The contact inquiry request containing name, email, and message.
        ai_client: The AI client instance.
        email_sent: Whether the email was sent successfully.

    Returns:
        A confirmation message for the contact inquiry.
    """
    content = confirmation_message_prompt(request, email_sent=email_sent)
    system_prompt = "You are a travel assistant for Bali travel service company."
    response = await ai_client.do_service(content, system_prompt, ContactAnalysisResponse)
    response = cast(ContactAnalysisResponse, response)
    return response


def confirmation_message_prompt(
    request: EmailInquiry,
    *,
    email_sent: bool,
) -> str:
    """Generate confirmation message for contact inquiry."""

    return f"""
            You are a friendly customer service assistant for a Bali travel agency called BaliBlissed.
    A user has submitted a contact inquiry. Your only job is to generate a confirmation message based on whether their email was sent successfully.

    User's Name: {request.name}
    User's Email: {request.email}

    #if {email_sent}
    The email was sent successfully. Generate a brief, friendly, and reassuring confirmation message. Acknowledge the user by name and mention that we will get back to them at their provided email address within 24-48 hours.
    #else
    The email failed to send due to a technical issue. Politely inform the user that there was a problem and ask them to try again later.
    #endif

    Do not repeat the user's message in your response. Just provide the confirmation message.
    Respond ONLY with a valid JSON object in this exact format:
    {{
        "confirmation": "Brief confirmation message here"
    }}
    """

# app/routes/email.py
"""
Email Routes.

Endpoints to send support emails and queue background email tasks.

Rate Limiting
-------------
All endpoints include explicit rate limits and `429` responses.
"""

from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Request, Response
from fastapi.responses import ORJSONResponse

from app.clients import EmailClient
from app.configs import file_logger
from app.decorators import timed
from app.managers import limiter
from app.schemas import EmailInquiry, EmailResponse

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/email", tags=["✉️ Email"])


def get_email_client() -> EmailClient:
    return EmailClient()


EmailDep = Annotated[EmailClient, Depends(get_email_client)]


# --- Routes ---
@router.post(
    "/contact-support/",
    response_model=EmailResponse,
    summary="Send a support email",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Email sent successfully"},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="email_contact_support",
)
@timed("/email/contact-support")
@limiter.limit("5/hour")
async def contact_support(
    request: Request,
    response: Response,
    email_req: Annotated[
        EmailInquiry,
        Body(
            examples={
                "basic": {
                    "summary": "Support request",
                    "value": {
                        "name": "John Doe",
                        "subject": "Travel Inquiry",
                        "message": "I need help with my booking.",
                        "email": "jhondoe@gmail.com",
                    },
                },
            },
        ),
    ],
    client: EmailDep,
) -> ORJSONResponse:
    """
    Send a support email.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    email_req : EmailInquiry
        Support email payload.
    client : EmailClient
        Email client dependency.

    Returns
    -------
    ORJSONResponse
        Standard success payload.

    Notes
    -----
    Rate limited to 5 requests per hour.

    Examples
    --------
    Request
        POST /email/contact-support/
        Body: {"name": "John Doe", "subject": "Travel Inquiry", "message": "...", "email": "jhondoe@gmail.com"}
    Response
        200 OK
        {"status": "success", "message": "Email sent successfully"}

    Response schema
    ---------------
    {
      "status": str,
      "message": str
    }
    """
    # No try/except block needed here!
    # If send_email fails, the @app.exception_handler above catches it automatically.
    await client.send_email(
        subject=f"Support Request: {email_req.subject}",
        body=email_req.message,
        reply_to=email_req.email,
    )
    return ORJSONResponse(content=EmailResponse().model_dump())


@router.post(
    "/contact-background/",
    response_model=EmailResponse,
    summary="Queue an email in the background",
    response_class=ORJSONResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {"status": "success", "message": "Email queued for sending."},
                },
            },
        },
        429: {
            "description": "Rate limit exceeded",
            "content": {"application/json": {"example": {"detail": "Too Many Requests"}}},
        },
    },
    operation_id="email_contact_background",
)
@timed("/email/contact-background")
@limiter.limit("20/minute")
async def contact_background(
    request: Request,
    response: Response,
    email_req: Annotated[
        EmailInquiry,
        Body(
            examples={
                "basic": {
                    "summary": "Background email",
                    "value": {
                        "name": "John Doe",
                        "subject": "Background",
                        "message": "Please process this in background.",
                        "email": "jhondoe@gmail.com",
                    },
                },
            },
        ),
    ],
    background_tasks: BackgroundTasks,
    client: EmailDep,
) -> ORJSONResponse:
    """
    Queue an email in the background.

    Parameters
    ----------
    request : Request
        Current request context.
    response : Response
        Current response context.
    email_req : EmailInquiry
        Background email payload.
    background_tasks : BackgroundTasks
        Background task manager.
    client : EmailClient
        Email client dependency.

    Returns
    -------
    ORJSONResponse
        Standard success payload with queued message.

    Notes
    -----
    Rate limited to 20 requests per minute.

    Examples
    --------
    Request
        POST /email/contact-background/
        Body: {"name": "John Doe", "subject": "Background", "message": "...", "email": "jhondoe@gmail.com"}
    Response
        200 OK
        {"status": "success", "message": "Email queued for sending."}

    Response schema
    ---------------
    {
      "status": str,
      "message": str
    }
    """
    # Background tasks handle their own exceptions internally (logging them),
    # but we can't catch them here once the response is returned.
    background_tasks.add_task(
        client.send_email,
        subject=f"Background Request: {email_req.subject}",
        body=email_req.message,
        reply_to=email_req.email,
    )
    response_data = EmailResponse(message="Email queued for sending.")
    return ORJSONResponse(content=response_data.model_dump())

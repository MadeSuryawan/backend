# app/routes/email.py
from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import ORJSONResponse

from app.clients import EmailClient
from app.configs import file_logger
from app.decorators import timed
from app.managers import limiter
from app.schemas import EmailRequest, EmailResponse

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/email", tags=["email"])


# --- Dependency Injection ---
email_client_instance = EmailClient()


def get_email_client() -> EmailClient:
    return email_client_instance


EmailDep = Annotated[EmailClient, Depends(get_email_client)]


# --- Routes ---
@router.post(
    "/contact-support/",
    response_model=EmailResponse,
    summary="Send a support email",
    response_class=ORJSONResponse,
)
@timed("/email/contact-support")
@limiter.limit("5/hour")
async def contact_support(
    request: Request,
    response: Response,
    email_req: EmailRequest,
    client: EmailDep,
) -> ORJSONResponse:
    """
    Send a support email.

    Rate Limited: 5 requests per hour to prevent spam.
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
)
@timed("/email/contact-background")
@limiter.limit("20/minute")
async def contact_background(
    request: Request,
    response: Response,
    email_req: EmailRequest,
    background_tasks: BackgroundTasks,
    client: EmailDep,
) -> ORJSONResponse:
    """
    Queue an email in the background.

    Rate Limited: 20 requests per minute.
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

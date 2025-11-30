from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import ORJSONResponse

from app.clients import EmailClient
from app.configs import file_logger
from app.schemas import EmailRequest, EmailResponse

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/email", tags=["email"])


# --- Dependency Injection ---
email_client_instance = EmailClient()


def get_email_client() -> EmailClient:
    return email_client_instance


# --- Routes ---
@router.post("/contact-support/", response_model=EmailResponse)
async def contact_support(
    email_req: EmailRequest,
    client: Annotated[EmailClient, Depends(get_email_client)],
) -> ORJSONResponse:
    # No try/except block needed here!
    # If send_email fails, the @app.exception_handler above catches it automatically.
    await client.send_email(
        subject=f"Support Request: {email_req.subject}",
        body=email_req.message,
        reply_to=email_req.email,
    )
    return ORJSONResponse(content=EmailResponse().model_dump())


@router.post("/contact-background/", response_model=EmailResponse)
async def contact_background(
    email_req: EmailRequest,
    background_tasks: BackgroundTasks,
    client: Annotated[EmailClient, Depends(get_email_client)],
) -> ORJSONResponse:
    # Background tasks handle their own exceptions internally (logging them),
    # but we can't catch them here once the response is returned.
    background_tasks.add_task(
        client.send_email,
        subject=f"Background Request: {email_req.subject}",
        body=email_req.message,
        reply_to=email_req.email,
    )
    response = EmailResponse(message="Email queued for sending.")
    return ORJSONResponse(content=response.model_dump())

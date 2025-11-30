from logging import getLogger
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends

from app.clients import EmailClient
from app.configs import file_logger
from app.schemas import EmailRequest

logger = file_logger(getLogger(__name__))

router = APIRouter(prefix="/email", tags=["email"])


# --- Dependency Injection ---
email_client_instance = EmailClient()


def get_email_client() -> EmailClient:
    return email_client_instance


# --- Routes ---
@router.post("/contact-support/")
async def contact_support(
    email_req: EmailRequest,
    client: Annotated[EmailClient, Depends(get_email_client)],
) -> dict[str, str]:
    # No try/except block needed here!
    # If send_email fails, the @app.exception_handler above catches it automatically.
    await client.send_email(
        subject=f"Support Request: {email_req.subject}",
        body=email_req.message,
        reply_to=email_req.email,
    )
    return {"status": "success", "message": "Email sent."}


@router.post("/contact-background/")
async def contact_background(
    email_req: EmailRequest,
    background_tasks: BackgroundTasks,
    client: Annotated[EmailClient, Depends(get_email_client)],
) -> dict[str, str]:
    # Background tasks handle their own exceptions internally (logging them),
    # but we can't catch them here once the response is returned.
    background_tasks.add_task(
        client.send_email,
        subject=f"Background Request: {email_req.subject}",
        body=email_req.message,
        reply_to=email_req.email,
    )
    return {"status": "success", "message": "Email queued for sending."}

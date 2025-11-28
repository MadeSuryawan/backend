from fastapi import Request
from fastapi.responses import JSONResponse


class EmailServiceError(Exception):
    """Base class for all email service related errors."""


class ConfigurationError(EmailServiceError):
    """Raised when files (secrets/tokens) are missing."""


class AuthenticationError(EmailServiceError):
    """Raised when OAuth2 token refresh fails."""


class SendingError(EmailServiceError):
    """Raised when the Google API fails to send the message."""


async def email_service_exception_handler(request: Request, exc: EmailServiceError) -> JSONResponse:
    """Catch-all for our custom email exceptions."""
    return JSONResponse(
        status_code=500,
        content={"status": "error", "detail": str(exc)},
    )


async def config_exception_handler(request: Request, exc: ConfigurationError) -> JSONResponse:
    """Specific handler for missing config/tokens."""
    return JSONResponse(
        status_code=503,  # Service Unavailable
        content={"status": "error", "detail": "Email service not configured correctly."},
    )

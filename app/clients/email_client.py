from asyncio import get_running_loop
from base64 import urlsafe_b64encode
from email.message import EmailMessage
from logging import getLogger
from threading import Lock
from typing import Any, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from app.configs import file_logger, settings
from app.errors import AuthenticationError, ConfigurationError, SendingError

logger = file_logger(getLogger(__name__))


class EmailClient:
    """
    A client to handle sending emails via the Gmail API.

    Optimized for FastAPI with async support and thread safety.
    """

    def __init__(self) -> None:
        self._credentials: Credentials | None = None
        self._service: Resource | None = None
        # Lock ensures thread-safety during service lazy-loading
        self._service_lock: Lock = Lock()

    def _get_credentials(self) -> Credentials | None:
        """
        Retrieve or refreshe OAuth2 credentials.

        Strictly for server-side use: requires existing token.json.
        """
        creds: Credentials | None = None

        if settings.GMAIL_TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(settings.GMAIL_TOKEN_FILE),
                    settings.GMAIL_SCOPES,
                )
            except ValueError as e:
                # Specific error for corrupt token file
                mssg = "Token file is corrupt."
                logger.exception(mssg)
                raise AuthenticationError(mssg) from e

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Gmail access token.")
                try:
                    creds.refresh(Request())
                except Exception as e:
                    # Catching generic Exception here because google-auth can raise various errors
                    logger.exception("Token refresh failed.")
                    mssg = "Token expired and refresh failed. Please run 'setup_token.py' locally to generate a new one."
                    raise AuthenticationError(mssg) from e
            else:
                # Specific error for missing file
                logger.exception("Token file not found or invalid.")
                mssg = (
                    f"Valid token not found at {settings.GMAIL_TOKEN_FILE}. Run 'setup_token.py'."
                )
                raise ConfigurationError(mssg)

        return creds

    @property
    def service(self) -> Resource | None:
        """Lazy-loads the Gmail API service safely across threads."""
        if self._service is None:
            with self._service_lock:  # Critical Section
                if self._service is None:  # Double-check locking
                    self._credentials = self._get_credentials()
                    self._service = build(
                        "gmail",
                        "v1",
                        credentials=self._credentials,
                        cache_discovery=False,
                    )
        return self._service if self._service else None

    def _create_message(
        self,
        subject: str,
        body: str,
        sender: str,
        to: str,
        reply_to: str,
    ) -> dict[str, str]:
        """Create a MIME message and encode it for Gmail API."""
        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["From"] = sender
        message["Subject"] = subject
        message["Reply-To"] = reply_to

        # Encode the message (URL-safe base64)
        encoded_message = urlsafe_b64encode(message.as_bytes()).decode()
        return {"raw": encoded_message}

    def send_sync(self, subject: str, body: str, reply_to: str) -> dict[str, Any]:
        """
        Blocking method to send an email.

        Should not be called directly within an async route.
        """
        try:
            message_body = self._create_message(
                subject=subject,
                body=body,
                sender=reply_to,
                to=settings.COMPANY_TARGET_EMAIL,
                reply_to=reply_to,
            )

            # Cast to Any so static analysis ignores the dynamic .users() method
            service = cast(Any, self.service)
            result = service.users().messages().send(userId="me", body=message_body).execute()

            logger.info(f"Email sent. ID: {result.get('id')}")
            return result

        except HttpError as error:
            logger.exception("Google API Error")
            mssg = f"Google API refused request: {error}"
            raise SendingError(mssg) from error
        except (ConfigurationError, AuthenticationError):
            # Let these bubble up as is
            raise
        except Exception as error:
            # Catch unexpected python errors (e.g. encoding issues)
            logger.exception("Unexpected error during sending")
            mssg = "An unexpected internal error occurred."
            raise SendingError(mssg) from error

    async def send_email(self, subject: str, body: str, reply_to: str) -> dict[str, Any]:
        """
        Asynchronous wrapper to send email without blocking the Event Loop.

        Uses a ThreadPoolExecutor.
        """
        loop = get_running_loop()
        try:
            # Run the synchronous 'send_sync' method in a separate thread
            return await loop.run_in_executor(None, self.send_sync, subject, body, reply_to)
        except Exception:
            logger.exception("Async email sending failed")
            raise

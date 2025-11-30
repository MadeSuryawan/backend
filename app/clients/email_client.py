"""Email client for Gmail API integration with OAuth2 authentication."""

from asyncio import get_running_loop
from base64 import urlsafe_b64encode
from email.message import EmailMessage
from email.utils import parseaddr
from logging import getLogger
from os import chmod
from re import compile as re_compile
from stat import S_IRUSR, S_IRWXG, S_IRWXO, S_IWUSR
from threading import Lock
from typing import Any, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError

from app.configs import file_logger, settings
from app.errors import AuthenticationError, ConfigurationError, SendingError

logger = file_logger(getLogger(__name__))

# Regex pattern for header injection prevention
_HEADER_INJECTION_PATTERN = re_compile(r"[\r\n]")


class EmailClient:
    """
    A client to handle sending emails via the Gmail API.

    Optimized for FastAPI with async support and thread safety.
    Includes security features for token file validation and email sanitization.
    """

    def __init__(self) -> None:
        """Initialize EmailClient with thread-safe lazy loading."""
        self._credentials: Credentials | None = None
        self._service: Resource | None = None
        # Lock ensures thread-safety during service lazy-loading
        self._service_lock: Lock = Lock()

    def _validate_token_file_permissions(self) -> None:
        """
        Validate and fix token file permissions for security.

        Ensures token file has secure permissions (600 on Unix systems).
        Token files contain sensitive refresh tokens that should be protected.
        """
        if not settings.GMAIL_TOKEN_FILE.exists():
            return

        try:
            mode = settings.GMAIL_TOKEN_FILE.stat().st_mode
            # Check if group or others have any permissions
            if mode & (S_IRWXG | S_IRWXO):
                logger.warning("Token file has insecure permissions, fixing to owner-only access")
                chmod(settings.GMAIL_TOKEN_FILE, S_IRUSR | S_IWUSR)
        except OSError:
            logger.exception("Failed to validate token file permissions")
            # Don't raise - this is a security enhancement, not a requirement

    def _validate_email(self, email: str) -> str:
        """
        Validate and sanitize email address.

        Args:
            email: Email address to validate.

        Returns:
            Sanitized email address.

        Raises:
            ValueError: If email is invalid or contains injection characters.
        """
        # Gmail API special value for authenticated user
        if email == "me":
            return email

        if _HEADER_INJECTION_PATTERN.search(email):
            mssg = "Email contains invalid characters (potential header injection)"
            raise ValueError(mssg)

        _, addr = parseaddr(email)
        if not addr or "@" not in addr:
            mssg = f"Invalid email address: {email}"
            raise ValueError(mssg)

        return addr

    def _sanitize_header(self, value: str) -> str:
        """
        Sanitize header values to prevent email header injection attacks.

        Args:
            value: Header value to sanitize.

        Returns:
            Sanitized header value with newlines removed.
        """
        return _HEADER_INJECTION_PATTERN.sub("", value)

    def _get_credentials(self) -> Credentials:
        """
        Retrieve or refresh OAuth2 credentials.

        Strictly for server-side use: requires existing token.json.

        Returns:
            Valid OAuth2 credentials.

        Raises:
            AuthenticationError: If token is corrupt or refresh fails.
            ConfigurationError: If token file is missing.
        """
        # Validate token file permissions before reading
        self._validate_token_file_permissions()

        creds: Credentials | None = None

        if settings.GMAIL_TOKEN_FILE.exists():
            try:
                creds = Credentials.from_authorized_user_file(
                    str(settings.GMAIL_TOKEN_FILE),
                    settings.GMAIL_SCOPES,
                )
            except ValueError as e:
                mssg = "Token file is corrupt."
                logger.exception(mssg)
                raise AuthenticationError(mssg) from e

        if creds is None:
            logger.error("Token file not found or invalid.")
            mssg = f"Valid token not found at {settings.GMAIL_TOKEN_FILE}. Run 'setup_token.py'."
            raise ConfigurationError(mssg)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Gmail access token.")
                try:
                    creds.refresh(Request())
                except Exception as e:
                    # google-auth can raise various errors
                    logger.exception("Token refresh failed.")
                    mssg = (
                        "Token expired and refresh failed. "
                        "Please run 'setup_token.py' locally to generate a new one."
                    )
                    raise AuthenticationError(mssg) from e
            else:
                logger.error("Token is invalid and cannot be refreshed.")
                mssg = (
                    f"Valid token not found at {settings.GMAIL_TOKEN_FILE}. Run 'setup_token.py'."
                )
                raise ConfigurationError(mssg)

        return creds

    @property
    def service(self) -> Resource:
        """
        Lazy-loads the Gmail API service safely across threads.

        Uses double-check locking pattern for thread-safe initialization.

        Returns:
            Gmail API service resource.

        Raises:
            ConfigurationError: If service cannot be initialized.
        """
        if self._service is None:
            with self._service_lock:
                if self._service is None:
                    self._credentials = self._get_credentials()
                    self._service = build(
                        "gmail",
                        "v1",
                        credentials=self._credentials,
                        cache_discovery=False,
                    )
        if self._service is None:
            mssg = "Failed to initialize Gmail service"
            raise ConfigurationError(mssg)
        return self._service

    def _create_message(
        self,
        subject: str,
        body: str,
        sender: str,
        to: str,
        reply_to: str,
    ) -> dict[str, str]:
        """
        Create a MIME message and encode it for Gmail API.

        All header values are sanitized to prevent header injection attacks.

        Args:
            subject: Email subject.
            body: Email body content.
            sender: Sender email address.
            to: Recipient email address.
            reply_to: Reply-to email address.

        Returns:
            Dictionary with base64-encoded message.

        Raises:
            ValueError: If email addresses are invalid.
        """
        # Validate and sanitize all email addresses
        validated_to = self._validate_email(to)
        validated_sender = self._validate_email(sender)
        validated_reply_to = self._validate_email(reply_to)

        # Sanitize headers to prevent injection
        sanitized_subject = self._sanitize_header(subject)

        message = EmailMessage()
        message.set_content(body)
        message["To"] = validated_to
        message["From"] = validated_sender
        message["Subject"] = sanitized_subject
        message["Reply-To"] = validated_reply_to

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

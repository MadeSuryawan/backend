from starlette.status import HTTP_417_EXPECTATION_FAILED

from app.errors import BaseAppError, create_exception_handler
from app.monitoring import get_logger

logger = get_logger(__name__)


class PasswordHashingError(BaseAppError):
    """Base error for password hasher module."""

    def __init__(
        self,
        detail: str = "We couldn't process your password. Please try again or use a different password.",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = HTTP_417_EXPECTATION_FAILED


class PasswordRehashError(PasswordHashingError):
    """Error for password rehashing."""

    def __init__(
        self,
        detail: str = "We encountered an issue with your password. Please try signing in again.",
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = HTTP_417_EXPECTATION_FAILED


password_hashing_exception_handler = create_exception_handler(logger)

from logging import getLogger

from starlette.status import HTTP_417_EXPECTATION_FAILED

from app.errors import BaseAppError, create_exception_handler
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


class PasswordHashingError(BaseAppError):
    """Base error for password hasher module."""

    def __init__(self, detail: str = "Password hashing failed") -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = HTTP_417_EXPECTATION_FAILED


class PasswordRehashError(PasswordHashingError):
    """Error for password rehashing."""

    def __init__(self, detail: str = "Password rehashing failed") -> None:
        super().__init__(detail)
        self.detail = detail
        self.error_code = HTTP_417_EXPECTATION_FAILED


password_hashing_exception_handler = create_exception_handler(logger)

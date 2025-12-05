from logging import getLogger

from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

from app.configs import file_logger
from app.errors.base import BaseAppError, create_exception_handler

logger = file_logger(getLogger(__name__))


class DatabaseError(BaseAppError):
    """Base exception for database errors."""

    def __init__(
        self,
        detail: str = "Database Error",
        status_code: int = HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        super().__init__(detail, status_code)


class DatabaseConnectionError(DatabaseError):
    """Exception raised when database connection fails."""

    def __init__(
        self,
        detail: str = "Failed to connect to the database",
    ) -> None:
        super().__init__(detail, HTTP_500_INTERNAL_SERVER_ERROR)


class DatabaseConfigurationError(DatabaseError):
    """Exception raised when database configuration is invalid."""

    def __init__(
        self,
        detail: str = "Invalid database configuration",
    ) -> None:
        super().__init__(detail, HTTP_500_INTERNAL_SERVER_ERROR)


class DatabaseInitializationError(DatabaseError):
    """Exception raised when database initialization fails."""

    def __init__(
        self,
        detail: str = "Failed to initialize database",
    ) -> None:
        super().__init__(detail, HTTP_500_INTERNAL_SERVER_ERROR)


database_exception_handler = create_exception_handler(logger)

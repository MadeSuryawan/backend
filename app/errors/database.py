import re
from logging import getLogger

from starlette.status import (
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)

from app.errors.base import BaseAppError, create_exception_handler
from app.utils.helpers import file_logger

logger = file_logger(getLogger(__name__))


def parse_unique_violation(error_msg: str) -> str:
    """
    Parse PostgreSQL unique violation error message to a user-friendly format.

    Extracts the field name and value from the DETAIL part of the error message.

    Example:
    Input: "Key (email)=(johndoe@gmail.com) already exists."
    Output: "User with email 'johndoe@gmail.com' already exists"

    Args:
        error_msg: The raw error message from the database driver.

    Returns:
        str: A formatted, user-friendly error message or the original message if parsing fails.
    """
    # Regex to match the DETAIL pattern in PostgreSQL unique violation errors
    # Pattern: Key (field_name)=(value) already exists.
    pattern = r"Key \((?P<field>.*)\)=\((?P<value>.*)\) already exists"
    match = re.search(pattern, error_msg)

    if match:
        field = match.group("field")
        value = match.group("value")
        return f"User with {field} '{value}' already exists"

    return error_msg


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


class DuplicateEntryError(DatabaseError):
    """Exception raised when attempting to create a duplicate entry."""

    def __init__(
        self,
        detail: str = "A record with this value already exists",
    ) -> None:
        super().__init__(detail, HTTP_409_CONFLICT)


class RecordNotFoundError(DatabaseError):
    """Exception raised when a record is not found."""

    def __init__(
        self,
        detail: str = "Record not found",
    ) -> None:
        super().__init__(detail, HTTP_404_NOT_FOUND)


class TransactionError(DatabaseError):
    """Exception raised when a transaction fails."""

    def __init__(
        self,
        detail: str = "Transaction failed",
    ) -> None:
        super().__init__(detail, HTTP_500_INTERNAL_SERVER_ERROR)


database_exception_handler = create_exception_handler(logger)

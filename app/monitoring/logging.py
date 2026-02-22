"""
Structured logging with PII sanitization.

This module provides secure, structured logging using structlog with:
- JSON output for production (for Datadog/CloudWatch compatibility)
- Pretty console output for development
- Automatic PII redaction
- OpenTelemetry trace context injection
- Request ID correlation

Security
--------
Sensitive fields are automatically redacted from logs:
- Authorization headers
- Cookie values
- API keys
- Email addresses (pattern detection)
- Passwords/tokens

Examples
--------
>>> from app.monitoring import get_logger
>>> logger = get_logger("my_module")
>>> logger.info("User action", user_id="123", action="login")
"""

from logging import INFO, Filter, LogRecord, StreamHandler, root
from logging.handlers import RotatingFileHandler
from pathlib import Path as SyncPath
from re import Pattern
from re import compile as re_compile
from typing import Any

from opentelemetry.trace import get_current_span
from structlog import configure
from structlog import get_logger as struct_logger
from structlog.contextvars import (
    bind_contextvars,
    clear_contextvars,
    get_contextvars,
    merge_contextvars,
)
from structlog.dev import ConsoleRenderer, RichTracebackFormatter
from structlog.processors import (
    JSONRenderer,
    StackInfoRenderer,
    UnicodeDecoder,
    add_log_level,
    format_exc_info,
)
from structlog.processors import (
    json as struct_json,
)
from structlog.stdlib import (
    BoundLogger,
    ExtraAdder,
    LoggerFactory,
    PositionalArgumentsFormatter,
    ProcessorFormatter,
    add_logger_name,
    filter_by_level,
)
from structlog.types import EventDict, Processor, WrappedLogger

from app.configs.settings import settings
from app.utils.helpers import today_str

# install()

# Sensitive headers to redact
SENSITIVE_HEADERS: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "x-api-key",
        "proxy-authorization",
        "x-csrf-token",
        "x-xsrf-token",
    },
)

# Patterns for detecting PII in log messages
# Order matters: more specific patterns should come before general ones
PII_PATTERNS: list[tuple[Pattern, str]] = [
    # JWT tokens (base64url format) - check first as they contain dots
    (re_compile(r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*"), "[REDACTED_JWT]"),
    # Email addresses
    (re_compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[REDACTED_EMAIL]"),
    # Credit card numbers (basic pattern) - check before phone
    (re_compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[REDACTED_CC]"),
    # SSN patterns - check before phone
    (re_compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    # Phone numbers (basic international format) - check last
    (re_compile(r"\+?[1-9]\d{1,14}"), "[REDACTED_PHONE]"),
]

# Characters to sanitize to prevent log injection
CONTROL_CHARS = str.maketrans({"\n": "\\n", "\r": "\\r", "\t": "\\t", "\x00": ""})


def sanitize_log_message(message: str) -> str:
    r"""
    Remove control characters and sanitize log messages.

    Args:
        message: Raw log message that might contain injection attempts.

    Returns:
        Sanitized message with control characters escaped or removed.

    Examples:
    --------
    >>> sanitize_log_message("Hello\nWorld")
    'Hello\\nWorld'
    """
    return message.translate(CONTROL_CHARS)


def sanitize_headers(headers: dict[str, Any]) -> dict[str, Any]:
    """
    Return headers with sensitive values redacted.

    Args:
        headers: Dictionary of HTTP headers.

    Returns:
        Headers dictionary with sensitive values replaced.

    Examples:
    --------
    >>> sanitize_headers({"Authorization": "Bearer token123", "Content-Type": "json"})
    {'Authorization': '[REDACTED]', 'Content-Type': 'json'}
    """
    return {k: "[REDACTED]" if k.lower() in SENSITIVE_HEADERS else v for k, v in headers.items()}


def redact_pii(message: str) -> str:
    """
    Redact PII patterns from log messages.

    Args:
        message: Log message potentially containing PII.

    Returns:
        Message with PII patterns replaced.

    Examples:
    --------
    >>> redact_pii("User user@example.com logged in")
    'User [REDACTED_EMAIL] logged in'
    """
    for pattern, replacement in PII_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


def add_timestamp(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Add ISO format timestamp to log entry.

    Args:
        logger: The wrapped logger instance.
        method_name: The name of the logging method being called.
        event_dict: The event dictionary being built.

    Returns:
        Updated event dictionary with timestamp.
    """
    event_dict["timestamp"] = today_str()
    return event_dict


def add_trace_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Add OpenTelemetry trace context to log entry.

    Args:
        logger: The wrapped logger instance.
        method_name: The name of the logging method being called.
        event_dict: The event dictionary being built.

    Returns:
        Updated event dictionary with trace context.
    """
    try:
        current_span = get_current_span()
        if current_span:
            context = current_span.get_span_context()
            if context.is_valid:
                event_dict["trace_id"] = format(context.trace_id, "032x")
                event_dict["span_id"] = format(context.span_id, "016x")
    except ImportError:
        pass  # OpenTelemetry not available
    return event_dict


def sanitize_event_dict(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Sanitize the event dictionary for PII and injection.

    Args:
        logger: The wrapped logger instance.
        method_name: The name of the logging method being called.
        event_dict: The event dictionary being built.

    Returns:
        Sanitized event dictionary.
    """
    # Sanitize the main event message
    if "event" in event_dict and isinstance(event_dict["event"], str):
        event_dict["event"] = redact_pii(sanitize_log_message(event_dict["event"]))

    # Sanitize any string values in the dict
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = redact_pii(sanitize_log_message(value))
        elif key.lower() == "headers" and isinstance(value, dict):
            event_dict[key] = sanitize_headers(value)

    return event_dict


def get_processors(*, colors: bool = True) -> list[Processor]:
    """
    Get the list of structlog processors based on environment.

    Args:
        colors: Whether to enable colors in ConsoleRenderer.

    Returns:
        List of processors for structlog configuration.
    """
    processors: list[Processor] = [
        filter_by_level,
        merge_contextvars,
        add_log_level,
        add_timestamp,
        add_trace_context,
        sanitize_event_dict,
    ]

    # Add environment-specific processors
    if settings.ENVIRONMENT == "development":
        # Pretty console output for development
        processors.extend(
            [
                ExtraAdder(),
                ConsoleRenderer(
                    colors=colors,
                    pad_level=False,
                    exception_formatter=RichTracebackFormatter(),
                ),
            ],
        )
    else:
        # JSON output for production (Datadog/CloudWatch)
        processors.extend(
            [
                ExtraAdder(),
                JSONRenderer(serializer=struct_json.dumps),
            ],
        )

    return processors


def configure_logging() -> None:
    """Configure structured logging for the application."""
    # Clear any existing root handlers to prevent duplicates
    # (Important when using hot-reloading)
    root.handlers.clear()

    # Configure standard library logging level
    root.setLevel(settings.LOG_LEVEL.upper())

    # Configure structlog
    configure(
        processors=[
            filter_by_level,
            merge_contextvars,
            add_logger_name,
            add_log_level,
            PositionalArgumentsFormatter(),
            StackInfoRenderer(),
            format_exc_info,
            UnicodeDecoder(),
            ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=LoggerFactory(),
        wrapper_class=BoundLogger,
        cache_logger_on_first_use=True,
    )

    console_handler = StreamHandler()
    console_formatter = ProcessorFormatter(
        # Use last processor (ConsoleRenderer) with colors enabled
        processor=get_processors(colors=True)[-1],
        foreign_pre_chain=[
            add_log_level,
            add_timestamp,
            add_trace_context,
        ],
    )
    console_handler.setFormatter(console_formatter)
    root.addHandler(console_handler)
    configure_file_logging()


def configure_file_logging() -> None:
    """Configure file logging for the application."""
    # Centralized File Handler (if enabled, NO colors)
    if settings.LOG_TO_FILE:
        log_file = SyncPath(settings.LOG_FILE)
        log_file.parent.mkdir(exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
        )
        file_handler.setLevel(INFO)

        # # Apply generic Metadata-Driven Filter
        # if settings.LOG_EXCLUSIONS:
        #     file_handler.addFilter(LogKeyFilter(settings.LOG_EXCLUSIONS))

        # File formatter (colors disabled for clean text log)
        file_formatter = ProcessorFormatter(
            processor=get_processors(colors=False)[-1],
            foreign_pre_chain=[
                add_log_level,
                add_timestamp,
                add_trace_context,
            ],
        )
        file_handler.setFormatter(file_formatter)
        root.addHandler(file_handler)


def get_logger(name: str) -> BoundLogger:
    """
    Get a structured logger instance.

    Args:
        name: The name of the logger (typically __name__).

    Returns:
        Configured structlog BoundLogger instance.

    Examples:
    --------
    >>> logger = get_logger("app.routes.users")
    >>> logger.info("User created", user_id="123")
    """
    return struct_logger(name)


def bind_request_id(request_id: str) -> None:
    """
    Bind request ID to the current logging context.

    Args:
        request_id: Unique identifier for the current request.

    Examples:
    --------
    >>> bind_request_id("abc-123")
    >>> logger.info("Processing request")  # Will include request_id
    """
    bind_contextvars(request_id=request_id)


def clear_context() -> None:
    """
    Clear all bound context variables.

    Examples
    --------
    >>> clear_context()
    """
    clear_contextvars()


class RequestIdFilter(Filter):
    """
    Filter to inject request_id into log records.

    This filter ensures the request_id is available in all log records
    within a request context.
    """

    def filter(self, record: LogRecord) -> bool:
        """
        Add request_id to the log record if available.

        Args:
            record: The log record being processed.

        Returns:
            True to allow the record through.
        """
        try:
            context = get_contextvars()
            record.request_id = context.get("request_id", "N/A")
        except (SystemError, RuntimeError, ValueError):
            record.request_id = "N/A"
        return True

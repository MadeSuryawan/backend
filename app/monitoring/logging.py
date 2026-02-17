"""
Structured logging configuration for BaliBlissed Backend.

This module provides structured logging using structlog with:
- JSON output for production (compatible with log aggregators)
- Pretty console output for development
- PII sanitization to prevent sensitive data leakage
- OpenTelemetry trace context injection for log-trace correlation
- Request ID (correlation ID) in every log entry

Security:
    - Automatic redaction of sensitive headers (Authorization, Cookie, etc.)
    - PII detection and redaction (emails, phone numbers, etc.)
    - Log injection prevention via message sanitization
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from logging import getLogger
from typing import Any

import orjson
import structlog
from structlog.contextvars import merge_contextvars
from structlog.processors import CallsiteParameter
from structlog.types import EventDict, Processor, WrappedLogger

from app.configs import settings

logger = getLogger(__name__)

# --- Context Variables ---
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)

# --- Constants ---
# Headers that should always be redacted
SENSITIVE_HEADERS = frozenset({
    "authorization",
    "cookie",
    "x-api-key",
    "proxy-authorization",
    "x-auth-token",
    "x-access-token",
    "x-refresh-token",
    "set-cookie",
})

# Fields that should be redacted in log events
SENSITIVE_FIELDS = frozenset({
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "credit_card",
    "card_number",
    "cvv",
    "ssn",
    "social_security",
})

# PII patterns for detection
PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

# Control characters pattern for log injection prevention
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def get_request_id() -> str | None:
    """Get the current request ID from context."""
    return request_id_var.get()


def set_request_id(request_id: str | None) -> None:
    """Set the request ID in context."""
    request_id_var.set(request_id)


def get_user_id() -> str | None:
    """Get the current user ID from context."""
    return user_id_var.get()


def set_user_id(user_id: str | None) -> None:
    """Set the user ID in context."""
    user_id_var.set(user_id)


def get_client_ip() -> str | None:
    """Get the current client IP from context."""
    return client_ip_var.get()


def set_client_ip(client_ip: str | None) -> None:
    """Set the client IP in context."""
    client_ip_var.set(client_ip)


def sanitize_log_message(message: str) -> str:
    """
    Sanitize log message to prevent log injection attacks.

    Removes newlines, carriage returns, and control characters.

    Parameters
    ----------
    message : str
        The log message to sanitize.

    Returns
    -------
    str
        Sanitized log message.
    """
    if not isinstance(message, str):
        return str(message)

    # Replace newlines and carriage returns
    message = message.replace("\n", "\\n").replace("\r", "\\r")
    # Remove control characters
    message = CONTROL_CHARS.sub("", message)
    return message


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """
    Sanitize HTTP headers by redacting sensitive values.

    Parameters
    ----------
    headers : dict[str, str]
        The headers dictionary to sanitize.

    Returns
    -------
    dict[str, str]
        Headers with sensitive values redacted.
    """
    return {
        k: "[REDACTED]" if k.lower() in SENSITIVE_HEADERS else v
        for k, v in headers.items()
    }


def redact_pii(value: str) -> str:
    """
    Redact PII patterns from a string value.

    Parameters
    ----------
    value : str
        The string value to check for PII.

    Returns
    -------
    str
        String with PII patterns redacted.
    """
    if not isinstance(value, str):
        return value

    result = value
    for pii_type, pattern in PII_PATTERNS.items():
        if pattern.search(result):
            result = pattern.sub(f"[REDACTED_{pii_type.upper()}]", result)
    return result


def redact_sensitive_value(key: str, value: Any) -> Any:
    """
    Redact a value if its key indicates sensitive data.

    Parameters
    ----------
    key : str
        The key/field name.
    value : Any
        The value to potentially redact.

    Returns
    -------
    Any
        The value, potentially redacted.
    """
    key_lower = key.lower()

    # Check if key matches sensitive field patterns
    for sensitive in SENSITIVE_FIELDS:
        if sensitive in key_lower:
            return "[REDACTED]"

    # Check string values for PII
    if isinstance(value, str):
        return redact_pii(value)

    return value


def sanitize_event_dict(event_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively sanitize an event dictionary.

    Parameters
    ----------
    event_dict : dict[str, Any]
        The event dictionary to sanitize.

    Returns
    -------
    dict[str, Any]
        Sanitized event dictionary.
    """
    result = {}
    for key, value in event_dict.items():
        if isinstance(value, dict):
            result[key] = sanitize_event_dict(value)
        elif isinstance(value, list):
            result[key] = [
                sanitize_event_dict(item) if isinstance(item, dict) else redact_sensitive_value(key, item)
                for item in value
            ]
        else:
            result[key] = redact_sensitive_value(key, value)
    return result


# --- Structlog Processors ---


def add_request_context(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Add request context (request_id, user_id, client_ip) to log events.

    Parameters
    ----------
    _logger : WrappedLogger
        The wrapped logger instance.
    _method_name : str
        The logging method name.
    event_dict : EventDict
        The event dictionary being logged.

    Returns
    -------
    EventDict
        Event dictionary with request context added.
    """
    if request_id := get_request_id():
        event_dict["request_id"] = request_id

    if user_id := get_user_id():
        # Don't include actual user_id in logs for privacy
        # Use a hashed/truncated version or just indicate presence
        event_dict["has_user"] = True

    if client_ip := get_client_ip():
        # Optionally mask the IP for privacy
        event_dict["client_ip_masked"] = mask_ip(client_ip)

    return event_dict


def mask_ip(ip: str) -> str:
    """
    Mask an IP address for privacy.

    Parameters
    ----------
    ip : str
        The IP address to mask.

    Returns
    -------
    str
        Masked IP address (e.g., 192.168.xxx.xxx).
    """
    parts = ip.split(".")
    if len(parts) == 4:  # noqa: PLR2004
        return f"{parts[0]}.{parts[1]}.xxx.xxx"
    return "xxx.xxx.xxx.xxx"


def add_opentelemetry_context(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Add OpenTelemetry trace context to log events.

    Parameters
    ----------
    _logger : WrappedLogger
        The wrapped logger instance.
    _method_name : str
        The logging method name.
    event_dict : EventDict
        The event dictionary being logged.

    Returns
    -------
    EventDict
        Event dictionary with trace context added.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            if ctx.is_valid:
                event_dict["trace_id"] = format(ctx.trace_id, "032x")
                event_dict["span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass  # OpenTelemetry not installed
    except Exception:
        pass  # Silently fail if tracing context unavailable

    return event_dict


def pii_sanitizer(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Sanitize PII and sensitive data from log events.

    Parameters
    ----------
    _logger : WrappedLogger
        The wrapped logger instance.
    _method_name : str
        The logging method name.
    event_dict : EventDict
        The event dictionary being logged.

    Returns
    -------
    EventDict
        Sanitized event dictionary.
    """
    return sanitize_event_dict(event_dict)


def message_sanitizer(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """
    Sanitize the log message to prevent log injection.

    Parameters
    ----------
    _logger : WrappedLogger
        The wrapped logger instance.
    _method_name : str
        The logging method name.
    event_dict : EventDict
        The event dictionary being logged.

    Returns
    -------
    EventDict
        Event dictionary with sanitized message.
    """
    if "event" in event_dict:
        event_dict["event"] = sanitize_log_message(event_dict["event"])
    return event_dict


def orjson_serializer(data: Any, **_kwargs: Any) -> bytes:
    """
    Serialize log data using orjson for better performance.

    Parameters
    ----------
    data : Any
        The data to serialize.
    **_kwargs : Any
        Additional keyword arguments (ignored).

    Returns
    -------
    bytes
        JSON serialized data.
    """
    return orjson.dumps(
        data,
        option=orjson.OPT_UTC_Z | orjson.OPT_NAIVE_UTC,
    )


def orjson_dumps(data: Any, **_kwargs: Any) -> str:
    """
    Serialize log data using orjson and return as string.

    Parameters
    ----------
    data : Any
        The data to serialize.
    **_kwargs : Any
        Additional keyword arguments (ignored).

    Returns
    -------
    str
        JSON serialized string.
    """
    return orjson.dumps(
        data,
        option=orjson.OPT_UTC_Z | orjson.OPT_NAIVE_UTC,
    ).decode("utf-8")


def get_shared_processors() -> list[Processor]:
    """
    Get the shared structlog processors for both dev and production.

    Returns
    -------
    list[Processor]
        List of structlog processors.
    """
    return [
        # Add context variables
        merge_contextvars,
        # Add timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # Add log level
        structlog.stdlib.add_log_level,
        # Add logger name
        structlog.stdlib.add_logger_name,
        # Add callsite info (file, line, function)
        structlog.processors.CallsiteParameterAdder(
            parameters=[
                CallsiteParameter.FILENAME,
                CallsiteParameter.LINENO,
                CallsiteParameter.FUNC_NAME,
            ],
        ),
        # Add request context
        add_request_context,
        # Add OpenTelemetry trace context
        add_opentelemetry_context,
        # Sanitize message for log injection prevention
        message_sanitizer,
        # Sanitize PII and sensitive data
        pii_sanitizer,
        # Process exceptions
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        structlog.processors.ExceptionPrettyPrinter(),
    ]


def configure_structlog(
    is_development: bool | None = None,
    log_level: str | None = None,
) -> None:
    """
    Configure structlog for the application.

    Parameters
    ----------
    is_development : bool | None
        If True, use console renderer; if False, use JSON.
        Defaults to checking settings.ENVIRONMENT.
    log_level : str | None
        The log level to use. Defaults to settings.LOG_LEVEL.
    """
    if is_development is None:
        is_development = settings.ENVIRONMENT == "development"

    if log_level is None:
        log_level = settings.LOG_LEVEL

    shared_processors = get_shared_processors()

    if is_development:
        # Development: Pretty console output
        processors = [
            *shared_processors,
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Production: JSON output with orjson
        processors = [
            *shared_processors,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(serializer=orjson_dumps),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to work with structlog
    import logging

    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    logger.info(
        "Structlog configured",
        extra={
            "environment": "development" if is_development else "production",
            "log_level": log_level,
        },
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structlog logger instance.

    Parameters
    ----------
    name : str | None
        The logger name. If None, uses the calling module name.

    Returns
    -------
    structlog.stdlib.BoundLogger
        A configured structlog logger.
    """
    return structlog.get_logger(name)


# Type alias for the logger
Logger = structlog.stdlib.BoundLogger

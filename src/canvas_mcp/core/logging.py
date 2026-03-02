"""Structured logging for Canvas MCP Server."""

import logging
import os
import re
import sys
from typing import Any

# Configure logger for Canvas MCP
logger = logging.getLogger("canvas_mcp")
logger.setLevel(logging.INFO)

# Create console handler with formatting
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter(
    fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(handler)

# PII keys that should be fully redacted in log context
_PII_KEYS = frozenset({
    "user_id", "student_id", "email", "name", "login_id",
    "sis_user_id", "value",
})

# ID keys that should be truncated (show only last 4 chars)
_ID_KEYS = frozenset({
    "course_id", "topic_id", "assignment_id", "entry_id", "submission_id",
})

# Regex to replace numeric path segments in URLs
_NUMERIC_PATH_RE = re.compile(r"/\d+")


def _is_redaction_enabled() -> bool:
    """Check if PII redaction is enabled (default: true)."""
    return os.getenv("LOG_REDACT_PII", "true").strip().lower() == "true"


def _sanitize_context(context: dict[str, Any]) -> dict[str, Any]:
    """Sanitize context dict by redacting PII and truncating IDs.

    - Keys in _PII_KEYS are replaced with '[REDACTED]'
    - Keys in _ID_KEYS are truncated to show only last 4 characters
    - All other keys pass through unchanged
    """
    if not _is_redaction_enabled():
        return context

    sanitized: dict[str, Any] = {}
    for key, val in context.items():
        if key in _PII_KEYS:
            sanitized[key] = "[REDACTED]"
        elif key in _ID_KEYS:
            str_val = str(val)
            if len(str_val) > 4:
                sanitized[key] = f"***{str_val[-4:]}"
            else:
                sanitized[key] = str_val
        else:
            sanitized[key] = val
    return sanitized


def sanitize_url(url: str) -> str:
    """Replace numeric path segments in a URL with '***'.

    Example: /courses/12345/users/678 → /courses/***/users/***
    """
    return _NUMERIC_PATH_RE.sub("/***", url)


def log_error(message: str, exc: Exception | None = None, **context: Any) -> None:
    """Log an error with optional exception and context.

    Args:
        message: The error message
        exc: Optional exception that caused the error
        **context: Additional context information to log
    """
    if context:
        message = f"{message} | Context: {_sanitize_context(context)}"

    if exc:
        logger.error(message, exc_info=exc)
    else:
        logger.error(message)


def log_warning(message: str, **context: Any) -> None:
    """Log a warning with optional context.

    Args:
        message: The warning message
        **context: Additional context information to log
    """
    if context:
        message = f"{message} | Context: {_sanitize_context(context)}"

    logger.warning(message)


def log_info(message: str, **context: Any) -> None:
    """Log an informational message with optional context.

    Args:
        message: The info message
        **context: Additional context information to log
    """
    if context:
        message = f"{message} | Context: {_sanitize_context(context)}"

    logger.info(message)


def log_debug(message: str, **context: Any) -> None:
    """Log a debug message with optional context.

    Args:
        message: The debug message
        **context: Additional context information to log
    """
    if context:
        message = f"{message} | Context: {_sanitize_context(context)}"

    logger.debug(message)

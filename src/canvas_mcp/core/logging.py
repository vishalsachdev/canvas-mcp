"""Structured logging for Canvas MCP Server."""

import logging
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


def log_error(message: str, exc: Exception | None = None, **context: Any) -> None:
    """Log an error with optional exception and context.

    Args:
        message: The error message
        exc: Optional exception that caused the error
        **context: Additional context information to log
    """
    if context:
        message = f"{message} | Context: {context}"

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
        message = f"{message} | Context: {context}"

    logger.warning(message)


def log_info(message: str, **context: Any) -> None:
    """Log an informational message with optional context.

    Args:
        message: The info message
        **context: Additional context information to log
    """
    if context:
        message = f"{message} | Context: {context}"

    logger.info(message)


def log_debug(message: str, **context: Any) -> None:
    """Log a debug message with optional context.

    Args:
        message: The debug message
        **context: Additional context information to log
    """
    if context:
        message = f"{message} | Context: {context}"

    logger.debug(message)

"""Per-request credential context for HTTP transport.

When the server runs in HTTP mode, each request carries its own Canvas API
credentials via headers (X-Canvas-Token, X-Canvas-URL). This module uses
Python's contextvars to thread those credentials through the async call
stack without modifying any tool signatures.

In stdio mode, the ContextVar remains unset (None), and the client falls
back to the global .env-based configuration.
"""

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True)
class RequestCredentials:
    """Canvas API credentials for a single HTTP request."""

    api_token: str
    api_url: str


_request_credentials: ContextVar[RequestCredentials | None] = ContextVar(
    "request_credentials", default=None
)


def get_request_credentials() -> RequestCredentials | None:
    """Get the current request's Canvas credentials, or None for stdio mode."""
    return _request_credentials.get()


def set_request_credentials(creds: RequestCredentials) -> None:
    """Set Canvas credentials for the current async context."""
    _request_credentials.set(creds)


def clear_request_credentials() -> None:
    """Clear credentials after request completes."""
    _request_credentials.set(None)

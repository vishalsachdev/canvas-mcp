"""Per-request credential context for HTTP transport.

When the server runs in HTTP mode, each request carries its own Canvas API
token via the X-Canvas-Token header. The Canvas API URL is pinned by server
configuration (CANVAS_API_URL), never supplied by the client. This module
uses Python's contextvars to thread the per-request token through the async
call stack without modifying any tool signatures.

In stdio mode, the ContextVar remains unset (None), and the client falls
back to the global .env-based configuration. To keep that fallback from
leaking the server's own token in HTTP mode, an additional ``_http_request_active``
marker distinguishes "HTTP request with no token" (must fail closed) from
"stdio mode" (env fallback is intended).
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

_http_request_active: ContextVar[bool] = ContextVar(
    "http_request_active", default=False
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


def is_http_request_active() -> bool:
    """Return True while handling an HTTP request.

    Used to fail closed: in HTTP mode a missing per-request token must never
    fall back to the server's own credentials.
    """
    return _http_request_active.get()


def set_http_request_active(active: bool = True) -> None:
    """Mark whether the current async context is handling an HTTP request."""
    _http_request_active.set(active)


def clear_http_request_context() -> None:
    """Clear all per-request HTTP context after the request completes."""
    _request_credentials.set(None)
    _http_request_active.set(False)

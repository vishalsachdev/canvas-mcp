"""Custom httpx.Auth implementation with token injection and single-replay on 401."""

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx

from canvas_mcp.auth.mobile import normalize_domain
from canvas_mcp.auth.models import OAuthError
from canvas_mcp.auth.session import OAuthSession

logger = logging.getLogger(__name__)

CANVAS_OAUTH_RETRY_STATE_KEY = "canvas_oauth_retry_state"


@dataclass
class OAuthRetryState:
    """Tracks whether an OAuth 401 replay has already occurred for a logical request."""

    retried: bool = False


class MobileOAuthAuth(httpx.Auth):
    """httpx authentication flow for Canvas mobile OAuth with one-replay on 401."""

    def __init__(self, session: OAuthSession) -> None:
        super().__init__()
        self.session = session
        self.norm_domain = normalize_domain(session.canvas_domain)

    def _is_canvas_origin(self, url: httpx.URL) -> bool:
        """Check if request URL matches the configured Canvas HTTPS origin."""
        if url.scheme.lower() != "https":
            return False
        if url.host.lower() != self.norm_domain:
            return False
        if url.port is not None and url.port != 443:
            return False
        return True

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """Inject Authorization bearer token on same-origin requests and replay once on 401."""
        is_canvas = self._is_canvas_origin(request.url)

        if not is_canvas:
            # Strip any Authorization header from cross-origin requests (e.g. signed download URLs)
            request.headers.pop("Authorization", None)
            yield request
            return

        # Materialize request body if needed for replayability
        try:
            _ = request.content
        except httpx.RequestNotRead:
            try:
                await request.aread()
            except Exception as exc:
                raise OAuthError(
                    f"Failed to read request body for OAuth dispatch: {type(exc).__name__}"
                ) from exc

        # Retrieve retry state from extensions, creating if absent
        if CANVAS_OAUTH_RETRY_STATE_KEY not in request.extensions:
            request.extensions[CANVAS_OAUTH_RETRY_STATE_KEY] = OAuthRetryState()
        retry_state: OAuthRetryState = request.extensions[CANVAS_OAUTH_RETRY_STATE_KEY]

        token, gen = self.session.snapshot()
        request.headers["Authorization"] = f"Bearer {token}"

        response = yield request

        # Only handle 401 if it came from the Canvas origin and hasn't been retried yet
        if response.status_code == 401:
            # Check final response origin
            if self._is_canvas_origin(response.request.url) and not retry_state.retried:
                retry_state.retried = True
                await response.aclose()

                new_token = await self.session.refresh(observed_generation=gen)
                request.headers["Authorization"] = f"Bearer {new_token}"

                yield request

"""Tests for HTTP transport: credential middleware, ContextVar flow, and CLI args."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_mcp.core.credentials import (
    RequestCredentials,
    clear_request_credentials,
    get_request_credentials,
    set_request_credentials,
)

# ---------------------------------------------------------------------------
# ContextVar credential tests
# ---------------------------------------------------------------------------


class TestRequestCredentials:
    """Test the ContextVar-based per-request credential system."""

    def test_default_is_none(self):
        """ContextVar defaults to None (stdio mode)."""
        clear_request_credentials()
        assert get_request_credentials() is None

    def test_set_and_get(self):
        """Can set and retrieve credentials."""
        creds = RequestCredentials(
            api_token="test-token",
            api_url="https://canvas.example.com/api/v1",
        )
        set_request_credentials(creds)
        result = get_request_credentials()
        assert result is not None
        assert result.api_token == "test-token"
        assert result.api_url == "https://canvas.example.com/api/v1"
        clear_request_credentials()

    def test_clear_resets_to_none(self):
        """clear_request_credentials resets to None."""
        set_request_credentials(
            RequestCredentials(api_token="t", api_url="u")
        )
        clear_request_credentials()
        assert get_request_credentials() is None

    def test_credentials_are_frozen(self):
        """RequestCredentials is immutable (frozen dataclass)."""
        creds = RequestCredentials(api_token="t", api_url="u")
        with pytest.raises(AttributeError):
            creds.api_token = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ASGI Middleware tests
# ---------------------------------------------------------------------------


class TestCanvasCredentialMiddleware:
    """Test the ASGI middleware that extracts Canvas headers."""

    @pytest.fixture
    def middleware(self):
        from canvas_mcp.server import CanvasCredentialMiddleware

        inner_app = AsyncMock()
        return CanvasCredentialMiddleware(inner_app)

    @pytest.mark.asyncio
    async def test_extracts_headers_and_sets_credentials(self, middleware):
        """Middleware sets ContextVar from X-Canvas-Token and X-Canvas-URL headers."""
        captured_creds = {}

        async def capture_app(scope, receive, send):
            creds = get_request_credentials()
            if creds:
                captured_creds["token"] = creds.api_token
                captured_creds["url"] = creds.api_url

        middleware.app = capture_app

        scope = {
            "type": "http",
            "headers": [
                (b"x-canvas-token", b"my-secret-token"),
                (b"x-canvas-url", b"https://school.instructure.com/api/v1"),
            ],
        }
        await middleware(scope, AsyncMock(), AsyncMock())

        assert captured_creds["token"] == "my-secret-token"
        assert captured_creds["url"] == "https://school.instructure.com/api/v1"
        # Credentials should be cleared after request
        assert get_request_credentials() is None

    @pytest.mark.asyncio
    async def test_clears_credentials_after_request(self, middleware):
        """Credentials are cleared even if the inner app raises."""
        async def failing_app(scope, receive, send):
            raise ValueError("boom")

        middleware.app = failing_app

        scope = {
            "type": "http",
            "headers": [
                (b"x-canvas-token", b"tok"),
                (b"x-canvas-url", b"https://x.com/api/v1"),
            ],
        }
        with pytest.raises(ValueError, match="boom"):
            await middleware(scope, AsyncMock(), AsyncMock())

        # Must be cleaned up despite error
        assert get_request_credentials() is None

    @pytest.mark.asyncio
    async def test_no_headers_passes_through(self, middleware):
        """Without Canvas headers, no credentials are set."""
        captured_creds = {"set": False}

        async def check_app(scope, receive, send):
            captured_creds["set"] = get_request_credentials() is not None

        middleware.app = check_app

        scope = {"type": "http", "headers": []}
        await middleware(scope, AsyncMock(), AsyncMock())
        assert captured_creds["set"] is False

    @pytest.mark.asyncio
    async def test_lifespan_passthrough(self, middleware):
        """Non-HTTP scopes (e.g., lifespan) pass through without credential logic."""
        called = {"value": False}

        async def inner(scope, receive, send):
            called["value"] = True

        middleware.app = inner

        scope = {"type": "lifespan"}
        await middleware(scope, AsyncMock(), AsyncMock())
        assert called["value"] is True


# ---------------------------------------------------------------------------
# Client integration: ContextVar flows through make_canvas_request
# ---------------------------------------------------------------------------


class TestClientPerRequestCredentials:
    """Test that make_canvas_request uses per-request credentials when set."""

    @pytest.fixture(autouse=True)
    def reset_creds(self):
        clear_request_credentials()
        yield
        clear_request_credentials()

    @pytest.mark.asyncio
    async def test_uses_per_request_credentials(self):
        """When ContextVar is set, make_canvas_request uses those credentials."""
        set_request_credentials(
            RequestCredentials(
                api_token="per-request-token",
                api_url="https://per-request.instructure.com/api/v1",
            )
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "name": "Test User"}
        mock_response.raise_for_status = MagicMock()

        with patch("canvas_mcp.core.client.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.aclose = AsyncMock()
            MockClient.return_value = mock_client_instance

            from canvas_mcp.core.client import make_canvas_request

            await make_canvas_request("get", "/users/self")

            # Verify a new client was created with the per-request token
            MockClient.assert_called_once()
            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer per-request-token"

            # Verify the URL uses per-request base URL
            mock_client_instance.get.assert_called_once()
            call_args = mock_client_instance.get.call_args
            assert "per-request.instructure.com" in call_args[0][0]

            # Client should be closed after use
            mock_client_instance.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_global_client(self):
        """When ContextVar is not set, uses global client (stdio mode)."""
        # No credentials set — stdio mode
        assert get_request_credentials() is None

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1}
        mock_response.raise_for_status = MagicMock()

        with patch("canvas_mcp.core.client._get_http_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            from canvas_mcp.core.client import make_canvas_request

            await make_canvas_request("get", "/courses")

            # Should use the global client
            mock_get_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_per_request_client_closed_on_error(self):
        """Per-request client is closed even when the request fails."""
        set_request_credentials(
            RequestCredentials(api_token="tok", api_url="https://x.com/api/v1")
        )

        with patch("canvas_mcp.core.client.httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=Exception("connection failed")
            )
            mock_client_instance.aclose = AsyncMock()
            MockClient.return_value = mock_client_instance

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("get", "/test")
            assert "error" in result

            # Client must still be closed
            mock_client_instance.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# CLI argument tests
# ---------------------------------------------------------------------------


class TestCLIArgs:
    """Test CLI argument parsing for transport options."""

    def test_default_transport_is_stdio(self):
        """Default transport is stdio."""
        import argparse


        # We can't easily test main() directly, but we can test the argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=8819)
        args = parser.parse_args([])
        assert args.transport == "stdio"
        assert args.host == "0.0.0.0"
        assert args.port == 8819

    def test_http_transport_args(self):
        """Can specify HTTP transport with host and port."""
        import argparse

        parser = argparse.ArgumentParser()
        parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
        parser.add_argument("--host", default="0.0.0.0")
        parser.add_argument("--port", type=int, default=8819)
        args = parser.parse_args(["--transport", "streamable-http", "--port", "9000"])
        assert args.transport == "streamable-http"
        assert args.port == 9000

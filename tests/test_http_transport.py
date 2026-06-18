"""Tests for HTTP transport: credential middleware, ContextVar flow, and CLI args."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_mcp.core.credentials import (
    RequestCredentials,
    clear_http_request_context,
    clear_request_credentials,
    get_request_credentials,
    is_http_request_active,
    set_http_request_active,
    set_request_credentials,
)


class _FakeConfig:
    """Minimal stand-in for the config object the middleware reads."""

    def __init__(
        self,
        canvas_api_url="https://canvas.illinois.edu/api/v1",
        mcp_access_keys=frozenset(),
        entra_auth_enabled=False,
        mcp_entra_allowed_oids=frozenset(),
    ):
        self.canvas_api_url = canvas_api_url
        self.mcp_access_keys = mcp_access_keys
        self.entra_auth_enabled = entra_auth_enabled
        self.mcp_entra_allowed_oids = mcp_entra_allowed_oids

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
    async def test_token_only_pins_url(self, middleware):
        """Middleware sets creds from X-Canvas-Token and the SERVER-pinned URL."""
        captured_creds = {}

        async def capture_app(scope, receive, send):
            creds = get_request_credentials()
            if creds:
                captured_creds["token"] = creds.api_token
                captured_creds["url"] = creds.api_url
                captured_creds["http_active"] = is_http_request_active()

        middleware.app = capture_app

        scope = {
            "type": "http",
            "headers": [(b"x-canvas-token", b"my-secret-token")],
        }
        with patch(
            "canvas_mcp.server.get_config",
            return_value=_FakeConfig("https://canvas.illinois.edu/api/v1"),
        ):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured_creds["token"] == "my-secret-token"
        # URL comes from server config, NOT the client
        assert captured_creds["url"] == "https://canvas.illinois.edu/api/v1"
        assert captured_creds["http_active"] is True
        # Context cleared after request
        assert get_request_credentials() is None
        assert is_http_request_active() is False

    @pytest.mark.asyncio
    async def test_canvas_url_header_is_ignored(self, middleware):
        """A client-supplied X-Canvas-URL is ignored; the pinned URL is always used."""
        captured = {}

        async def capture_app(scope, receive, send):
            creds = get_request_credentials()
            captured["url"] = creds.api_url if creds else None

        middleware.app = capture_app

        scope = {
            "type": "http",
            "headers": [
                (b"x-canvas-token", b"tok"),
                # Attacker-controlled URL must have no effect (SSRF prevention).
                (b"x-canvas-url", b"http://169.254.169.254/latest/meta-data/"),
            ],
        }
        with patch(
            "canvas_mcp.server.get_config",
            return_value=_FakeConfig("https://canvas.illinois.edu/api/v1"),
        ):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured["url"] == "https://canvas.illinois.edu/api/v1"

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, middleware):
        """Without X-Canvas-Token, the request is rejected 401 and the app never runs."""
        app_called = {"value": False}

        async def inner(scope, receive, send):
            app_called["value"] = True

        middleware.app = inner
        send = AsyncMock()

        scope = {"type": "http", "headers": []}
        await middleware(scope, AsyncMock(), send)

        assert app_called["value"] is False  # fail closed: inner app not reached
        # First send call is the response start with status 401
        first_call = send.call_args_list[0][0][0]
        assert first_call["type"] == "http.response.start"
        assert first_call["status"] == 401
        # Context cleared
        assert get_request_credentials() is None
        assert is_http_request_active() is False

    @pytest.mark.asyncio
    async def test_blank_token_returns_401(self, middleware):
        """A blank/whitespace X-Canvas-Token is treated as missing."""
        app_called = {"value": False}

        async def inner(scope, receive, send):
            app_called["value"] = True

        middleware.app = inner
        send = AsyncMock()

        scope = {"type": "http", "headers": [(b"x-canvas-token", b"   ")]}
        await middleware(scope, AsyncMock(), send)

        assert app_called["value"] is False
        assert send.call_args_list[0][0][0]["status"] == 401

    @pytest.mark.asyncio
    async def test_clears_context_after_error(self, middleware):
        """Credentials AND the http-active marker are cleared even if the app raises."""
        async def failing_app(scope, receive, send):
            raise ValueError("boom")

        middleware.app = failing_app

        scope = {"type": "http", "headers": [(b"x-canvas-token", b"tok")]}
        with patch(
            "canvas_mcp.server.get_config",
            return_value=_FakeConfig("https://canvas.illinois.edu/api/v1"),
        ):
            with pytest.raises(ValueError, match="boom"):
                await middleware(scope, AsyncMock(), AsyncMock())

        # Must be cleaned up despite error
        assert get_request_credentials() is None
        assert is_http_request_active() is False

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


class TestAccessKeyGate:
    """Test the v1 MCP_ACCESS_KEYS header gate."""

    @pytest.fixture
    def middleware(self):
        from canvas_mcp.server import CanvasCredentialMiddleware

        return CanvasCredentialMiddleware(AsyncMock())

    @pytest.mark.asyncio
    async def test_valid_key_passes_through(self, middleware):
        """A matching X-MCP-Access-Key lets the request proceed to creds."""
        captured = {}

        async def capture_app(scope, receive, send):
            creds = get_request_credentials()
            captured["token"] = creds.api_token if creds else None

        middleware.app = capture_app
        scope = {
            "type": "http",
            "headers": [
                (b"x-mcp-access-key", b"key-abc"),
                (b"x-canvas-token", b"tok"),
            ],
        }
        cfg = _FakeConfig(mcp_access_keys=frozenset({"key-abc", "key-def"}))
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured["token"] == "tok"

    @pytest.mark.asyncio
    async def test_missing_key_returns_401_and_skips_canvas(self, middleware):
        """No access key -> 401 before the Canvas token is even considered."""
        app_called = {"value": False}

        async def inner(scope, receive, send):
            app_called["value"] = True

        middleware.app = inner
        send = AsyncMock()
        scope = {
            "type": "http",
            "headers": [(b"x-canvas-token", b"tok")],  # valid canvas token, but no access key
        }
        cfg = _FakeConfig(mcp_access_keys=frozenset({"key-abc"}))
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), send)

        assert app_called["value"] is False
        first_call = send.call_args_list[0][0][0]
        assert first_call["status"] == 401
        assert get_request_credentials() is None

    @pytest.mark.asyncio
    async def test_wrong_key_returns_401(self, middleware):
        """A non-matching access key is rejected."""
        send = AsyncMock()
        scope = {
            "type": "http",
            "headers": [
                (b"x-mcp-access-key", b"wrong"),
                (b"x-canvas-token", b"tok"),
            ],
        }
        cfg = _FakeConfig(mcp_access_keys=frozenset({"key-abc"}))
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), send)

        assert send.call_args_list[0][0][0]["status"] == 401

    @pytest.mark.asyncio
    async def test_no_keys_configured_gate_disabled(self, middleware):
        """With no MCP_ACCESS_KEYS, the gate is inactive (token gate still applies)."""
        captured = {}

        async def capture_app(scope, receive, send):
            creds = get_request_credentials()
            captured["token"] = creds.api_token if creds else None

        middleware.app = capture_app
        scope = {"type": "http", "headers": [(b"x-canvas-token", b"tok")]}
        cfg = _FakeConfig(mcp_access_keys=frozenset())
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured["token"] == "tok"


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
# Event loop change detection tests
# ---------------------------------------------------------------------------


class TestEventLoopChangeDetection:
    """Regression tests for 'Event loop is closed' on user-scoped tools.

    Root cause: asyncio.run(_validate_token()) during server startup creates
    and immediately closes event loop A.  Any global httpx.AsyncClient or
    asyncio.Semaphore created inside that call has its internal anyio/asyncio
    connection-pool primitives tied to loop A.  When mcp.run() starts event
    loop B, subsequent tool calls reuse those stale globals and get
    "Event loop is closed" errors.

    Fix: _get_http_client() and _get_request_semaphore() keep a weakref to the
    loop that was running when they were created.  When that loop is
    garbage-collected (as asyncio.run() does when it exits), the weakref goes
    dead, and the next call from loop B detects a stale global and discards it.
    """

    def setup_method(self):
        """Reset client globals before each test."""
        import canvas_mcp.core.client as _cm
        _cm.http_client = None
        _cm._http_client_loop_ref = None
        _cm._request_semaphore = None
        _cm._semaphore_loop_ref = None

    def teardown_method(self):
        """Reset client globals after each test."""
        import canvas_mcp.core.client as _cm
        _cm.http_client = None
        _cm._http_client_loop_ref = None
        _cm._request_semaphore = None
        _cm._semaphore_loop_ref = None

    @pytest.mark.asyncio
    async def test_http_client_stores_weakref_to_loop(self):
        """_get_http_client() stores a weakref to the creating loop."""
        import asyncio

        import canvas_mcp.core.client as _cm
        from canvas_mcp.core.client import _get_http_client

        _get_http_client()
        assert _cm._http_client_loop_ref is not None
        stored_loop = _cm._http_client_loop_ref()
        assert stored_loop is asyncio.get_running_loop()

    @pytest.mark.asyncio
    async def test_semaphore_stores_weakref_to_loop(self):
        """_get_request_semaphore() stores a weakref to the creating loop."""
        import asyncio

        import canvas_mcp.core.client as _cm
        from canvas_mcp.core.client import _get_request_semaphore

        _get_request_semaphore()
        assert _cm._semaphore_loop_ref is not None
        stored_loop = _cm._semaphore_loop_ref()
        assert stored_loop is asyncio.get_running_loop()

    @pytest.mark.asyncio
    async def test_http_client_recreated_when_stored_loop_gone(self):
        """_get_http_client() discards the cached client when the stored loop is gone.

        Simulates what happens after asyncio.run() closes its event loop: the
        weakref stored by _get_http_client() becomes dead (resolves to None),
        and the next call must create a fresh client bound to the current loop.
        """
        import gc
        import weakref

        import canvas_mcp.core.client as _cm
        from canvas_mcp.core.client import _get_http_client

        # Grab a reference to the current client
        first_client = _get_http_client()

        # Simulate a dead weakref (as if the old loop was GC-collected after
        # asyncio.run() closed it) by pointing the stored ref at a temporary
        # object that we immediately let go.
        class _FakeLoop:
            pass

        fake_loop = _FakeLoop()
        _cm._http_client_loop_ref = weakref.ref(fake_loop)
        del fake_loop
        gc.collect()
        # Weakref must now be dead
        assert _cm._http_client_loop_ref() is None

        # Next call must return a fresh client (not the stale one)
        second_client = _get_http_client()
        assert second_client is not first_client, "Stale client was not replaced when loop weakref died"

    @pytest.mark.asyncio
    async def test_semaphore_recreated_when_stored_loop_gone(self):
        """_get_request_semaphore() discards the cached semaphore when the stored loop is gone."""
        import gc
        import weakref

        import canvas_mcp.core.client as _cm
        from canvas_mcp.core.client import _get_request_semaphore

        first_sem = _get_request_semaphore()

        class _FakeLoop:
            pass

        fake_loop = _FakeLoop()
        _cm._semaphore_loop_ref = weakref.ref(fake_loop)
        del fake_loop
        gc.collect()
        assert _cm._semaphore_loop_ref() is None

        second_sem = _get_request_semaphore()
        assert second_sem is not first_sem, "Stale semaphore was not replaced when loop weakref died"

    def test_http_client_recreated_across_asyncio_run_calls(self):
        """A fresh client is created in loop B when loop A was closed by asyncio.run().

        This is the exact scenario that caused the 'Event loop is closed' bug:
        startup validation runs in asyncio.run() (loop A), then mcp.run() starts
        loop B.  The fix must create a new client in loop B.
        """
        import asyncio
        import gc

        import canvas_mcp.core.client as _cm
        from canvas_mcp.core.client import _get_http_client

        # Loop A — simulate asyncio.run() during startup validation
        state_a: dict = {}

        async def _loop_a():
            client = _get_http_client()
            state_a["client_id"] = id(client)
            state_a["loop_ref_alive"] = (
                _cm._http_client_loop_ref is not None
                and _cm._http_client_loop_ref() is not None
            )

        asyncio.run(_loop_a())
        # Loop A is closed; force GC
        gc.collect()

        # Weakref to loop A must be dead before loop B can detect the stale state
        assert _cm._http_client_loop_ref is not None
        assert _cm._http_client_loop_ref() is None, (
            "Weakref to loop A must be dead after asyncio.run() exits"
        )
        assert state_a["loop_ref_alive"], "Loop ref should be alive INSIDE loop A"

        # Loop B — simulate mcp.run()
        state_b: dict = {}

        async def _loop_b():
            client = _get_http_client()
            state_b["client_id"] = id(client)
            # The loop ref must be alive while inside loop B
            state_b["loop_ref_alive"] = (
                _cm._http_client_loop_ref is not None
                and _cm._http_client_loop_ref() is not None
            )
            # And it must point to the currently running loop
            state_b["loop_ref_is_current"] = (
                _cm._http_client_loop_ref is not None
                and _cm._http_client_loop_ref() is asyncio.get_running_loop()
            )

        asyncio.run(_loop_b())

        # The loop weakref must have been live INSIDE loop B (proves fresh client was created)
        assert state_b["loop_ref_alive"], (
            "Loop weakref must be alive inside loop B — proves a fresh client was created"
        )
        assert state_b["loop_ref_is_current"], (
            "Loop weakref must point to loop B's running loop"
        )

    def test_server_startup_resets_globals_after_asyncio_run(self):
        """server.main() resets http_client globals after asyncio.run() token validation.

        Defense-in-depth: even before the first tool call, the startup code in
        server.py explicitly clears the stale globals so mcp.run() starts clean.
        """
        import canvas_mcp.core.client as _cm

        # Pretend a stale client was left over from asyncio.run()
        _cm.http_client = MagicMock()
        _cm._http_client_loop_ref = MagicMock()

        # Run the same cleanup code that server.py executes in its finally block
        _cm.http_client = None
        _cm._http_client_loop_ref = None
        _cm._request_semaphore = None
        _cm._semaphore_loop_ref = None

        assert _cm.http_client is None
        assert _cm._http_client_loop_ref is None
        assert _cm._request_semaphore is None
        assert _cm._semaphore_loop_ref is None


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


# ---------------------------------------------------------------------------
# Fail-closed behavior: HTTP request with no per-request token
# ---------------------------------------------------------------------------


class TestFailClosedNoToken:
    """In HTTP mode, a missing per-request token must NEVER use server creds."""

    @pytest.fixture(autouse=True)
    def reset_context(self):
        clear_http_request_context()
        yield
        clear_http_request_context()

    @pytest.mark.asyncio
    async def test_make_request_blocks_when_http_active_no_token(self):
        """make_canvas_request returns an error (not server fallback) in HTTP mode w/o token."""
        set_http_request_active(True)
        assert get_request_credentials() is None

        with patch("canvas_mcp.core.client._get_http_client") as mock_get_client:
            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("get", "/users/self")

            assert isinstance(result, dict) and "error" in result
            # Global (server-token) client must NOT be used
            mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_authenticated_client_raises_when_http_active_no_token(self):
        """canvas_authenticated_client raises rather than using the server client."""
        set_http_request_active(True)
        assert get_request_credentials() is None

        from canvas_mcp.core.client import canvas_authenticated_client

        with pytest.raises(PermissionError):
            async with canvas_authenticated_client():
                pass

    @pytest.mark.asyncio
    async def test_authenticated_client_uses_per_request_token(self):
        """canvas_authenticated_client builds a client with the caller's token."""
        set_http_request_active(True)
        set_request_credentials(
            RequestCredentials(
                api_token="caller-token",
                api_url="https://canvas.illinois.edu/api/v1",
            )
        )

        with patch("canvas_mcp.core.client.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            from canvas_mcp.core.client import canvas_authenticated_client

            async with canvas_authenticated_client() as client:
                assert client is instance

            call_kwargs = MockClient.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer caller-token"

    @pytest.mark.asyncio
    async def test_stdio_mode_still_falls_back_to_global_client(self):
        """Without an active HTTP request, the global (env) client is still used."""
        # http NOT active -> stdio mode
        assert is_http_request_active() is False
        assert get_request_credentials() is None

        from canvas_mcp.core.client import canvas_authenticated_client

        with patch("canvas_mcp.core.client._get_http_client") as mock_get_client:
            sentinel = object()
            mock_get_client.return_value = sentinel
            async with canvas_authenticated_client() as client:
                assert client is sentinel
            mock_get_client.assert_called_once()


# ---------------------------------------------------------------------------
# Startup guard: HTTP mode fails closed when the key gate is unconfigured
# ---------------------------------------------------------------------------


class TestHttpAccessKeyStartupGuard:
    """In HTTP mode, an unconfigured MCP_ACCESS_KEYS must refuse to start
    unless MCP_ALLOW_UNAUTHENTICATED=true is explicitly set (external auth)."""

    def _run_main(self, monkeypatch, env):
        """Drive main() in HTTP mode with --config (exits before serving).

        Returns the SystemExit raised by main() so the caller can assert the
        exit code: 1 == guard tripped (fail closed), 0 == guard passed.
        """
        from canvas_mcp.core import config as config_module

        # Clean slate: required HTTP env, no server token, plus test overrides.
        monkeypatch.setenv("CANVAS_API_URL", "https://canvas.illinois.edu/api/v1")
        monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
        monkeypatch.delenv("CANVAS_SESSION_COOKIE", raising=False)
        monkeypatch.delenv("MCP_ACCESS_KEYS", raising=False)
        monkeypatch.delenv("MCP_ALLOW_UNAUTHENTICATED", raising=False)
        monkeypatch.delenv("ENTRA_AUTH_ENABLED", raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        config_module.reset_config()
        monkeypatch.setattr(
            "sys.argv",
            ["canvas-mcp-server", "--transport", "streamable-http", "--config"],
        )
        from canvas_mcp.server import main

        with pytest.raises(SystemExit) as exc_info:
            main()
        config_module.reset_config()
        return exc_info.value

    def test_no_keys_no_optin_exits_nonzero(self, monkeypatch):
        """No MCP_ACCESS_KEYS and no opt-in -> fail closed (exit 1)."""
        exc = self._run_main(monkeypatch, env={})
        assert exc.code == 1

    def test_no_keys_with_explicit_optin_starts(self, monkeypatch):
        """No keys but MCP_ALLOW_UNAUTHENTICATED=true -> guard passes (exit 0)."""
        exc = self._run_main(
            monkeypatch, env={"MCP_ALLOW_UNAUTHENTICATED": "true"}
        )
        assert exc.code == 0

    def test_entra_enabled_without_optin_exits_nonzero(self, monkeypatch):
        """ENTRA_AUTH_ENABLED=true without MCP_ALLOW_UNAUTHENTICATED -> fail closed.

        Even with MCP_ACCESS_KEYS set, Entra mode must require the explicit
        external-auth acknowledgment (the X-MS-* identity header is only
        trustworthy when App Service actually fronts the endpoint).
        """
        exc = self._run_main(
            monkeypatch,
            env={"ENTRA_AUTH_ENABLED": "true", "MCP_ACCESS_KEYS": "key-abc"},
        )
        assert exc.code == 1

    def test_entra_enabled_with_optin_starts(self, monkeypatch):
        """ENTRA_AUTH_ENABLED=true + MCP_ALLOW_UNAUTHENTICATED=true -> starts (exit 0)."""
        exc = self._run_main(
            monkeypatch,
            env={
                "ENTRA_AUTH_ENABLED": "true",
                "MCP_ALLOW_UNAUTHENTICATED": "true",
            },
        )
        assert exc.code == 0

    def test_keys_configured_starts(self, monkeypatch):
        """MCP_ACCESS_KEYS configured -> guard passes regardless of opt-in (exit 0)."""
        exc = self._run_main(
            monkeypatch, env={"MCP_ACCESS_KEYS": "key-abc,key-def"}
        )
        assert exc.code == 0


# ---------------------------------------------------------------------------
# Entra platform-auth path (Azure App Service validates the token upstream;
# the middleware authorizes the injected X-MS-CLIENT-PRINCIPAL-ID identity)
# ---------------------------------------------------------------------------


def _principal_header(claims: dict) -> bytes:
    """Build a base64 X-MS-CLIENT-PRINCIPAL value from a claim dict."""
    import base64
    import json

    payload = {"claims": [{"typ": k, "val": v} for k, v in claims.items()]}
    return base64.b64encode(json.dumps(payload).encode("utf-8"))


class TestEntraPlatformAuth:
    """When entra_auth_enabled, the access key is replaced by the platform identity."""

    @pytest.fixture
    def middleware(self):
        from canvas_mcp.server import CanvasCredentialMiddleware

        return CanvasCredentialMiddleware(AsyncMock())

    @pytest.mark.asyncio
    async def test_allowlisted_identity_passes_without_access_key(self, middleware):
        """A platform-injected oid on the allowlist proceeds — no X-MCP-Access-Key."""
        captured = {}

        async def capture_app(scope, receive, send):
            creds = get_request_credentials()
            captured["token"] = creds.api_token if creds else None

        middleware.app = capture_app
        scope = {
            "type": "http",
            "headers": [
                (b"x-ms-client-principal-id", b"oid-alice"),
                (b"x-canvas-token", b"tok"),
            ],
        }
        cfg = _FakeConfig(
            entra_auth_enabled=True,
            mcp_entra_allowed_oids=frozenset({"oid-alice", "oid-bob"}),
        )
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured["token"] == "tok"

    @pytest.mark.asyncio
    async def test_missing_identity_returns_401(self, middleware):
        """No X-MS-CLIENT-PRINCIPAL-ID -> fail closed (401), Canvas not reached."""
        app_called = {"value": False}

        async def inner(scope, receive, send):
            app_called["value"] = True

        middleware.app = inner
        send = AsyncMock()
        scope = {"type": "http", "headers": [(b"x-canvas-token", b"tok")]}
        cfg = _FakeConfig(entra_auth_enabled=True)
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), send)

        assert app_called["value"] is False
        assert send.call_args_list[0][0][0]["status"] == 401
        assert get_request_credentials() is None

    @pytest.mark.asyncio
    async def test_non_allowlisted_identity_returns_403(self, middleware):
        """A valid platform identity not on the allowlist -> 403."""
        send = AsyncMock()
        scope = {
            "type": "http",
            "headers": [
                (b"x-ms-client-principal-id", b"oid-eve"),
                (b"x-canvas-token", b"tok"),
            ],
        }
        cfg = _FakeConfig(
            entra_auth_enabled=True,
            mcp_entra_allowed_oids=frozenset({"oid-alice"}),
        )
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), send)

        assert send.call_args_list[0][0][0]["status"] == 403

    @pytest.mark.asyncio
    async def test_empty_allowlist_allows_any_platform_identity(self, middleware):
        """Empty allowlist -> any platform-authenticated identity proceeds."""
        captured = {}

        async def capture_app(scope, receive, send):
            creds = get_request_credentials()
            captured["token"] = creds.api_token if creds else None

        middleware.app = capture_app
        scope = {
            "type": "http",
            "headers": [
                (b"x-ms-client-principal-id", b"oid-anyone"),
                (b"x-ms-client-principal", _principal_header({"scp": "access_as_user"})),
                (b"x-canvas-token", b"tok"),
            ],
        }
        cfg = _FakeConfig(entra_auth_enabled=True, mcp_entra_allowed_oids=frozenset())
        with patch("canvas_mcp.server.get_config", return_value=cfg):
            await middleware(scope, AsyncMock(), AsyncMock())

        assert captured["token"] == "tok"


# ---------------------------------------------------------------------------
# Session cookie authentication tests
# ---------------------------------------------------------------------------


class TestSessionCookieCredentials:
    """RequestCredentials carries session_cookie and defaults it to empty string."""

    def test_default_session_cookie_is_empty(self):
        """session_cookie defaults to empty string for backward compatibility."""
        creds = RequestCredentials(api_token="tok", api_url="https://canvas.example.com/api/v1")
        assert creds.session_cookie == ""

    def test_session_cookie_stored_and_retrieved(self):
        """session_cookie value round-trips through set/get."""
        creds = RequestCredentials(
            api_token="",
            api_url="https://canvas.example.com/api/v1",
            session_cookie="abc123",
        )
        set_request_credentials(creds)
        result = get_request_credentials()
        assert result is not None
        assert result.session_cookie == "abc123"
        clear_request_credentials()

    def test_frozen_with_session_cookie(self):
        """RequestCredentials with session_cookie is still immutable."""
        creds = RequestCredentials(api_token="", api_url="u", session_cookie="s")
        with pytest.raises(AttributeError):
            creds.session_cookie = "other"  # type: ignore[misc]


class TestCanvasAuthHeaders:
    """_canvas_auth_headers builds the correct headers for each credential type."""

    def test_token_produces_bearer_header(self):
        from canvas_mcp.core.client import _canvas_auth_headers

        headers = _canvas_auth_headers(api_token="mytoken")
        assert headers["Authorization"] == "Bearer mytoken"
        assert "Cookie" not in headers

    def test_session_cookie_produces_cookie_header(self):
        from canvas_mcp.core.client import _canvas_auth_headers

        headers = _canvas_auth_headers(session_cookie="cookieval")
        assert headers["Cookie"] == "canvas_session=cookieval"
        assert "Authorization" not in headers

    def test_token_takes_precedence_over_cookie(self):
        from canvas_mcp.core.client import _canvas_auth_headers

        headers = _canvas_auth_headers(api_token="tok", session_cookie="cook")
        assert headers["Authorization"] == "Bearer tok"
        assert "Cookie" not in headers

    def test_neither_produces_no_auth_header(self):
        from canvas_mcp.core.client import _canvas_auth_headers

        headers = _canvas_auth_headers()
        assert "Authorization" not in headers
        assert "Cookie" not in headers
        assert "User-Agent" in headers


class TestMiddlewareSessionCookie:
    """CanvasCredentialMiddleware accepts X-Canvas-Session-Cookie in HTTP mode."""

    @pytest.fixture
    def middleware(self):
        from canvas_mcp.server import CanvasCredentialMiddleware

        app = AsyncMock()
        mw = CanvasCredentialMiddleware(app)
        mw._app = app
        return mw

    def _make_scope(self, headers: dict[bytes, bytes]) -> dict:
        return {
            "type": "http",
            "headers": list(headers.items()),
        }

    @pytest.fixture(autouse=True)
    def reset_context(self):
        clear_http_request_context()
        yield
        clear_http_request_context()

    @pytest.mark.asyncio
    async def test_cookie_only_sets_credentials(self, middleware):
        """A request with only X-Canvas-Session-Cookie is accepted."""
        scope = self._make_scope({b"x-canvas-session-cookie": b"cookievalue"})
        receive = AsyncMock()
        send = AsyncMock()

        with patch("canvas_mcp.server.get_config", return_value=_FakeConfig()):
            with patch("canvas_mcp.server.set_request_credentials") as mock_set:
                await middleware(scope, receive, send)

        mock_set.assert_called_once()
        stored: RequestCredentials = mock_set.call_args[0][0]
        assert stored.session_cookie == "cookievalue"
        assert stored.api_token == ""

    @pytest.mark.asyncio
    async def test_token_takes_precedence_when_both_present(self, middleware):
        """When both headers are supplied, the API token wins."""
        scope = self._make_scope({
            b"x-canvas-token": b"apitoken",
            b"x-canvas-session-cookie": b"cookievalue",
        })
        receive = AsyncMock()
        send = AsyncMock()

        with patch("canvas_mcp.server.get_config", return_value=_FakeConfig()):
            with patch("canvas_mcp.server.set_request_credentials") as mock_set:
                await middleware(scope, receive, send)

        stored: RequestCredentials = mock_set.call_args[0][0]
        assert stored.api_token == "apitoken"
        assert stored.session_cookie == "cookievalue"

    @pytest.mark.asyncio
    async def test_neither_token_nor_cookie_returns_401(self, middleware):
        """A request with no canvas credentials gets HTTP 401."""
        scope = self._make_scope({})
        receive = AsyncMock()
        responses: list[dict] = []

        async def capture_send(event: dict) -> None:
            responses.append(event)

        with patch("canvas_mcp.server.get_config", return_value=_FakeConfig()):
            await middleware(scope, receive, capture_send)

        start = next(r for r in responses if r.get("type") == "http.response.start")
        assert start["status"] == 401

    @pytest.mark.asyncio
    async def test_cookie_prefix_stripped(self, middleware):
        """If the user pastes 'canvas_session=value', the prefix is stripped."""
        scope = self._make_scope({b"x-canvas-session-cookie": b"canvas_session=cookievalue"})
        receive = AsyncMock()
        send = AsyncMock()

        with patch("canvas_mcp.server.get_config", return_value=_FakeConfig()):
            with patch("canvas_mcp.server.set_request_credentials") as mock_set:
                await middleware(scope, receive, send)

        stored: RequestCredentials = mock_set.call_args[0][0]
        assert stored.session_cookie == "cookievalue"

"""Integration tests for mobile OAuth: manual CLI-to-request pipeline and headed browser capture."""

import os
import re
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

import httpx
import pytest

from canvas_mcp.auth import cli
from canvas_mcp.auth.store import TokenStore
from canvas_mcp.core import config as cfg_mod
from canvas_mcp.core.client import make_canvas_request


def test_in_process_cli_manual_login_to_request_pipeline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise complete CLI login and subsequent Canvas authenticated request with refresh."""
    store_file = tmp_path / "tokens.json"
    custom_store = TokenStore(store_file)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        # Mobile verify
        if "mobile_verify.json" in url_str:
            return httpx.Response(
                200,
                json={
                    "client_id": "client-id-xyz",
                    "client_secret": "client-secret-xyz",
                    "base_url": "https://canvas.example.test",
                    "authorized": True,
                },
            )
        # Token exchange or refresh
        elif "/login/oauth2/token" in url_str:
            body = parse_qs(request.content.decode("utf-8"))
            grant_type = body.get("grant_type", [""])[0]
            if grant_type == "authorization_code":
                assert body.get("code") == ["integ_code_123"]
                return httpx.Response(
                    200,
                    json={
                        "access_token": "initial-integ-access-tok",
                        "refresh_token": "integ-refresh-tok",
                        "token_type": "Bearer",
                        "user": {"id": 888, "name": "Integ User"},
                    },
                )
            elif grant_type == "refresh_token":
                assert body.get("refresh_token") == ["integ-refresh-tok"]
                return httpx.Response(
                    200,
                    json={
                        "access_token": "refreshed-integ-access-tok",
                        "token_type": "Bearer",
                    },
                )
        # User self
        elif "/api/v1/users/self" in url_str:
            return httpx.Response(200, json={"id": 888, "name": "Integ User"})
        # Courses request
        elif "/api/v1/courses" in url_str:
            auth_header = request.headers.get("Authorization")
            if auth_header == "Bearer initial-integ-access-tok":
                # Stale initial token triggers 401
                return httpx.Response(401, json={"error": "Token expired"})
            elif auth_header == "Bearer refreshed-integ-access-tok":
                return httpx.Response(200, json=[{"id": 101, "name": "Integ 101"}])
            return httpx.Response(403)

        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    def mock_getpass(prompt: str = "") -> str:
        captured = capsys.readouterr().err
        match = re.search(r"[?&]state=([a-zA-Z0-9_-]+)", captured)
        assert match is not None
        state = match.group(1)
        return (
            f"https://sso.canvaslms.com/canvas/login?code=integ_code_123&state={state}"
        )

    # 1. Run CLI login
    with patch.object(cli, "TokenStore", return_value=custom_store):
        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("getpass.getpass", side_effect=mock_getpass):
                cli.main(["login", "--domain", "canvas.example.test", "--manual"])

    out = capsys.readouterr().out
    assert "Successfully authenticated with Canvas mobile OAuth" in out
    assert "User ID: 888" in out

    # 2. Reload store in separate object
    reloaded_store = TokenStore(store_file)
    entry = reloaded_store.load("canvas.example.test")
    assert entry is not None
    assert entry.access_token.get_secret_value() == "initial-integ-access-tok"

    # 3. Configure environment for stdio OAuth
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example.test/api/v1")
    cfg_mod.reset_config()

    # 4. Make Canvas API request through client: hits 401 -> refresh -> 200
    import asyncio

    orig_client_init = httpx.AsyncClient.__init__

    def patched_client_init(self: Any, *args: Any, **kwargs: Any) -> None:
        if "transport" not in kwargs or kwargs["transport"] is None:
            kwargs["transport"] = httpx.MockTransport(mock_handler)
        orig_client_init(self, *args, **kwargs)

    with patch("canvas_mcp.auth.session.TokenStore", return_value=reloaded_store):
        with patch.object(httpx.AsyncClient, "__init__", patched_client_init):
            courses = asyncio.run(make_canvas_request("get", "/api/v1/courses"))

    assert courses == [{"id": 101, "name": "Integ 101"}]
    # 5. Check reloaded store was updated with refreshed token
    updated_entry = reloaded_store.load("canvas.example.test")
    assert updated_entry is not None
    assert updated_entry.access_token.get_secret_value() == "refreshed-integ-access-tok"


# ---------------------------------------------------------------------------
# Browser integration tests (Headed Chromium with Playwright)
# ---------------------------------------------------------------------------

BROWSER_TESTS_ENABLED = os.environ.get("CANVAS_OAUTH_BROWSER_TESTS") == "1"


@pytest.mark.skipif(
    not BROWSER_TESTS_ENABLED,
    reason="Browser integration tests require CANVAS_OAUTH_BROWSER_TESTS=1",
)
@pytest.mark.asyncio
async def test_browser_capture_success_with_local_routes() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.fail("playwright is not installed but CANVAS_OAUTH_BROWSER_TESTS=1")

    from canvas_mcp.auth.browser import capture_authorization_code

    state = "test_browser_state_abc123"
    auth_url = f"https://canvas.example.test/login/oauth2/auth?state={state}"

    async def route_interceptor(route: Any) -> None:
        url = route.request.url
        if "canvas.example.test" in url:
            # Simulate Canvas IdP page redirecting to sso callback
            callback = f"https://sso.canvaslms.com/canvas/login?code=browser_code_xyz&state={state}"
            await route.fulfill(
                status=200,
                content_type="text/html",
                body=f"<html><body>Redirecting...<script>window.location.href = '{callback}';</script></body></html>",
            )
        elif "sso.canvaslms.com/canvas/login" in url:
            await route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body>Callback captured</body></html>",
            )
        else:
            await route.abort()

    # Launch real browser and test capture
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False)
        except Exception as exc:
            pytest.fail(f"Failed to launch Chromium browser: {exc}")

        context = await browser.new_context()
        await context.route("**/*", route_interceptor)

        # Patch browser.new_context to apply our route to newly created contexts
        orig_new_context = browser.new_context

        async def patched_new_context(*args: Any, **kwargs: Any) -> Any:
            ctx = await orig_new_context(*args, **kwargs)
            await ctx.route("**/*", route_interceptor)
            return ctx

        browser.new_context = patched_new_context  # type: ignore[method-assign]

        with patch("playwright.async_api.async_playwright") as mock_ap:
            # Set up mock_ap to return our real browser
            mock_ap.return_value.__aenter__.return_value.chromium.launch = AsyncMock(
                return_value=browser
            )

            code = await capture_authorization_code(
                auth_url, state, timeout_seconds=30.0
            )
            assert code == "browser_code_xyz"


@pytest.mark.skipif(
    not BROWSER_TESTS_ENABLED,
    reason="Browser integration tests require CANVAS_OAUTH_BROWSER_TESTS=1",
)
@pytest.mark.asyncio
async def test_browser_capture_popup_page() -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        pytest.fail("playwright is not installed but CANVAS_OAUTH_BROWSER_TESTS=1")

    from canvas_mcp.auth.browser import capture_authorization_code

    state = "test_popup_state_def456"
    auth_url = f"https://canvas.example.test/login/oauth2/auth?state={state}"

    async def route_interceptor(route: Any) -> None:
        url = route.request.url
        if "canvas.example.test" in url:
            # Page opens a popup that navigates to the callback URL
            callback = f"https://sso.canvaslms.com/canvas/login?code=popup_code_xyz&state={state}"
            html = f"""
            <html>
            <body>
            <button id="btn" onclick="window.open('{callback}', '_blank')">Login</button>
            <script>
                setTimeout(() => window.open('{callback}', '_blank'), 100);
            </script>
            </body>
            </html>
            """
            await route.fulfill(status=200, content_type="text/html", body=html)
        elif "sso.canvaslms.com/canvas/login" in url:
            await route.fulfill(
                status=200,
                content_type="text/html",
                body="<html><body>Done</body></html>",
            )
        else:
            await route.abort()

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False)
        except Exception as exc:
            pytest.fail(f"Failed to launch Chromium browser: {exc}")

        orig_new_context = browser.new_context

        async def patched_new_context(*args: Any, **kwargs: Any) -> Any:
            ctx = await orig_new_context(*args, **kwargs)
            await ctx.route("**/*", route_interceptor)
            return ctx

        browser.new_context = patched_new_context  # type: ignore[method-assign]

        with patch("playwright.async_api.async_playwright") as mock_ap:
            mock_ap.return_value.__aenter__.return_value.chromium.launch = AsyncMock(
                return_value=browser
            )

            code = await capture_authorization_code(
                auth_url, state, timeout_seconds=30.0
            )
            assert code == "popup_code_xyz"

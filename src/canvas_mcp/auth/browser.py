"""Playwright browser automation for Canvas mobile OAuth interactive login."""

import asyncio
import logging
from urllib.parse import urlsplit

from canvas_mcp.auth.mobile import extract_authorization_code
from canvas_mcp.auth.models import OAuthError

logger = logging.getLogger(__name__)

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 16; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36"
)


async def capture_authorization_code(
    authorization_url: str,
    state: str,
    timeout_seconds: float = 180.0,
) -> str:
    """Launch headed Chromium to capture the OAuth authorization callback.

    Uses Pixel 7 mobile viewport and user-agent emulation. Blocks service workers.
    Observes context-wide requests across main page and any popup windows.
    """
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError as e:
        raise OAuthError(
            "Playwright is not installed. Install with `uv sync --extra oauth`."
        ) from e

    loop = asyncio.get_running_loop()
    code_future: asyncio.Future[str] = loop.create_future()
    deadline = loop.time() + timeout_seconds

    async with async_playwright() as p:
        browser = None
        context = None
        nav_task: asyncio.Task[object] | None = None
        try:
            browser = await p.chromium.launch(headless=False)
        except Exception as e:
            raise OAuthError(f"Failed to launch Chromium browser: {e}") from e
        try:
            context = await browser.new_context(
                viewport={"width": 412, "height": 915},
                device_scale_factor=2.625,
                is_mobile=True,
                has_touch=True,
                user_agent=BROWSER_USER_AGENT,
                service_workers="block",
            )

            def handle_url_candidate(url: str) -> None:
                try:
                    parsed = urlsplit(url)
                    if (
                        parsed.scheme.lower() == "https"
                        and parsed.hostname
                        and parsed.hostname.lower() == "sso.canvaslms.com"
                        and parsed.path.rstrip("/") == "/canvas/login"
                    ):
                        code = extract_authorization_code(url, state)
                        if not code_future.done():
                            code_future.set_result(code)
                except OAuthError as exc:
                    if not code_future.done():
                        code_future.set_exception(exc)
                except Exception as exc:
                    logger.debug("Error checking URL %s: %s", url, exc)

            def on_request(req: object) -> None:
                url = getattr(req, "url", "")
                if url:
                    handle_url_candidate(url)

            def on_disconnected() -> None:
                if not code_future.done():
                    code_future.set_exception(
                        OAuthError("Browser was closed before authorization completed.")
                    )

            browser.on("disconnected", lambda: on_disconnected())
            context.on("request", on_request)

            page = await context.new_page()

            def on_page_close() -> None:
                if len(context.pages) == 0 and not code_future.done():
                    code_future.set_exception(
                        OAuthError(
                            "Browser page was closed before authorization completed."
                        )
                    )

            page.on("close", lambda _: on_page_close())

            # Start navigation with remaining deadline
            remaining = max(1.0, deadline - loop.time())
            nav_task = asyncio.create_task(
                page.goto(authorization_url, timeout=int(remaining * 1000))
            )

            # Wait for either code capture, navigation error, or timeout
            done, _ = await asyncio.wait(
                [code_future, nav_task],
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if code_future.done():
                return code_future.result()

            if nav_task in done:
                # Check if navigation failed with an error that isn't expected callback abort
                nav_exc = nav_task.exception()
                if nav_exc is not None and not code_future.done():
                    # If navigation failed because browser was closed or cancelled
                    if isinstance(nav_exc, PlaywrightError) and (
                        "closed" in str(nav_exc).lower()
                        or "target closed" in str(nav_exc).lower()
                    ):
                        raise OAuthError(
                            "Browser was closed before authorization completed."
                        ) from nav_exc
                    # Other navigation errors
                    logger.debug("Initial navigation exception: %s", nav_exc)

            # Continue waiting for code_future until deadline
            remaining = max(0.1, deadline - loop.time())
            try:
                return await asyncio.wait_for(code_future, timeout=remaining)
            except TimeoutError as exc:
                raise OAuthError(
                    f"OAuth authorization timed out after {timeout_seconds} seconds."
                ) from exc

        finally:
            if nav_task is not None:
                if not nav_task.done():
                    nav_task.cancel()
                try:
                    await nav_task
                except (asyncio.CancelledError, Exception) as nav_err:
                    logger.debug("Navigation task finished on close: %s", nav_err)
            if context is not None:
                try:
                    await context.close()
                except Exception as e:
                    logger.debug("Error closing browser context: %s", e)
            if browser is not None:
                try:
                    await browser.close()
                except Exception as e:
                    logger.debug("Error closing browser: %s", e)

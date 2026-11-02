"""CLI command canvas-mcp-auth for Canvas mobile OAuth authentication."""

import argparse
import asyncio
import getpass
import logging
import os
import secrets
import sys

import httpx

from canvas_mcp.auth.browser import capture_authorization_code
from canvas_mcp.auth.mobile import (
    build_authorization_url,
    exchange_authorization_code,
    extract_authorization_code,
    fetch_mobile_credentials,
    normalize_domain,
    verify_user_identity,
)
from canvas_mcp.auth.models import OAuthError
from canvas_mcp.auth.store import TokenStore

logger = logging.getLogger(__name__)


def _read_manual_input() -> str:
    try:
        return getpass.getpass(prompt="Callback URL: ")
    except EOFError as err:
        raise OAuthError(
            "End of input reached without receiving callback URL."
        ) from err


async def capture_code_manual(auth_url: str, state: str, timeout: float) -> str:
    """Prompt user locally on stderr for the full redirected callback URL."""
    sys.stderr.write(
        f"\nOpen the following URL in your browser to sign in:\n\n{auth_url}\n\n"
        "After signing in, paste the full redirected URL below.\n"
    )
    sys.stderr.flush()

    loop = asyncio.get_running_loop()
    try:
        redirect_url = await asyncio.wait_for(
            loop.run_in_executor(None, _read_manual_input),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise OAuthError(
            f"Manual authorization timed out after {timeout} seconds."
        ) from exc
    except (KeyboardInterrupt, SystemExit) as err:
        raise OAuthError("Manual authorization was cancelled.") from err

    if not redirect_url.strip():
        raise OAuthError("Empty callback URL provided.")

    return extract_authorization_code(redirect_url.strip(), state)


async def run_login(
    domain: str,
    *,
    manual: bool = False,
    timeout: float = 180.0,
    store: TokenStore | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Execute complete mobile OAuth login flow and persist tokens."""
    norm_domain = normalize_domain(domain)
    token_store = store or TokenStore()

    should_close_client = False
    if client is None:
        client = httpx.AsyncClient()
        should_close_client = True

    try:
        credentials = await fetch_mobile_credentials(norm_domain, client=client)
        state = secrets.token_urlsafe(32)
        auth_url = build_authorization_url(norm_domain, credentials.client_id, state)

        code: str
        if manual:
            code = await capture_code_manual(auth_url, state, timeout)
        else:
            try:
                code = await capture_authorization_code(
                    auth_url, state, timeout_seconds=timeout
                )
            except OAuthError as exc:
                err_msg = str(exc).lower()
                is_launch_failure = (
                    "playwright is not installed" in err_msg
                    or "failed to launch chromium" in err_msg
                )
                if is_launch_failure:
                    if sys.stdin.isatty():
                        sys.stderr.write(
                            f"\nBrowser launch unavailable ({exc}). Switching to manual login.\n"
                        )
                        code = await capture_code_manual(auth_url, state, timeout)
                    else:
                        sys.stderr.write(
                            f"\nBrowser launch unavailable ({exc}).\n"
                            "Run `canvas-mcp-auth login --manual` in an interactive terminal.\n"
                        )
                        raise
                else:
                    raise

        tokens = await exchange_authorization_code(
            norm_domain,
            credentials,
            code,
            client=client,
        )

        user = await verify_user_identity(
            norm_domain,
            tokens.access_token.get_secret_value(),
            expected_user=tokens.user,
            client=client,
        )
        tokens.user = user

        token_store.save(tokens)

        sys.stdout.write(
            f"Successfully authenticated with Canvas mobile OAuth.\n"
            f"Canvas host: {norm_domain}\n"
            f"User ID: {user.id}\n"
            f"Stored tokens: {token_store.path}\n\n"
            f"Configuration:\n"
            f"  Set CANVAS_API_URL=https://{norm_domain}/api/v1\n"
            f"  Warning: An existing nonempty CANVAS_API_TOKEN takes precedence over OAuth.\n"
            f"  Ensure CANVAS_API_TOKEN is unset or empty to use OAuth.\n"
            f"  Restart any running Canvas MCP server processes to apply.\n"
        )
        sys.stdout.flush()

    finally:
        if should_close_client and client is not None:
            await client.aclose()


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for canvas-mcp-auth."""
    parser = argparse.ArgumentParser(
        prog="canvas-mcp-auth",
        description="Canvas MCP OAuth authentication helper",
    )
    subparsers = parser.add_subparsers(dest="command")

    login_parser = subparsers.add_parser(
        "login", help="Log in to Canvas via mobile OAuth"
    )
    login_parser.add_argument(
        "--domain",
        help="Canvas domain or URL (e.g. canvas.example.edu or https://canvas.example.edu)",
    )
    login_parser.add_argument(
        "--manual",
        action="store_true",
        help="Perform manual authorization without launching a browser",
    )
    login_parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="Timeout in seconds for authorization (default: 180)",
    )

    args = parser.parse_args(argv)
    if args.command != "login":
        parser.print_help(sys.stderr)
        sys.exit(1)

    if args.timeout <= 0:
        sys.stderr.write("Error: --timeout must be positive seconds.\n")
        sys.exit(1)

    domain = args.domain or os.environ.get("CANVAS_API_URL")
    if not domain:
        sys.stderr.write(
            "Error: Domain not provided. Specify --domain or set CANVAS_API_URL in the environment.\n"
        )
        sys.exit(1)

    try:
        norm_domain = normalize_domain(domain)
    except ValueError as e:
        sys.stderr.write(f"Error: Invalid Canvas domain: {e}\n")
        sys.exit(1)

    try:
        asyncio.run(run_login(norm_domain, manual=args.manual, timeout=args.timeout))
    except OAuthError as e:
        sys.stderr.write(f"Authentication failed: {e}\n")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.stderr.write("\nAuthentication cancelled by user.\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Authentication failed: {type(e).__name__}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Canvas MCP Server

A Model Context Protocol server for Canvas LMS integration.
Provides educators and students with AI-powered tools for course management,
assignment handling, discussion facilitation, student analytics, and personal
academic tracking.

Supports two transport modes:
- stdio (default): Local process communication, credentials from .env
- streamable-http: HTTP server, per-request credentials via X-Canvas-Token/X-Canvas-URL headers
"""

import argparse
import asyncio
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from .core.config import get_config, validate_config
from .core.credentials import (
    RequestCredentials,
    clear_request_credentials,
    set_request_credentials,
)
from .core.logging import log_error, log_info, log_warning
from .resources import register_resources_and_prompts
from .tools import (
    register_accessibility_tools,
    register_assignment_tools,
    register_code_execution_tools,
    register_course_tools,
    register_discovery_tools,
    register_discussion_tools,
    register_file_tools,
    register_messaging_tools,
    register_module_tools,
    register_other_tools,
    register_page_tools,
    register_peer_review_comment_tools,
    register_peer_review_tools,
    register_rubric_tools,
    register_student_tools,
)


class CanvasCredentialMiddleware:
    """ASGI middleware that extracts Canvas credentials from HTTP headers.

    For each incoming HTTP request, reads X-Canvas-Token and X-Canvas-URL
    headers and sets them in the ContextVar so make_canvas_request uses
    the caller's credentials instead of the server's .env config.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            # Parse headers from ASGI scope (list of [name, value] byte pairs)
            headers = dict(scope.get("headers", []))
            token = headers.get(b"x-canvas-token", b"").decode()
            canvas_url = headers.get(b"x-canvas-url", b"").decode()

            if token and canvas_url:
                set_request_credentials(
                    RequestCredentials(api_token=token, api_url=canvas_url)
                )
            try:
                await self.app(scope, receive, send)
            finally:
                clear_request_credentials()
        else:
            # Passthrough for lifespan and other non-HTTP scopes
            await self.app(scope, receive, send)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    transport: str = "stdio",
) -> FastMCP:
    """Create and configure the Canvas MCP server."""
    config = get_config()
    kwargs: dict[str, Any] = {"name": config.mcp_server_name}
    if transport != "stdio":
        kwargs["host"] = host
        kwargs["port"] = port
    mcp = FastMCP(**kwargs)
    return mcp


def register_all_tools(mcp: FastMCP) -> None:
    """Register all MCP tools, resources, and prompts."""
    log_info("Registering Canvas MCP tools...")

    # Register tools by category
    register_course_tools(mcp)
    register_assignment_tools(mcp)
    register_discussion_tools(mcp)
    register_file_tools(mcp)
    register_module_tools(mcp)
    register_other_tools(mcp)
    register_page_tools(mcp)
    register_rubric_tools(mcp)
    register_peer_review_tools(mcp)
    register_peer_review_comment_tools(mcp)
    register_messaging_tools(mcp)
    register_student_tools(mcp)
    register_accessibility_tools(mcp)
    register_discovery_tools(mcp)
    register_code_execution_tools(mcp)

    # Register resources and prompts
    register_resources_and_prompts(mcp)

    log_info("All Canvas MCP tools registered successfully!")


async def _validate_token() -> tuple[bool, str]:
    """Validate the Canvas API token by calling /users/self.

    Returns:
        Tuple of (success, message). On success the message contains the
        authenticated user name; on failure it describes the error.
    """
    from .core.client import make_canvas_request

    try:
        response = await make_canvas_request("get", "/users/self")
        if isinstance(response, dict) and "error" in response:
            return (False, f"Token validation failed: {response['error']}")
        user_name = response.get("name", "Unknown") if isinstance(response, dict) else "Unknown"
        return (True, f"Authenticated as: {user_name}")
    except Exception as e:
        return (False, f"Token validation error: {type(e).__name__}: {e}")


def test_connection() -> bool:
    """Test the Canvas API connection."""
    log_info("Testing Canvas API connection...")

    try:
        async def test_api() -> bool:
            ok, message = await _validate_token()
            if ok:
                log_info(f"✓ API connection successful! {message}")
                return True
            else:
                log_error(message)
                return False

        return asyncio.run(test_api())

    except Exception as e:
        log_error("API test failed with exception", exc=e)
        return False


def main() -> None:
    """Main entry point for the Canvas MCP server."""
    parser = argparse.ArgumentParser(
        description="Canvas MCP Server - AI-powered Canvas LMS integration"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test Canvas API connection and exit"
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Show current configuration and exit"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol (default: stdio)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8819,
        help="Port for HTTP server (default: 8819)"
    )

    args = parser.parse_args()
    is_http = args.transport == "streamable-http"

    # In HTTP mode, .env credentials are optional (per-request auth instead)
    if not is_http:
        if not validate_config():
            log_error("Please check your .env file configuration")
            log_error("Use the env.template file as a reference")
            sys.exit(1)

    config = get_config()

    # Handle special commands
    if args.config:
        print("Canvas MCP Server Configuration:", file=sys.stderr)
        print(f"  Server Name: {config.mcp_server_name}", file=sys.stderr)
        print(f"  Transport: {args.transport}", file=sys.stderr)
        if is_http:
            print(f"  Host: {args.host}", file=sys.stderr)
            print(f"  Port: {args.port}", file=sys.stderr)
        else:
            print(f"  Canvas API URL: {config.canvas_api_url}", file=sys.stderr)
        print(f"  Debug Mode: {config.debug}", file=sys.stderr)
        print(f"  API Timeout: {config.api_timeout}s", file=sys.stderr)
        print(f"  Cache TTL: {config.cache_ttl}s", file=sys.stderr)
        sandbox_mode = config.ts_sandbox_mode
        if sandbox_mode not in {"auto", "local", "container"}:
            sandbox_mode = "auto"
        print(f"  Sandbox Enabled: {config.enable_ts_sandbox}", file=sys.stderr)
        if config.enable_ts_sandbox:
            print(f"  Sandbox Mode: {sandbox_mode}", file=sys.stderr)
            if config.ts_sandbox_timeout_sec > 0:
                print(
                    f"  Sandbox Timeout: {config.ts_sandbox_timeout_sec}s",
                    file=sys.stderr
                )
            if config.ts_sandbox_memory_limit_mb > 0:
                print(
                    f"  Sandbox Memory: {config.ts_sandbox_memory_limit_mb}MB",
                    file=sys.stderr
                )
            if config.ts_sandbox_cpu_limit > 0:
                print(
                    f"  Sandbox CPU Limit: {config.ts_sandbox_cpu_limit}s",
                    file=sys.stderr
                )
            if config.ts_sandbox_block_outbound_network:
                allowlist = config.ts_sandbox_allowlist_hosts or "canvas API only"
                print(
                    f"  Sandbox Network Allowlist: {allowlist}",
                    file=sys.stderr
                )
        if config.institution_name:
            print(f"  Institution: {config.institution_name}", file=sys.stderr)
        sys.exit(0)

    if args.test:
        if test_connection():
            log_info("All tests passed!")
            sys.exit(0)
        else:
            log_error("Connection test failed!")
            sys.exit(1)

    # Initialize audit logging (before any API calls)
    from .core.audit import init_audit_logging
    init_audit_logging()

    # Normal server startup
    if is_http:
        log_info(
            f"Starting Canvas MCP server in HTTP mode on {args.host}:{args.port}"
        )
        log_info("Credentials: per-request via X-Canvas-Token / X-Canvas-URL headers")
    else:
        log_info(f"Starting Canvas MCP server with API URL: {config.canvas_api_url}")

    if config.institution_name:
        log_info(f"Institution: {config.institution_name}")

    # Validate token on startup for stdio mode only
    if not is_http:
        try:
            ok, message = asyncio.run(_validate_token())
            if ok:
                log_info(f"✓ {message}")
            else:
                log_warning(
                    f"Token validation failed: {message}. "
                    "Check your CANVAS_API_TOKEN. Server will start anyway."
                )
        except Exception:
            log_warning(
                "Could not validate token on startup (network may be unavailable). "
                "Server will start anyway."
            )

    log_info("Use Ctrl+C to stop the server")

    # Create and configure server
    mcp = create_server(
        host=args.host, port=args.port, transport=args.transport
    )
    register_all_tools(mcp)

    try:
        if is_http:
            _run_http_server(mcp)
        else:
            mcp.run()
    except KeyboardInterrupt:
        log_info("\nShutting down server...")
    except Exception as e:
        log_error("Server error", exc=e)
        sys.exit(1)
    finally:
        # Cleanup HTTP client resources (stdio mode only — HTTP uses per-request clients)
        if not is_http:
            from .core.client import cleanup_http_client

            try:
                asyncio.run(cleanup_http_client())
            except RuntimeError:
                pass  # Event loop already closed — safe to ignore
        log_info("Server stopped")


def _run_http_server(mcp: FastMCP) -> None:
    """Run the MCP server with HTTP transport and credential middleware."""
    import uvicorn

    # Get the Starlette app from FastMCP, then wrap with credential middleware
    starlette_app = mcp.streamable_http_app()
    app = CanvasCredentialMiddleware(starlette_app)

    config = uvicorn.Config(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    import anyio

    anyio.run(server.serve)


if __name__ == "__main__":
    main()

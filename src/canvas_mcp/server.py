#!/usr/bin/env python3
"""
Canvas MCP Server

A Model Context Protocol server for Canvas LMS integration.
Provides educators and students with AI-powered tools for course management,
assignment handling, discussion facilitation, student analytics, and personal
academic tracking.

Supports two transport modes:
- stdio (default): Local process communication, credentials from .env
- streamable-http: HTTP server, per-request token via X-Canvas-Token header;
  the Canvas API URL is pinned by server config (CANVAS_API_URL), not the client.
"""

import argparse
import asyncio
import base64
import hmac
import json
import sys
import time
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP

from .core.config import get_config, validate_config
from .core.credentials import (
    RequestCredentials,
    clear_http_request_context,
    set_http_request_active,
    set_request_credentials,
)
from .core.logging import log_error, log_info, log_warning
from .resources import register_resources_and_prompts
from .tools import (
    register_accessibility_tools,
    register_admin_tools,
    register_code_execution_tools,
    register_course_tools,
    register_discovery_tools,
    register_educator_assignment_tools,
    register_educator_discussion_tools,
    register_educator_file_tools,
    register_educator_messaging_tools,
    register_educator_module_tools,
    register_educator_page_crud_tools,
    register_enrollment_tools,
    register_page_tools,
    register_peer_review_comment_tools,
    register_peer_review_tools,
    register_rubric_tools,
    register_shared_assignment_tools,
    register_shared_content_tools,
    register_shared_discussion_tools,
    register_shared_file_tools,
    register_shared_messaging_tools,
    register_shared_module_tools,
    register_student_tools,
)


async def _send_json_error(send: Any, status: int, message: str) -> None:
    """Emit a minimal ASGI JSON error response (used to fail closed)."""
    body = json.dumps({"error": message}).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": body})


async def _read_body(receive) -> bytes:
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body", False):
            break
    return body


def _access_key_ok(presented: str, allowed: frozenset[str]) -> bool:
    """Constant-time check of a presented access key against the allowed set."""
    if not presented:
        return False
    # compare_digest against each key; the any() still runs every comparison's
    # constant-time op, avoiding early-exit timing leaks on the matched key.
    return any(hmac.compare_digest(presented, key) for key in allowed)


def _client_principal_id(headers: dict[bytes, bytes]) -> str | None:
    """Read the Entra object id from Azure App Service's injected identity header.

    ``X-MS-CLIENT-PRINCIPAL-ID`` is set by the App Service auth layer *after* it
    validates the token; external callers cannot spoof it (the platform strips
    inbound ``X-MS-*`` headers). Empty/absent → ``None``.
    """
    pid = headers.get(b"x-ms-client-principal-id", b"").decode("utf-8", errors="ignore").strip()
    return pid or None


def _client_principal_claims(headers: dict[bytes, bytes]) -> dict[str, str]:
    """Decode the base64 JSON ``X-MS-CLIENT-PRINCIPAL`` header into a claim map.

    The header is ``{"claims": [{"typ": ..., "val": ...}, ...]}``. Returns an
    empty dict on any parse failure (used only for audit context, never auth).
    """
    raw = headers.get(b"x-ms-client-principal", b"")
    if not raw:
        return {}
    try:
        payload = json.loads(base64.b64decode(raw))
        return {
            c["typ"]: c["val"]
            for c in payload.get("claims", [])
            if "typ" in c and "val" in c
        }
    except Exception:
        return {}


_ADMIN_APPROVE_PATH = "/admin/access/approve"
_ADMIN_CONFIRM_PATH = "/admin/access/confirm"


_overlay_store = None


def _access_store(config):
    """Build the overlay store once and reuse it across requests.

    The store's ``is_granted`` TTL cache is per-instance, so it only works if
    the instance survives between requests — rebuilding per request also re-ran
    ``create_table_if_not_exists`` and a fresh credential/client every time.
    Returns None until it can be built (feature off / azure unavailable), and
    retries on the next call so a transient build failure self-heals.
    """
    global _overlay_store
    if _overlay_store is None:
        from .core.access.factory import build_store
        _overlay_store = build_store(config)
    return _overlay_store


def _schedule_notify(config, store, requester) -> None:
    """Fire-and-forget admin email; never blocks or breaks the request path."""
    from .core.access.factory import build_email_sender
    from .core.access.notify import notify_access_request
    sender = build_email_sender(config)
    if sender is None:
        return
    now = int(time.time())
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    asyncio.create_task(notify_access_request(
        store=store, requester=requester, secret=config.access_token_secret,
        approve_base_url=config.access_approve_base_url,
        admin_emails=config.access_admin_emails,
        cooldown_hours=config.access_notify_cooldown_hours,
        ttl_seconds=24 * 3600, send_email=sender,
        jti=uuid.uuid4().hex, now=now, now_iso=now_iso))


class CanvasCredentialMiddleware:
    """ASGI middleware that extracts the caller's Canvas token from headers.

    For each incoming HTTP request, reads X-Canvas-Token and combines it with
    the server-pinned CANVAS_API_URL so make_canvas_request uses the caller's
    own Canvas token instead of any server .env token.

    Fail-closed semantics:
    - When MCP_ACCESS_KEYS is configured, a missing/invalid X-MCP-Access-Key
      returns HTTP 401 before anything else (the v1 multi-user gate).
    - A missing/blank X-Canvas-Token returns HTTP 401 before the app runs.
    - X-Canvas-URL is ignored (logged); the Canvas API URL is never
      client-controlled, which removes the SSRF surface entirely.
    - The "HTTP request active" marker is set so downstream code refuses to
      fall back to the server's own credentials.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            # Passthrough for lifespan and other non-HTTP scopes
            await self.app(scope, receive, send)
            return

        config = get_config()
        path = scope.get("path", "")

        # --- Admin access-approval routes (intercepted before any token gate) ---
        if path in (_ADMIN_APPROVE_PATH, _ADMIN_CONFIRM_PATH):
            from .core.access.factory import feature_ready
            if not (config.access_request_enabled and feature_ready(config)):
                await _send_json_error(send, 404, "Not found")
                return
            store = _access_store(config)
            if store is None:
                await _send_json_error(send, 503, "Access service unavailable")
                return
            from .core.access import routes
            now = int(time.time())
            if path == _ADMIN_APPROVE_PATH:
                await routes.handle_approve(scope.get("query_string", b""), send,
                                            store=store, secret=config.access_token_secret, now=now)
            else:
                body = await _read_body(receive)
                await routes.handle_confirm(body, send, store=store,
                                            secret=config.access_token_secret, now=now)
            return

        set_http_request_active(True)
        try:
            # Parse headers from ASGI scope (list of [name, value] byte pairs)
            headers = dict(scope.get("headers", []))

            if config.entra_auth_enabled:
                # Entra platform-auth path: Azure App Service has already validated
                # the bearer token and (for unauthenticated callers) emitted the
                # 401 + RFC 9728 challenge before we ran. Here we enforce the
                # per-identity allowlist + audit on the trusted injected header.
                # Student records are FERPA "Sensitive" — fail closed if the
                # platform identity is absent (defense-in-depth) or not allowlisted.
                oid = _client_principal_id(headers)
                if not oid:
                    await _send_json_error(send, 401, "Missing verified Entra identity")
                    return
                in_env = oid in config.mcp_entra_allowed_oids
                in_overlay = False
                store = None
                if not in_env and config.access_request_enabled:
                    store = _access_store(config)
                    in_overlay = store.is_granted(oid) if store else False
                if config.mcp_entra_allowed_oids and not (in_env or in_overlay):
                    # Send the deny FIRST, so scheduling the access-request email
                    # can never delay or break the 403 (auth boundary: respond,
                    # then notify). The notify is additionally guarded so a
                    # scheduling error degrades to "no email", never a dropped 403.
                    await _send_json_error(send, 403, "Identity not authorized for this MCP server")
                    if config.access_request_enabled and store is not None:
                        try:
                            claims_for_req = _client_principal_claims(headers)
                            from .core.access.store import Requester
                            requester = Requester(
                                oid=oid,
                                upn=claims_for_req.get("preferred_username")
                                or claims_for_req.get("upn", ""),
                                display_name=claims_for_req.get("name", ""))
                            _schedule_notify(config, store, requester)
                        except Exception as exc:
                            log_error(f"access-request notify scheduling failed: {exc}")
                    return
                claims = _client_principal_claims(headers)
                # Log only the stable, opaque identifiers (oid GUID, scope, client
                # app id) — NOT X-MS-CLIENT-PRINCIPAL-NAME, which is the user's
                # UPN/email and would write PII to the app log on every request,
                # bypassing LOG_REDACT_PII. Per-user audit attribution uses the oid;
                # the dedicated audit logger (core.audit) handles richer events.
                log_info(
                    "MCP request authorized via Entra identity",
                    entra_oid=oid,
                    entra_scp=claims.get("scp")
                    or claims.get("http://schemas.microsoft.com/identity/claims/scope"),
                    entra_azp=claims.get("azp") or claims.get("appid"),
                )
            else:
                # v1 access-key gate (when configured): reject before touching creds.
                allowed_keys = config.mcp_access_keys
                if allowed_keys:
                    presented = headers.get(b"x-mcp-access-key", b"").decode("utf-8", errors="ignore").strip()
                    if not _access_key_ok(presented, allowed_keys):
                        await _send_json_error(send, 401, "Invalid or missing X-MCP-Access-Key")
                        return

            token = headers.get(b"x-canvas-token", b"").decode("utf-8", errors="ignore").strip()

            if b"x-canvas-url" in headers:
                log_warning("Ignoring X-Canvas-URL header; Canvas API URL is server-pinned")

            if not token:
                await _send_json_error(send, 401, "Missing X-Canvas-Token header")
                return

            canvas_url = config.canvas_api_url.strip()
            if not canvas_url:
                log_error("CANVAS_API_URL is required in HTTP mode but is not configured")
                await _send_json_error(send, 500, "Server Canvas API URL is not configured")
                return

            set_request_credentials(
                RequestCredentials(api_token=token, api_url=canvas_url)
            )
            await self.app(scope, receive, send)
        finally:
            clear_http_request_context()


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


def register_all_tools(mcp: FastMCP, role: str = "all") -> None:
    """Register MCP tools based on the selected role profile.

    Args:
        mcp: FastMCP server instance
        role: One of "student", "educator", or "all" (default)
    """
    log_info(f"Registering Canvas MCP tools (role: {role})...")

    # Shared tools — always registered for all roles
    register_course_tools(mcp)
    register_shared_content_tools(mcp)
    register_shared_assignment_tools(mcp)
    register_shared_discussion_tools(mcp)
    register_shared_module_tools(mcp)
    register_shared_file_tools(mcp)
    register_shared_messaging_tools(mcp)
    register_discovery_tools(mcp)

    # Student-specific tools
    if role in ("student", "all"):
        register_student_tools(mcp)

    # Educator-specific tools
    if role in ("educator", "all"):
        register_educator_assignment_tools(mcp)
        register_educator_discussion_tools(mcp)
        register_educator_module_tools(mcp)
        register_educator_file_tools(mcp)
        register_page_tools(mcp)
        register_educator_page_crud_tools(mcp)
        register_rubric_tools(mcp)
        register_peer_review_tools(mcp)
        register_peer_review_comment_tools(mcp)
        register_educator_messaging_tools(mcp)
        register_accessibility_tools(mcp)
        register_enrollment_tools(mcp)  # requires teacher-scoped roster access
        if get_config().execute_typescript_enabled:
            register_code_execution_tools(mcp)
        register_admin_tools(mcp)

    # Resources and prompts — always registered
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


def _cmd_list_grants(args) -> int:
    """List self-service access grants from the overlay store. Returns an exit code."""
    store = _access_store(get_config())
    if store is None:
        print("Access store unavailable (check ACCESS_* config + az login).")
        return 1
    grants = store.list_grants()
    if not grants:
        print("No self-service grants.")
        return 0
    for g in grants:
        print(f"{g.oid}\t{g.display_name}\t{g.upn}\t{g.granted_utc}")
    return 0


def _cmd_revoke(args) -> int:
    """Revoke one self-service access grant by Entra OID. Returns an exit code."""
    store = _access_store(get_config())
    if store is None:
        print("Access store unavailable (check ACCESS_* config + az login).")
        return 1
    if store.revoke(args.revoke):
        print(f"revoked {args.revoke}")
        return 0
    print(f"oid not found: {args.revoke}")
    return 1


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
    parser.add_argument(
        "--role",
        choices=["student", "educator", "all"],
        default=None,
        help="Tool profile: student (~31 tools), educator (~86 tools), all (default: all)"
    )
    parser.add_argument(
        "--list-grants",
        action="store_true",
        help="List self-service access grants (hosted; needs az login) and exit"
    )
    parser.add_argument(
        "--revoke",
        metavar="OID",
        help="Revoke a self-service access grant by Entra OID and exit"
    )

    args = parser.parse_args()
    is_http = args.transport == "streamable-http"

    config = get_config()

    # Admin access-approval commands talk only to the overlay store (Azure, via
    # az login) — not Canvas — so dispatch them before the Canvas-credential /
    # HTTP-mode validation below, which they don't need.
    if args.list_grants:
        raise SystemExit(_cmd_list_grants(args))
    if args.revoke:
        raise SystemExit(_cmd_revoke(args))

    # HTTP mode: the Canvas URL is server-pinned and per-user tokens arrive via
    # X-Canvas-Token. A server token must NOT be set, or a missing request token
    # could silently fall back to it (mis-attributing actions to the operator).
    if is_http:
        if not config.canvas_api_url:
            log_error("CANVAS_API_URL is required in HTTP mode (the Canvas API URL is server-pinned)")
            sys.exit(1)
        if config.canvas_api_token:
            log_error(
                "CANVAS_API_TOKEN must NOT be set in HTTP mode — clients supply their "
                "own token via the X-Canvas-Token header. Unset it and restart."
            )
            sys.exit(1)
        if config.entra_auth_enabled and not config.mcp_allow_unauthenticated:
            # Entra platform-auth trusts the X-MS-CLIENT-PRINCIPAL-ID header, which
            # is ONLY safe when Azure App Service auth actually fronts the endpoint
            # (it strips client-supplied X-MS-* headers). The app can't detect that
            # at runtime, so the operator must assert it explicitly — otherwise a
            # caller could forge the identity header and bypass auth. Require the
            # external-auth opt-in regardless of any (now-ignored) MCP_ACCESS_KEYS.
            log_error(
                "ENTRA_AUTH_ENABLED=true requires MCP_ALLOW_UNAUTHENTICATED=true — an "
                "explicit acknowledgment that an external authenticator (Azure App "
                "Service / Entra) fronts this endpoint and injects the trusted "
                "X-MS-CLIENT-PRINCIPAL identity. Refusing to start: without that "
                "platform, the identity header is client-spoofable."
            )
            sys.exit(1)
        if not config.entra_auth_enabled and not config.mcp_access_keys:
            # Secure-by-default: refuse to start an ungated endpoint unless the
            # operator has explicitly accepted that external auth fronts it.
            # Student education records are FERPA "Sensitive" data (U of I DAT01)
            # and must never be accessed without specific authorization, so a
            # silent fail-open here is a compliance failure, not a warning.
            if config.mcp_allow_unauthenticated:
                log_warning(
                    "HTTP mode has no MCP_ACCESS_KEYS, but MCP_ALLOW_UNAUTHENTICATED=true "
                    "is set — assuming external authentication (e.g. Entra/Easy Auth) "
                    "fronts this endpoint. The app-level key gate is DISABLED."
                )
            else:
                log_error(
                    "HTTP mode requires MCP_ACCESS_KEYS (the app-level auth gate). "
                    "Refusing to start an unauthenticated endpoint that can read and "
                    "write Canvas gradebooks. Set MCP_ACCESS_KEYS, or if an external "
                    "authenticator (Entra/Easy Auth) fronts this endpoint, set "
                    "MCP_ALLOW_UNAUTHENTICATED=true to opt in deliberately."
                )
                sys.exit(1)
    else:
        # stdio mode: .env credentials are required (single-user, env-based auth)
        if not validate_config():
            log_error("Please check your .env file configuration")
            log_error("Use the env.template file as a reference")
            sys.exit(1)

    # Handle special commands
    if args.config:
        print("Canvas MCP Server Configuration:", file=sys.stderr)
        print(f"  Server Name: {config.mcp_server_name}", file=sys.stderr)
        print(f"  Transport: {args.transport}", file=sys.stderr)
        resolved_role = args.role or config.canvas_role
        print(f"  Tool Profile: {resolved_role}", file=sys.stderr)
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
        log_info("Credentials: per-request via X-Canvas-Token header; Canvas API URL is server-pinned")
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
        finally:
            # asyncio.run() creates and immediately closes its own event loop.
            # Any global httpx client or asyncio semaphore created during token
            # validation is now bound to that closed loop.  Reset them so they
            # are recreated fresh inside the event loop that mcp.run() starts.
            from .core import client as _client_module
            _client_module.http_client = None
            _client_module._http_client_loop_ref = None
            _client_module._request_semaphore = None
            _client_module._semaphore_loop_ref = None

    log_info("Use Ctrl+C to stop the server")

    # Create and configure server
    mcp = create_server(
        host=args.host, port=args.port, transport=args.transport
    )
    # Resolve role: CLI flag > env var > default
    role = args.role or config.canvas_role
    if role not in ("student", "educator", "all"):
        log_warning(f"Unknown role '{role}', defaulting to 'all'")
        role = "all"
    # Make the resolved role authoritative so runtime tool behavior (e.g.
    # list_courses reading get_config().canvas_role) matches the registered
    # profile even when the CLI --role flag overrides the CANVAS_ROLE env var.
    config.canvas_role = role
    log_info(f"Tool profile: {role}")
    register_all_tools(mcp, role=role)

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

"""Configuration management for Canvas MCP server."""

import os
import re
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv

from .logging import log_error, log_info, log_warning

# Load environment variables from .env file
load_dotenv()

_INVALID_INT_ENV_VARS: dict[str, str] = {}
_INVALID_FLOAT_ENV_VARS: dict[str, str] = {}

VALID_SANDBOX_MODES = frozenset({"auto", "local", "container"})


def _parse_keys(raw: str) -> frozenset[str]:
    """Parse a comma/whitespace-separated list of access keys into a set."""
    if not raw:
        return frozenset()
    return frozenset(k for k in raw.replace(",", " ").split() if k)


def _normalize_canvas_url(raw: str) -> str:
    """Normalize ``CANVAS_API_URL`` to the canonical ``…/api/v1`` form.

    Canvas REST endpoints live under ``/api/v1``. Users frequently enter just
    the base host (e.g. ``https://canvas.school.edu``); requests without the
    suffix make Canvas issue a 302 redirect to SSO login, which surfaces as a
    misleading ``HTTP error: 302`` that looks like a bad token. Canonicalize
    the path to exactly ``/api/v1`` (dropping any extra segments copied from a
    browser, plus stray query strings / fragments) so all of these resolve to
    the same URL:

    - ``https://canvas.school.edu``             → ``https://canvas.school.edu/api/v1``
    - ``https://canvas.school.edu/``            → ``https://canvas.school.edu/api/v1``
    - ``https://canvas.school.edu/api/v1``      → unchanged
    - ``https://canvas.school.edu/api/v1/``     → ``https://canvas.school.edu/api/v1``
    - ``https://canvas.school.edu/api/v1/foo``  → ``https://canvas.school.edu/api/v1``
    - ``https://canvas.school.edu/api/v1?x=1``  → ``https://canvas.school.edu/api/v1``

    An explicit ``/api/v<N>`` version segment is preserved (only trailing
    sub-paths after it are dropped), so a deliberately-set ``/api/v2`` is never
    silently downgraded to ``/api/v1``.

    A scheme-less input (e.g. ``canvas.school.edu``) is returned unchanged so
    ``validate_config()`` can flag the missing ``https://`` rather than this
    silently producing a relative-path URL.
    """
    url = raw.strip()
    if not url:
        return ""

    parsed = urlparse(url)
    # Without a scheme, urlparse puts the host in ``path`` and leaves
    # ``netloc`` empty — we can't reliably rebuild it, so leave it for the
    # validator to warn about.
    if not parsed.scheme or not parsed.netloc:
        return url

    # Preserve an existing ``/api/v<N>`` version segment (truncating any extra
    # path after it), matching only at a segment boundary so a real version
    # like ``/api/v2`` is kept rather than rewritten. When the path carries no
    # version segment, append the canonical ``/api/v1``.
    version = re.search(r"/api/v\d+(?=/|$)", parsed.path)
    path = parsed.path[: version.end()] if version else "/api/v1"
    return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() == "true"


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        _INVALID_INT_ENV_VARS[name] = value
        return default


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = float(value)
    except ValueError:
        _INVALID_FLOAT_ENV_VARS[name] = value
        return default
    if parsed <= 0:
        _INVALID_FLOAT_ENV_VARS[name] = value
        return default
    return parsed


class Config:
    """Configuration class for Canvas MCP server."""

    def __init__(self) -> None:
        # Required configuration
        self.canvas_api_token = os.getenv("CANVAS_API_TOKEN", "")
        # Keep the configured (pre-normalization) value so validate_config()
        # can report the normalization delta from the same read that produced
        # canvas_api_url. Whitespace-trimmed, matching the normalizer's input.
        self.canvas_api_url_configured = os.getenv("CANVAS_API_URL", "").strip()
        self.canvas_api_url = _normalize_canvas_url(self.canvas_api_url_configured)

        # Optional configuration with defaults
        self.mcp_server_name = os.getenv("MCP_SERVER_NAME", "canvas-api")
        self.debug = _bool_env("DEBUG", False)
        self.api_timeout = _int_env("API_TIMEOUT", 30)
        self.cache_ttl = _int_env("CACHE_TTL", 300)
        self.max_concurrent_requests = _int_env("MAX_CONCURRENT_REQUESTS", 10)
        self.read_file_max_size_mb = _float_env("READ_FILE_MAX_SIZE_MB", 100.0)

        # Development configuration
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_api_requests = _bool_env("LOG_API_REQUESTS", False)

        # Privacy and security configuration
        self.enable_data_anonymization = _bool_env("ENABLE_DATA_ANONYMIZATION", True)
        self.anonymization_debug = _bool_env("ANONYMIZATION_DEBUG", False)
        self.log_redact_pii = _bool_env("LOG_REDACT_PII", True)

        # Audit logging configuration
        self.log_access_events = _bool_env("LOG_ACCESS_EVENTS", False)
        self.log_execution_events = _bool_env("LOG_EXECUTION_EVENTS", False)
        self.audit_log_dir = os.getenv("AUDIT_LOG_DIR", "")

        # Code execution sandbox configuration (secure defaults)
        self.enable_ts_sandbox = _bool_env("ENABLE_TS_SANDBOX", True)
        self.ts_sandbox_mode = os.getenv("TS_SANDBOX_MODE", "auto").lower()
        self.ts_sandbox_block_outbound_network = _bool_env("TS_SANDBOX_BLOCK_OUTBOUND_NETWORK", True)
        self.ts_sandbox_allowlist_hosts = os.getenv("TS_SANDBOX_ALLOWLIST_HOSTS", "")
        self.ts_sandbox_cpu_limit = _int_env("TS_SANDBOX_CPU_LIMIT", 30)
        self.ts_sandbox_memory_limit_mb = _int_env("TS_SANDBOX_MEMORY_LIMIT_MB", 512)
        self.ts_sandbox_timeout_sec = _int_env("TS_SANDBOX_TIMEOUT_SEC", 120)
        self.ts_sandbox_container_image = os.getenv("TS_SANDBOX_CONTAINER_IMAGE", "node:20-alpine")

        # Code execution kill switch — set EXECUTE_TYPESCRIPT_ENABLED=false to
        # disable the execute_typescript tool without changing CANVAS_ROLE.
        self.execute_typescript_enabled = _bool_env("EXECUTE_TYPESCRIPT_ENABLED", True)

        # HTTP access-key gate (v1, multi-user). Comma- or whitespace-separated
        # list of accepted keys; an HTTP caller must present a matching
        # X-MCP-Access-Key header. Empty disables the gate (rely on external
        # auth). stdio mode ignores this entirely.
        self.mcp_access_keys = _parse_keys(os.getenv("MCP_ACCESS_KEYS", ""))

        # Secure-by-default: in HTTP mode, an unconfigured key gate makes the
        # server exit unless the operator EXPLICITLY opts into unauthenticated
        # mode (i.e. external auth such as Entra/Easy Auth fronts the endpoint).
        # This makes "fail open" impossible by omission — only by declaration.
        self.mcp_allow_unauthenticated = _bool_env("MCP_ALLOW_UNAUTHENTICATED", False)

        # Entra ID platform auth: when the endpoint is fronted by Azure App
        # Service authentication, the platform validates the Entra token and
        # injects a trusted X-MS-CLIENT-PRINCIPAL(-ID) identity header. The app
        # reads that for per-identity authorization + audit (the token is already
        # validated upstream). Gate behind a flag so local/stdio runs never trust
        # the spoofable X-MS-* headers. mcp_entra_allowed_oids is the allowlist of
        # Entra object IDs permitted to use this server (empty = allow any
        # platform-authenticated identity).
        self.entra_auth_enabled = _bool_env("ENTRA_AUTH_ENABLED", False)
        self.mcp_entra_allowed_oids = _parse_keys(os.getenv("MCP_ENTRA_ALLOWED_OIDS", ""))

        # --- Self-service access-approval flow (hosted-only; off by default) ---
        # Feature flag. When false (default) the gate behaves exactly as before
        # and the /admin/access/* routes 404. See internal access-approval spec.
        self.access_request_enabled = _bool_env("ACCESS_REQUEST_ENABLED", False)
        # Azure Table Storage overlay (managed-identity auth; no keys).
        self.access_table_account = os.getenv("ACCESS_TABLE_ACCOUNT", "")
        self.access_table_name = os.getenv("ACCESS_TABLE_NAME", "accessoverlay")
        # Azure Communication Services email.
        self.acs_endpoint = os.getenv("ACS_ENDPOINT", "")
        self.acs_sender = os.getenv("ACS_SENDER", "")
        # Admin notification recipients (comma/space separated).
        self.access_admin_emails = [
            e.strip()
            for e in os.getenv("ACCESS_ADMIN_EMAILS", "").replace(",", " ").split()
            if e.strip()
        ]
        # Public base URL used to build approval links (no trailing slash).
        self.access_approve_base_url = os.getenv("ACCESS_APPROVE_BASE_URL", "").rstrip("/")
        # HMAC secret for approval tokens; empty disables the feature (fail-closed).
        self.access_token_secret = os.getenv("ACCESS_TOKEN_SECRET", "")
        # Suppress re-emailing the admin for the same OID within this window.
        self.access_notify_cooldown_hours = _int_env("ACCESS_NOTIFY_COOLDOWN_HOURS", 24)

        # Optional metadata
        self.institution_name = os.getenv("INSTITUTION_NAME", "")
        self.timezone = os.getenv("TIMEZONE", "UTC")

        # Role-based tool filtering
        self.canvas_role = os.getenv("CANVAS_ROLE", "all").lower()


# Global configuration instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """Discard the cached configuration singleton.

    The next ``get_config()`` call rebuilds it from the current environment.
    Used by tests that patch environment variables so they don't read stale
    config captured at first access.

    Also clears the invalid-env-var caches, which are populated during
    ``Config.__init__`` and read by ``validate_config()``; otherwise a stale
    entry from a prior parse would produce a warning inconsistent with the
    rebuilt configuration's environment.

    Scope: this resets the config singleton only. Derived state built from
    config elsewhere is **not** reset here — notably the stdio HTTP client in
    ``core.client``, which captures the ``Authorization`` token at creation and
    is reused until its event loop closes. A caller rotating ``CANVAS_API_TOKEN``
    at runtime must also ``await cleanup_http_client()`` so the next request
    rebuilds the client with the new credentials. (Tests mock the request layer,
    and HTTP-transport mode uses per-request clients, so neither is affected.)
    """
    global _config
    _config = None
    _INVALID_INT_ENV_VARS.clear()
    _INVALID_FLOAT_ENV_VARS.clear()


def validate_config() -> bool:
    """Validate that required configuration is present."""
    config = get_config()
    unimplemented_env_vars = {
        "TOKEN_STORAGE_BACKEND": "token storage backend selection is not enforced yet",
        "TOKEN_ENVELOPE_KEY_SOURCE": "token envelope encryption is not enforced yet",
        "MCP_CLIENT_AUTH_MODE": "MCP client authentication is not implemented for stdio transport",
        "MCP_CLIENT_API_KEY_REQUIRED": "MCP client authentication is not implemented for stdio transport",
        "MCP_CLIENT_CERT_AUTHORITY": "MCP client authentication is not implemented for stdio transport",
        "LOG_ROTATION_DAYS": "log rotation is not enforced yet",
        "LOG_RETENTION_DAYS": "log retention is not enforced yet",
        "LOG_DESTINATION": "log destinations are not configurable yet",
        "SIEM_FORWARDING_ENABLED": "SIEM forwarding is not implemented yet",
        "MCP_BIND_HOST": "MCP uses stdio transport and does not bind network sockets",
        "MCP_BIND_PORT": "MCP uses stdio transport and does not bind network sockets",
        "FIREWALL_HINT": "firewall hints are documentation-only",
    }

    if not config.canvas_api_token:
        log_error("CANVAS_API_TOKEN environment variable is required")
        log_error("Please set CANVAS_API_TOKEN in your .env file")
        return False

    if not config.canvas_api_url:
        log_error("CANVAS_API_URL environment variable is required")
        log_error("Please set CANVAS_API_URL in your .env file")
        return False

    # Diagnose a CANVAS_API_URL that can't reach Canvas. The triple-slash case
    # (e.g. 'https:///host') is the subtle one: it has a scheme but an empty
    # netloc, so the normalizer leaves it untouched. Report the specific defect
    # rather than a one-size-fits-all message.
    parsed_url = urlparse(config.canvas_api_url)
    if parsed_url.scheme not in ("http", "https"):
        log_warning(
            "CANVAS_API_URL should start with 'https://'",
            current_url=config.canvas_api_url,
        )
    elif not parsed_url.netloc:
        log_warning(
            "CANVAS_API_URL is missing a hostname",
            current_url=config.canvas_api_url,
        )
    elif parsed_url.scheme != "https":
        log_warning(
            "CANVAS_API_URL should use the 'https://' scheme",
            current_url=config.canvas_api_url,
        )

    if (
        config.canvas_api_url_configured
        and config.canvas_api_url_configured != config.canvas_api_url
    ):
        log_info(
            "CANVAS_API_URL normalized to canonical form",
            configured=config.canvas_api_url_configured,
            effective=config.canvas_api_url,
        )

    if config.ts_sandbox_mode not in VALID_SANDBOX_MODES:
        log_warning(
            "TS_SANDBOX_MODE should be one of auto, local, container; "
            f"defaulting to 'auto' (got '{config.ts_sandbox_mode}')"
        )

    valid_roles = ("student", "educator", "all")
    if config.canvas_role not in valid_roles:
        log_warning(
            f"CANVAS_ROLE should be one of {', '.join(valid_roles)}; "
            f"defaulting to 'all' (got '{config.canvas_role}')"
        )
        config.canvas_role = "all"

    for env_name, env_value in _INVALID_INT_ENV_VARS.items():
        log_warning(
            f"{env_name} expects an integer; using default value "
            f"(got '{env_value}')"
        )

    for env_name, env_value in _INVALID_FLOAT_ENV_VARS.items():
        log_warning(
            f"{env_name} expects a positive number; using default value "
            f"(got '{env_value}')"
        )

    for env_name, note in unimplemented_env_vars.items():
        if os.getenv(env_name):
            log_warning(f"{env_name} is set but {note}.")

    return True

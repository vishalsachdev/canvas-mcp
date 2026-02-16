"""Configuration management for Canvas MCP server."""

import os
import sys

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

_INVALID_INT_ENV_VARS: dict[str, str] = {}


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


class Config:
    """Configuration class for Canvas MCP server."""

    def __init__(self) -> None:
        # Required configuration
        self.canvas_api_token = os.getenv("CANVAS_API_TOKEN", "")
        self.canvas_api_url = os.getenv("CANVAS_API_URL", "https://canvas.illinois.edu/api/v1")

        # Optional configuration with defaults
        self.mcp_server_name = os.getenv("MCP_SERVER_NAME", "canvas-api")
        self.debug = _bool_env("DEBUG", False)
        self.api_timeout = _int_env("API_TIMEOUT", 30)
        self.cache_ttl = _int_env("CACHE_TTL", 300)
        self.max_concurrent_requests = _int_env("MAX_CONCURRENT_REQUESTS", 10)

        # Development configuration
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_api_requests = _bool_env("LOG_API_REQUESTS", False)

        # Privacy and security configuration
        self.enable_data_anonymization = _bool_env("ENABLE_DATA_ANONYMIZATION", True)
        self.anonymization_debug = _bool_env("ANONYMIZATION_DEBUG", False)
        self.log_redact_pii = _bool_env("LOG_REDACT_PII", True)

        # Code execution sandbox configuration (best-effort by default)
        self.enable_ts_sandbox = _bool_env("ENABLE_TS_SANDBOX", False)
        self.ts_sandbox_mode = os.getenv("TS_SANDBOX_MODE", "auto").lower()
        self.ts_sandbox_block_outbound_network = _bool_env("TS_SANDBOX_BLOCK_OUTBOUND_NETWORK", False)
        self.ts_sandbox_allowlist_hosts = os.getenv("TS_SANDBOX_ALLOWLIST_HOSTS", "")
        self.ts_sandbox_cpu_limit = _int_env("TS_SANDBOX_CPU_LIMIT", 0)
        self.ts_sandbox_memory_limit_mb = _int_env("TS_SANDBOX_MEMORY_LIMIT_MB", 0)
        self.ts_sandbox_timeout_sec = _int_env("TS_SANDBOX_TIMEOUT_SEC", 0)
        self.ts_sandbox_container_image = os.getenv("TS_SANDBOX_CONTAINER_IMAGE", "node:20-alpine")

        # Optional metadata
        self.institution_name = os.getenv("INSTITUTION_NAME", "")
        self.timezone = os.getenv("TIMEZONE", "UTC")

    @property
    def api_base_url(self) -> str:
        """Legacy compatibility for API_BASE_URL."""
        return self.canvas_api_url

    @property
    def api_token(self) -> str:
        """Legacy compatibility for API_TOKEN."""
        return self.canvas_api_token


# Global configuration instance
_config: Config | None = None


def get_config() -> Config:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


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
        "LOG_ACCESS_EVENTS": "access/audit logging is not implemented yet",
        "LOG_EXECUTION_EVENTS": "execution event logging is not implemented yet",
        "LOG_RETENTION_DAYS": "log retention is not enforced yet",
        "LOG_DESTINATION": "log destinations are not configurable yet",
        "SIEM_FORWARDING_ENABLED": "SIEM forwarding is not implemented yet",
        "MCP_BIND_HOST": "MCP uses stdio transport and does not bind network sockets",
        "MCP_BIND_PORT": "MCP uses stdio transport and does not bind network sockets",
        "FIREWALL_HINT": "firewall hints are documentation-only",
    }

    if not config.canvas_api_token:
        print("Error: CANVAS_API_TOKEN environment variable is required", file=sys.stderr)
        print("Please set it to your Canvas API token in your .env file", file=sys.stderr)
        return False

    if not config.canvas_api_url:
        print("Error: CANVAS_API_URL environment variable is required", file=sys.stderr)
        print("Please set it to your Canvas API URL in your .env file", file=sys.stderr)
        return False

    if not config.canvas_api_url.endswith("/api/v1"):
        print("Warning: CANVAS_API_URL should end with '/api/v1'", file=sys.stderr)
        print(f"Current URL: {config.canvas_api_url}", file=sys.stderr)

    if config.ts_sandbox_mode not in {"auto", "local", "container"}:
        print(
            "Warning: TS_SANDBOX_MODE should be one of auto, local, container; "
            f"defaulting to 'auto' (got '{config.ts_sandbox_mode}')",
            file=sys.stderr
        )

    for env_name, env_value in _INVALID_INT_ENV_VARS.items():
        print(
            f"Warning: {env_name} expects an integer; using default value "
            f"(got '{env_value}')",
            file=sys.stderr
        )

    for env_name, note in unimplemented_env_vars.items():
        if os.getenv(env_name):
            print(
                f"Warning: {env_name} is set but {note}.",
                file=sys.stderr
            )

    return True


# Legacy compatibility - these will be used by existing code
API_BASE_URL = get_config().api_base_url
API_TOKEN = get_config().api_token

"""Configuration management for Canvas MCP server."""

import os
import sys

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Configuration class for Canvas MCP server."""

    def __init__(self) -> None:
        # Required configuration
        self.canvas_api_token = os.getenv("CANVAS_API_TOKEN", "")
        self.canvas_api_url = os.getenv("CANVAS_API_URL", "https://canvas.illinois.edu/api/v1")

        # Optional configuration with defaults
        self.mcp_server_name = os.getenv("MCP_SERVER_NAME", "canvas-api")
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.api_timeout = int(os.getenv("API_TIMEOUT", "30"))
        self.cache_ttl = int(os.getenv("CACHE_TTL", "300"))
        self.max_concurrent_requests = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))

        # Development configuration
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_api_requests = os.getenv("LOG_API_REQUESTS", "false").lower() == "true"

        # Privacy and security configuration
        self.enable_data_anonymization = os.getenv("ENABLE_DATA_ANONYMIZATION", "true").lower() == "true"
        self.anonymization_debug = os.getenv("ANONYMIZATION_DEBUG", "false").lower() == "true"

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

    return True


# Legacy compatibility - these will be used by existing code
API_BASE_URL = get_config().api_base_url
API_TOKEN = get_config().api_token

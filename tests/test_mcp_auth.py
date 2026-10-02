"""Tests for public HTTP MCP OAuth configuration."""

import os
from unittest.mock import patch

from canvas_mcp.core.config import Config


def test_oidc_auth_config_requires_redirect_allowlist():
    from canvas_mcp.core import config as config_module

    values = {
        "MCP_AUTH_MODE": "oidc",
        "MCP_PUBLIC_URL": "https://mcp.example.com",
        "MCP_OIDC_CONFIG_URL": "https://idp.example.com/.well-known/openid-configuration",
        "MCP_OIDC_CLIENT_ID": "client-id",
        "MCP_OIDC_CLIENT_SECRET": "client-secret",
        "MCP_OIDC_JWT_SIGNING_KEY": "signing-key",
        "MCP_OIDC_ALLOWED_CLIENT_REDIRECT_URIS": "",
    }
    previous_config = config_module._config
    try:
        with patch.dict(os.environ, values, clear=False):
            config_module._config = Config()
            assert config_module.validate_http_auth_config() is False
    finally:
        config_module._config = previous_config


def test_oidc_auth_config_accepts_chatgpt_redirects():
    from canvas_mcp.core import config as config_module

    values = {
        "MCP_AUTH_MODE": "oidc",
        "MCP_PUBLIC_URL": "https://mcp.example.com",
        "MCP_OIDC_CONFIG_URL": "https://idp.example.com/.well-known/openid-configuration",
        "MCP_OIDC_CLIENT_ID": "client-id",
        "MCP_OIDC_CLIENT_SECRET": "client-secret",
        "MCP_OIDC_JWT_SIGNING_KEY": "signing-key",
        "MCP_OIDC_ALLOWED_CLIENT_REDIRECT_URIS": "https://chatgpt.com/connector_platform_oauth_redirect,https://chatgpt.com/connector/oauth/*,http://localhost:*,http://127.0.0.1:*",
    }
    previous_config = config_module._config
    try:
        with patch.dict(os.environ, values, clear=False):
            config_module._config = Config()
            assert config_module.validate_http_auth_config() is True
    finally:
        config_module._config = previous_config

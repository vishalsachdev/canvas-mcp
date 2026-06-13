"""Tests for configuration management (singleton lifecycle, env parsing)."""

import canvas_mcp.core.config as config_module
from canvas_mcp.core.config import get_config, reset_config


def test_get_config_returns_cached_singleton():
    """get_config() returns the same instance until reset_config() is called."""
    first = get_config()
    assert get_config() is first
    reset_config()
    assert get_config() is not first


def test_reset_config_rebuilds_from_current_env(monkeypatch):
    """A value patched after first access is picked up after reset_config()."""
    monkeypatch.setenv("MCP_SERVER_NAME", "before")
    reset_config()
    assert get_config().mcp_server_name == "before"

    monkeypatch.setenv("MCP_SERVER_NAME", "after")
    reset_config()
    assert get_config().mcp_server_name == "after"


def test_reset_config_clears_invalid_env_caches(monkeypatch):
    """reset_config() discards stale invalid-env-var warnings.

    Without clearing these module-level caches, an invalid value parsed for a
    prior config would keep producing warnings after the env is corrected and
    config is rebuilt.
    """
    monkeypatch.setenv("API_TIMEOUT", "not-an-int")
    reset_config()
    get_config()  # triggers _int_env -> records the invalid value
    assert "API_TIMEOUT" in config_module._INVALID_INT_ENV_VARS

    # Correct the environment and reset: the stale warning must not persist.
    monkeypatch.setenv("API_TIMEOUT", "45")
    reset_config()
    assert "API_TIMEOUT" not in config_module._INVALID_INT_ENV_VARS

    get_config()  # valid now -> nothing recorded
    assert "API_TIMEOUT" not in config_module._INVALID_INT_ENV_VARS

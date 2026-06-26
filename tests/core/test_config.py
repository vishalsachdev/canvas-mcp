"""Tests for configuration management (singleton lifecycle, env parsing)."""

import pytest

import canvas_mcp.core.config as config_module
from canvas_mcp.core.config import _normalize_canvas_url


def test_get_config_returns_cached_singleton():
    """get_config() returns the same instance until reset_config() is called."""
    first = config_module.get_config()
    assert config_module.get_config() is first
    config_module.reset_config()
    assert config_module.get_config() is not first


def test_reset_config_rebuilds_from_current_env(monkeypatch):
    """A value patched after first access is picked up after reset_config()."""
    monkeypatch.setenv("MCP_SERVER_NAME", "before")
    config_module.reset_config()
    assert config_module.get_config().mcp_server_name == "before"

    monkeypatch.setenv("MCP_SERVER_NAME", "after")
    config_module.reset_config()
    assert config_module.get_config().mcp_server_name == "after"


def test_reset_config_clears_invalid_env_caches(monkeypatch):
    """reset_config() discards stale invalid-env-var warnings.

    Without clearing these module-level caches, an invalid value parsed for a
    prior config would keep producing warnings after the env is corrected and
    config is rebuilt.
    """
    monkeypatch.setenv("API_TIMEOUT", "not-an-int")
    config_module.reset_config()
    config_module.get_config()  # triggers _int_env -> records the invalid value
    assert "API_TIMEOUT" in config_module._INVALID_INT_ENV_VARS

    # Correct the environment and reset: the stale warning must not persist.
    monkeypatch.setenv("API_TIMEOUT", "45")
    config_module.reset_config()
    assert "API_TIMEOUT" not in config_module._INVALID_INT_ENV_VARS

    config_module.get_config()  # valid now -> nothing recorded
    assert "API_TIMEOUT" not in config_module._INVALID_INT_ENV_VARS


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Base host (the common footgun) gets the suffix appended.
        ("https://canvas.school.edu", "https://canvas.school.edu/api/v1"),
        # Trailing slash is stripped before appending.
        ("https://canvas.school.edu/", "https://canvas.school.edu/api/v1"),
        # Already-canonical form is unchanged.
        ("https://canvas.school.edu/api/v1", "https://canvas.school.edu/api/v1"),
        # Canonical form with a trailing slash is normalized.
        ("https://canvas.school.edu/api/v1/", "https://canvas.school.edu/api/v1"),
        # Surrounding whitespace is trimmed.
        ("  https://canvas.school.edu/api/v1  ", "https://canvas.school.edu/api/v1"),
        # Empty / blank stays empty so validate_config() can flag it as missing.
        ("", ""),
        ("   ", ""),
    ],
)
def test_normalize_canvas_url(raw, expected):
    assert _normalize_canvas_url(raw) == expected


def test_config_normalizes_canvas_api_url(monkeypatch):
    """CANVAS_API_URL from the environment is normalized on Config build."""
    monkeypatch.setenv("CANVAS_API_TOKEN", "test-token")
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.school.edu")
    config_module.reset_config()
    assert config_module.get_config().canvas_api_url == "https://canvas.school.edu/api/v1"

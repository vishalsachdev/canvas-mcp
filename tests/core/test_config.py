"""Tests for configuration management."""

import os

import pytest

from canvas_mcp.core.config import Config, get_config, validate_config


def test_config_initialization(mock_env: dict[str, str]) -> None:
    """Test configuration initialization with environment variables."""
    config = Config()
    assert config.canvas_api_token == "test_token_1234567890abcdefghij"
    assert config.canvas_api_url == "https://canvas.test.edu/api/v1"
    assert config.mcp_server_name == "test-canvas-api"
    assert config.debug is False
    assert config.api_timeout == 30
    assert config.cache_ttl == 300


def test_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test configuration defaults when environment variables are not set."""
    # Set only required variables (token must be at least 20 chars)
    monkeypatch.setenv("CANVAS_API_TOKEN", "test_token_1234567890")
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.test.edu/api/v1")

    config = Config()
    assert config.mcp_server_name == "canvas-api"
    assert config.debug is False
    assert config.api_timeout == 30
    assert config.cache_ttl == 300
    assert config.max_concurrent_requests == 10
    assert config.log_level == "INFO"
    assert config.enable_data_anonymization is True


def test_config_singleton(mock_env: dict[str, str]) -> None:
    """Test that get_config returns the same instance."""
    config1 = get_config()
    config2 = get_config()
    assert config1 is config2


def test_validate_config_success(mock_env: dict[str, str]) -> None:
    """Test configuration validation with valid configuration."""
    assert validate_config() is True


def test_validate_config_missing_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test configuration validation with missing API token."""
    monkeypatch.delenv("CANVAS_API_TOKEN", raising=False)

    from canvas_mcp.core import config
    config._config = None

    assert validate_config() is False
    captured = capsys.readouterr()
    assert "CANVAS_API_TOKEN" in captured.err


def test_validate_config_missing_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Test configuration validation with empty API URL."""
    monkeypatch.setenv("CANVAS_API_TOKEN", "test_token_1234567890")
    monkeypatch.setenv("CANVAS_API_URL", "")  # Set to empty string

    from canvas_mcp.core import config
    config._config = None

    assert validate_config() is False
    captured = capsys.readouterr()
    assert "CANVAS_API_URL" in captured.err


def test_api_base_url_property(mock_env: dict[str, str]) -> None:
    """Test legacy compatibility for API_BASE_URL property."""
    config = Config()
    assert config.api_base_url == config.canvas_api_url


def test_api_token_property(mock_env: dict[str, str]) -> None:
    """Test legacy compatibility for API_TOKEN property."""
    config = Config()
    assert config.api_token == config.canvas_api_token


def test_config_boolean_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test boolean configuration parsing."""
    monkeypatch.setenv("CANVAS_API_TOKEN", "test_token_1234567890")
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.test.edu/api/v1")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("LOG_API_REQUESTS", "True")
    monkeypatch.setenv("ENABLE_DATA_ANONYMIZATION", "TRUE")

    config = Config()
    assert config.debug is True
    assert config.log_api_requests is True
    assert config.enable_data_anonymization is True


def test_config_integer_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test integer configuration parsing."""
    monkeypatch.setenv("CANVAS_API_TOKEN", "test_token_1234567890")
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.test.edu/api/v1")
    monkeypatch.setenv("API_TIMEOUT", "60")
    monkeypatch.setenv("CACHE_TTL", "600")
    monkeypatch.setenv("MAX_CONCURRENT_REQUESTS", "20")

    config = Config()
    assert config.api_timeout == 60
    assert config.cache_ttl == 600
    assert config.max_concurrent_requests == 20

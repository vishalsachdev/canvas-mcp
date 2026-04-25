"""
Delete Guard Security Tests

Tests for the CANVAS_ALLOW_DELETES configuration field and the
client-level guard that blocks DELETE requests when disabled.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_mcp.core.config import Config


class TestDeleteGuardConfig:
    """Test CANVAS_ALLOW_DELETES config field."""

    def test_default_allows_deletes(self):
        """allow_deletes defaults to True when env var is not set."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }, clear=True):
            config = Config()
            assert config.allow_deletes is True

    def test_explicit_true(self):
        """allow_deletes is True when CANVAS_ALLOW_DELETES=true."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
            "CANVAS_ALLOW_DELETES": "true",
        }, clear=True):
            config = Config()
            assert config.allow_deletes is True

    def test_explicit_false(self):
        """allow_deletes is False when CANVAS_ALLOW_DELETES=false."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
            "CANVAS_ALLOW_DELETES": "false",
        }, clear=True):
            config = Config()
            assert config.allow_deletes is False

    def test_case_insensitive_false(self):
        """allow_deletes is False when CANVAS_ALLOW_DELETES=FALSE (uppercase)."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
            "CANVAS_ALLOW_DELETES": "FALSE",
        }, clear=True):
            config = Config()
            assert config.allow_deletes is False

    def test_non_true_string_is_false(self):
        """allow_deletes is False for non-'true' values like 'yes'."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
            "CANVAS_ALLOW_DELETES": "yes",
        }, clear=True):
            config = Config()
            assert config.allow_deletes is False


def _make_mock_config(allow_deletes=True):
    """Create a mock config for client guard tests."""
    mock_config = MagicMock()
    mock_config.allow_deletes = allow_deletes
    mock_config.api_base_url = "https://canvas.example.com/api/v1"
    mock_config.log_api_requests = False
    mock_config.enable_data_anonymization = False
    mock_config.log_access_events = False
    return mock_config


def _make_mock_client():
    """Create a mock httpx client with async methods."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 123, "name": "Test"}
    mock_response.raise_for_status = MagicMock()

    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.put = AsyncMock(return_value=mock_response)
    mock_client.delete = AsyncMock(return_value=mock_response)
    return mock_client


class TestDeleteGuardClient:
    """Test the delete guard in make_canvas_request()."""

    @pytest.mark.asyncio
    async def test_delete_allowed_when_enabled(self):
        """DELETE passes through when allow_deletes=True."""
        mock_config = _make_mock_config(allow_deletes=True)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client), \
             patch("canvas_mcp.core.audit.log_data_access"):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("delete", "/courses/123/modules/456")

        mock_client.delete.assert_called_once()
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_delete_blocked_when_disabled(self):
        """DELETE returns error dict when allow_deletes=False."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("delete", "/courses/123/modules/456")

        assert "error" in result
        mock_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_error_includes_endpoint(self):
        """Blocked error message includes the endpoint so user knows what was blocked."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("delete", "/courses/123/modules/456")

        assert "/courses/123/modules/456" in result["error"]

    @pytest.mark.asyncio
    async def test_blocked_error_includes_remediation(self):
        """Blocked error message tells user how to re-enable deletes."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("delete", "/courses/123/modules/456")

        assert "CANVAS_ALLOW_DELETES" in result["error"]
        assert "true" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_unaffected_when_deletes_disabled(self):
        """GET requests pass through even when allow_deletes=False."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client), \
             patch("canvas_mcp.core.audit.log_data_access"):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("get", "/courses/123")

        mock_client.get.assert_called_once()
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_post_unaffected_when_deletes_disabled(self):
        """POST requests pass through even when allow_deletes=False."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client), \
             patch("canvas_mcp.core.audit.log_data_access"):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("post", "/courses/123/modules", data={"name": "Test"})

        mock_client.post.assert_called_once()
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_put_unaffected_when_deletes_disabled(self):
        """PUT requests pass through even when allow_deletes=False."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client), \
             patch("canvas_mcp.core.audit.log_data_access"):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("put", "/courses/123/modules/456", data={"name": "Updated"})

        mock_client.put.assert_called_once()
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_uppercase_delete_also_blocked(self):
        """DELETE with uppercase method string is also blocked (case-insensitive)."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client):
            from canvas_mcp.core.client import make_canvas_request
            result = await make_canvas_request("DELETE", "/courses/123/modules/456")

        assert "error" in result
        mock_client.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_warning_called_when_blocked(self):
        """log_warning is called when a DELETE is blocked."""
        mock_config = _make_mock_config(allow_deletes=False)
        mock_client = _make_mock_client()

        with patch("canvas_mcp.core.config.get_config", return_value=mock_config), \
             patch("canvas_mcp.core.client._get_http_client", return_value=mock_client), \
             patch("canvas_mcp.core.client.log_warning") as mock_log_warning:
            from canvas_mcp.core.client import make_canvas_request
            await make_canvas_request("delete", "/courses/123/modules/456")

        mock_log_warning.assert_called_once()
        call_args = mock_log_warning.call_args[0][0]
        assert "blocked" in call_args.lower()

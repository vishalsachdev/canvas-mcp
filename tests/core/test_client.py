"""Unit tests for core HTTP client helpers."""

from canvas_mcp.core.client import _canvas_auth_headers


class TestCanvasAuthHeaders:
    """All Canvas API requests must carry a User-Agent (Instructure enforces it)."""

    def test_includes_user_agent(self):
        headers = _canvas_auth_headers("some-token")
        assert "User-Agent" in headers
        assert headers["User-Agent"].startswith("canvas-mcp/")

    def test_includes_bearer_authorization(self):
        headers = _canvas_auth_headers("some-token")
        assert headers["Authorization"] == "Bearer some-token"

    def test_user_agent_identifies_project(self):
        """UA should be self-identifying per Instructure's guidance (contact URL)."""
        headers = _canvas_auth_headers("t")
        assert "github.com/vishalsachdev/canvas-mcp" in headers["User-Agent"]

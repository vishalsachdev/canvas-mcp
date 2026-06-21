"""Unit tests for code_execution.py security-critical helper functions.

These cover the pure helpers that gate the sandbox's safety properties:
- `_validate_container_image` — command-injection guard for the docker/podman argv
- `_normalize_host` / `_parse_allowlist_hosts` — outbound network allowlist matching
- `_append_node_options` — NODE_OPTIONS composition
- `_resolve_canvas_credentials` — fail-closed per-request token isolation

The end-to-end sandbox behavior is exercised in tests/security/; this file locks
in the building blocks that those guarantees rest on.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from canvas_mcp.tools.code_execution import (
    _append_node_options,
    _normalize_host,
    _parse_allowlist_hosts,
    _resolve_canvas_credentials,
    _validate_container_image,
)


class TestValidateContainerImage:
    """_validate_container_image must reject anything that could inject argv."""

    @pytest.mark.parametrize("image", [
        "node:20-alpine",
        "node:18",
        "alpine:latest",
        "registry.io/org/image:tag",
        "ghcr.io/vishalsachdev/canvas-mcp:v1.4.0",
        "my_registry.local/team/img:1.2.3",
    ])
    def test_valid_images_accepted(self, image):
        assert _validate_container_image(image) is True

    @pytest.mark.parametrize("image", [
        "",                       # empty
        "node",                   # no tag
        "node:",                  # empty tag
        ":tag",                   # empty name
        "node:20; rm -rf /",      # shell metacharacter ;
        "node:20 && evil",        # space + &&
        "node:$(whoami)",         # command substitution
        "node:`id`",              # backtick substitution
        "node:20|cat /etc/passwd",  # pipe
        "node:20\nFROM evil",     # newline injection
        "node:20 --privileged",   # arg injection via space
        "node:tag with spaces",   # spaces
    ])
    def test_injection_attempts_rejected(self, image):
        assert _validate_container_image(image) is False


class TestNormalizeHost:
    """_normalize_host extracts a bare lowercase hostname from varied inputs."""

    @pytest.mark.parametrize("value,expected", [
        ("https://canvas.illinois.edu/api/v1", "canvas.illinois.edu"),
        ("http://Canvas.Illinois.EDU/courses", "canvas.illinois.edu"),
        ("canvas.illinois.edu", "canvas.illinois.edu"),
        ("canvas.illinois.edu:443", "canvas.illinois.edu"),
        ("canvas.illinois.edu/courses/123", "canvas.illinois.edu"),
        ("HTTPS://EXAMPLE.COM", "example.com"),
        ("", ""),
        ("   ", ""),
    ])
    def test_normalize(self, value, expected):
        assert _normalize_host(value) == expected


class TestParseAllowlistHosts:
    """_parse_allowlist_hosts splits on commas/spaces and normalizes each host."""

    def test_empty_string(self):
        assert _parse_allowlist_hosts("") == []

    def test_whitespace_only(self):
        assert _parse_allowlist_hosts("   ") == []

    def test_comma_separated(self):
        assert _parse_allowlist_hosts("a.com,b.com") == ["a.com", "b.com"]

    def test_space_separated(self):
        assert _parse_allowlist_hosts("a.com b.com") == ["a.com", "b.com"]

    def test_mixed_with_urls_and_ports(self):
        result = _parse_allowlist_hosts("https://a.com/x, b.com:443  c.com")
        assert result == ["a.com", "b.com", "c.com"]


class TestAppendNodeOptions:
    """_append_node_options composes NODE_OPTIONS without leaking empties."""

    def test_none_existing(self):
        assert _append_node_options(None, ["--max-old-space-size=256"]) == "--max-old-space-size=256"

    def test_empty_existing(self):
        assert _append_node_options("", ["--require=/g.cjs"]) == "--require=/g.cjs"

    def test_existing_preserved_and_extended(self):
        assert _append_node_options("--a", ["--b", "--c"]) == "--a --b --c"

    def test_no_extra_args(self):
        assert _append_node_options("--a", []) == "--a"

    def test_all_empty(self):
        assert _append_node_options(None, []) == ""

    def test_strips_surrounding_whitespace(self):
        assert _append_node_options("  --a  ", ["--b"]) == "--a --b"


class TestResolveCanvasCredentials:
    """_resolve_canvas_credentials must fail closed in HTTP mode."""

    def _config(self):
        return SimpleNamespace(
            canvas_api_url="https://env.instructure.com/api/v1",
            canvas_api_token="env-token",
        )

    def test_per_request_credentials_take_precedence(self):
        req = SimpleNamespace(api_url="https://req.instructure.com/api/v1", api_token="req-token")
        with patch("canvas_mcp.tools.code_execution.get_request_credentials", return_value=req):
            url, token = _resolve_canvas_credentials(self._config())
        assert url == "https://req.instructure.com/api/v1"
        assert token == "req-token"

    def test_http_mode_without_request_creds_fails_closed(self):
        """HTTP request active but no per-request token → never use env token."""
        with patch("canvas_mcp.tools.code_execution.get_request_credentials", return_value=None), \
             patch("canvas_mcp.tools.code_execution.is_http_request_active", return_value=True):
            with pytest.raises(PermissionError, match="Canvas token required"):
                _resolve_canvas_credentials(self._config())

    def test_stdio_mode_falls_back_to_env(self):
        """stdio mode (no HTTP request active) uses the server's configured token."""
        with patch("canvas_mcp.tools.code_execution.get_request_credentials", return_value=None), \
             patch("canvas_mcp.tools.code_execution.is_http_request_active", return_value=False):
            url, token = _resolve_canvas_credentials(self._config())
        assert url == "https://env.instructure.com/api/v1"
        assert token == "env-token"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

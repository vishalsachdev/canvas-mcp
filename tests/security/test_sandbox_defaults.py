"""
Sandbox Defaults Security Tests

Tests for secure-by-default sandbox configuration, environment filtering,
and fetch API network guard.

Test Coverage:
- Default sandbox enabled
- Default network blocked
- Default CPU, memory, timeout limits
- Environment variable filtering (allowlist)
- Fetch API guard in network guard JS
"""

import os

import pytest
from unittest.mock import patch

from canvas_mcp.core.config import Config
from canvas_mcp.tools.code_execution import (
    _SAFE_ENV_KEYS,
    _build_safe_env,
    _write_network_guard,
)


class TestSandboxDefaults:
    """Test that sandbox defaults are secure."""

    def test_default_sandbox_enabled(self):
        """ENABLE_TS_SANDBOX defaults to True."""
        with patch.dict(os.environ, {}, clear=True):
            # Provide required env vars
            env = {"CANVAS_API_TOKEN": "test", "CANVAS_API_URL": "https://x.com/api/v1"}
            with patch.dict(os.environ, env):
                config = Config()
                assert config.enable_ts_sandbox is True

    def test_default_network_blocked(self):
        """TS_SANDBOX_BLOCK_OUTBOUND_NETWORK defaults to True."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }):
            config = Config()
            assert config.ts_sandbox_block_outbound_network is True

    def test_default_cpu_limit(self):
        """TS_SANDBOX_CPU_LIMIT defaults to 30."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }):
            config = Config()
            assert config.ts_sandbox_cpu_limit == 30

    def test_default_memory_limit(self):
        """TS_SANDBOX_MEMORY_LIMIT_MB defaults to 512."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }):
            config = Config()
            assert config.ts_sandbox_memory_limit_mb == 512

    def test_default_timeout(self):
        """TS_SANDBOX_TIMEOUT_SEC defaults to 120."""
        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }):
            config = Config()
            assert config.ts_sandbox_timeout_sec == 120


class TestEnvironmentFiltering:
    """Test subprocess environment variable filtering."""

    def test_env_filtering_excludes_secrets(self):
        """Arbitrary env vars (like DB passwords, AWS keys) are excluded."""
        with patch.dict(os.environ, {
            "SECRET_KEY": "supersecret",
            "AWS_SECRET_ACCESS_KEY": "awskey",
            "DATABASE_URL": "postgres://...",
            "PATH": "/usr/bin",
            "CANVAS_API_TOKEN": "tok",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }):
            config = Config()
            env = _build_safe_env(config)
            assert "SECRET_KEY" not in env
            assert "AWS_SECRET_ACCESS_KEY" not in env
            assert "DATABASE_URL" not in env
            # Canvas credentials should be present (explicitly added)
            assert env["CANVAS_API_TOKEN"] == "tok"

    def test_env_filtering_includes_path(self):
        """PATH is preserved in the subprocess environment."""
        with patch.dict(os.environ, {
            "PATH": "/usr/local/bin:/usr/bin",
            "CANVAS_API_TOKEN": "tok",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }):
            config = Config()
            env = _build_safe_env(config)
            assert "PATH" in env
            assert env["PATH"] == "/usr/local/bin:/usr/bin"

    def test_safe_env_keys_are_reasonable(self):
        """Verify the allowlist contains expected system keys."""
        assert "PATH" in _SAFE_ENV_KEYS
        assert "HOME" in _SAFE_ENV_KEYS
        assert "NODE_PATH" in _SAFE_ENV_KEYS
        assert "TMPDIR" in _SAFE_ENV_KEYS
        # Should NOT contain sensitive patterns
        for key in _SAFE_ENV_KEYS:
            assert "SECRET" not in key.upper()
            assert "TOKEN" not in key.upper()
            assert "PASSWORD" not in key.upper()


class TestFetchGuard:
    """Test that the network guard JS includes globalThis.fetch interception."""

    def test_fetch_guard_generated(self, tmp_path):
        """Guard JS should include globalThis.fetch override."""
        guard_path = _write_network_guard(["canvas.example.com"], tmp_path)
        try:
            content = guard_path.read_text()
            assert "globalThis.fetch" in content
            assert "originalFetch" in content
            assert "enforce" in content
        finally:
            guard_path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

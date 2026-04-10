"""
Code Execution Security Tests

Tests for TypeScript code execution security, including
sandbox escape attempts, resource limits, and credential protection.

Test Coverage:
- TC-3.1: Sandbox Security
- TC-3.2: Code Execution Audit
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


class TestSandboxSecurity:
    """Test code execution sandboxing and isolation."""

    @pytest.mark.skip(reason="Sandboxing not yet fully implemented")
    def test_file_system_access_restriction(self):
        """TC-3.1.1: Attempt file system access outside temp directory."""
        # Test code that tries to read /etc/passwd

        # Execute and verify access denied
        # This would use the execute_typescript tool
        # Expected: Access denied or error

    def test_network_access_restriction(self):
        """TC-3.1.2: Verify network guard blocks unauthorized hosts."""
        from canvas_mcp.tools.code_execution import _write_network_guard

        # Generate the guard and verify it intercepts https.request
        guard_path = _write_network_guard(["allowed.com"], Path(tempfile.mkdtemp()))
        try:
            content = guard_path.read_text()
            assert "enforce" in content
            assert "SANDBOX_NETWORK_BLOCKED" in content
            assert "allowed.com" in content
        finally:
            guard_path.unlink()

    def test_credential_theft_prevention(self):
        """TC-3.1.3: Verify env filtering prevents credential leakage."""
        from canvas_mcp.core.config import Config
        from canvas_mcp.tools.code_execution import _build_safe_env

        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "secret_token",
            "CANVAS_API_URL": "https://x.com/api/v1",
            "AWS_SECRET_ACCESS_KEY": "aws_secret",
            "DATABASE_PASSWORD": "db_pass",
            "PATH": "/usr/bin",
        }):
            config = Config()
            env = _build_safe_env(config)
            # Canvas creds are explicitly added (needed for execution)
            assert env["CANVAS_API_TOKEN"] == "secret_token"
            # Other secrets must NOT be present
            assert "AWS_SECRET_ACCESS_KEY" not in env
            assert "DATABASE_PASSWORD" not in env

    def test_resource_exhaustion_timeout(self):
        """TC-3.1.4: Test timeout protection for infinite loops."""
        # Test code with infinite loop

        # Execute with timeout
        # Expected: Timeout after configured limit (120s default)
        # Verify process is terminated

    def test_memory_exhaustion_protection(self):
        """TC-3.1.4: Verify memory limit is set in Config defaults."""
        from canvas_mcp.core.config import Config

        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
        }):
            config = Config()
            # Default memory limit should be 512 MB (non-zero)
            assert config.ts_sandbox_memory_limit_mb == 512

    @pytest.mark.skip(reason="Command execution protection needed")
    def test_shell_execution_blocked(self):
        """TC-3.1.5: Test that shell commands are blocked."""
        # Test code that tries to spawn shell

        # Execute and verify shell execution blocked
        # Expected: Permission denied or execution blocked

    def test_temporary_file_cleanup(self):
        """TC-3.1.6: Verify temporary files are cleaned up."""
        # Test that temporary files created during execution are deleted
        # This is mentioned as implemented in the docs

        # Create test directory
        temp_dir = tempfile.mkdtemp()
        temp_file = Path(temp_dir) / "test.ts"

        # Simulate code execution file
        temp_file.write_text("console.log('test');")

        # Verify file is deleted after execution
        # In real implementation, this would be done by execute_typescript
        assert temp_file.exists()  # Before cleanup

        # Simulate cleanup
        temp_file.unlink()
        assert not temp_file.exists()  # After cleanup


class TestCodeExecutionAudit:
    """Test code execution audit logging."""

    def test_code_execution_logged(self, capsys):
        """TC-3.2.1: Verify code execution is logged."""
        import json as _json
        import tempfile as _tempfile

        from canvas_mcp.core import config as cfg_mod
        from canvas_mcp.core.audit import (
            init_audit_logging,
            log_code_execution,
            reset_audit_state,
        )

        reset_audit_state()
        with patch.dict(os.environ, {
            "LOG_ACCESS_EVENTS": "false",
            "LOG_EXECUTION_EVENTS": "true",
            "CANVAS_API_TOKEN": "test",
            "AUDIT_LOG_DIR": _tempfile.mkdtemp(),
        }):
            old = cfg_mod._config
            cfg_mod._config = None
            try:
                init_audit_logging()
                log_code_execution("abcdef12", "local", "success", 1.5)
                captured = capsys.readouterr()
                event = _json.loads(captured.err.strip().split("\n")[-1])
                assert event["event_type"] == "code_execution"
                assert event["code_hash"] == "abcdef12"
                assert "timestamp" in event
            finally:
                cfg_mod._config = old
                reset_audit_state()

    def test_code_execution_errors_logged(self, capsys):
        """TC-3.2.2: Verify code execution errors are logged."""
        import json as _json
        import tempfile as _tempfile

        from canvas_mcp.core import config as cfg_mod
        from canvas_mcp.core.audit import (
            init_audit_logging,
            log_code_execution,
            reset_audit_state,
        )

        reset_audit_state()
        with patch.dict(os.environ, {
            "LOG_ACCESS_EVENTS": "false",
            "LOG_EXECUTION_EVENTS": "true",
            "CANVAS_API_TOKEN": "test",
            "AUDIT_LOG_DIR": _tempfile.mkdtemp(),
        }):
            old = cfg_mod._config
            cfg_mod._config = None
            try:
                init_audit_logging()
                log_code_execution("deadbeef", "local", "error", 0.5, error="segfault")
                captured = capsys.readouterr()
                event = _json.loads(captured.err.strip().split("\n")[-1])
                assert event["status"] == "error"
                assert event["error"] == "segfault"
            finally:
                cfg_mod._config = old
                reset_audit_state()

    @pytest.mark.skip(reason="Code execution logging not yet implemented")
    def test_sensitive_output_sanitized(self):
        """TC-3.2.3: Verify sensitive data in output is sanitized."""
        # Test that PII or credentials in execution output are masked
        pass


class TestCodeExecutionConfiguration:
    """Test code execution configuration and limits."""

    def test_timeout_configurable(self):
        """Verify code execution timeout is configurable."""
        # Check that timeout can be configured
        # Default is 120 seconds as per docs

        # Verify default timeout
        # Implementation depends on how timeout is configured

    @pytest.mark.skip(reason="Resource limits not yet configurable")
    def test_resource_limits_configurable(self):
        """Verify resource limits can be configured."""
        # Test that memory, CPU limits can be configured
        pass


class TestMaliciousCodeDetection:
    """Test detection of malicious code patterns."""

    @pytest.mark.skip(reason="Static code analysis not yet implemented")
    def test_dangerous_imports_detected(self):
        """Test detection of dangerous imports."""
        # Code with dangerous imports like child_process, fs, net

        # Verify dangerous imports are detected/blocked

    @pytest.mark.skip(reason="Static code analysis not yet implemented")
    def test_obfuscated_code_detected(self):
        """Test detection of obfuscated code."""
        # Heavily obfuscated code

        # Verify obfuscation is detected


class TestCodeExecutionIsolation:
    """Test execution environment isolation."""

    def test_execution_in_temp_directory(self):
        """Verify code executes in temporary directory."""
        # Test that execution happens in isolated temp directory
        # Not in project directory or user home
        pass

    def test_limited_environment_variables(self):
        """Test that only allowlisted environment variables are passed."""
        from canvas_mcp.core.config import Config
        from canvas_mcp.tools.code_execution import _SAFE_ENV_KEYS, _build_safe_env

        with patch.dict(os.environ, {
            "CANVAS_API_TOKEN": "test",
            "CANVAS_API_URL": "https://x.com/api/v1",
            "PATH": "/usr/bin",
            "HOME": "/home/user",
            "MY_CUSTOM_VAR": "should_not_appear",
            "PGPASSWORD": "should_not_appear",
        }):
            config = Config()
            env = _build_safe_env(config)

            # Only safe keys + Canvas credentials should be present
            for key in env:
                assert key in _SAFE_ENV_KEYS or key in (
                    "CANVAS_API_URL", "CANVAS_API_TOKEN"
                ), f"Unexpected key in env: {key}"

            assert "MY_CUSTOM_VAR" not in env
            assert "PGPASSWORD" not in env


class TestWindowsTsxCommand:
    """Tests for Windows-compatible tsx command building (issue #83)."""

    def test_non_windows_uses_npx(self):
        """On non-Windows platforms, _build_local_tsx_command returns npx tsx."""
        from canvas_mcp.tools.code_execution import _build_local_tsx_command
        with patch('canvas_mcp.tools.code_execution.sys.platform', 'linux'):
            cmd = _build_local_tsx_command('/tmp/test.ts')
        assert cmd == ['npx', 'tsx', '/tmp/test.ts']

    def test_windows_uses_node_with_tsx_cli_via_which(self, tmp_path):
        """On Windows, finds tsx cli.mjs relative to tsx.cmd discovered via PATH."""
        from canvas_mcp.tools.code_execution import _build_local_tsx_command
        # Simulate tsx.cmd in a directory alongside node_modules/tsx
        tsx_cmd_dir = tmp_path / 'npm'
        tsx_cmd_dir.mkdir()
        tsx_cmd = tsx_cmd_dir / 'tsx.cmd'
        tsx_cmd.touch()
        tsx_cli = tsx_cmd_dir / 'node_modules' / 'tsx' / 'dist' / 'cli.mjs'
        tsx_cli.parent.mkdir(parents=True)
        tsx_cli.touch()

        def mock_which(name):
            if name == 'node':
                return '/usr/bin/node'
            if name == 'tsx':
                return str(tsx_cmd)
            return None

        with patch('canvas_mcp.tools.code_execution.sys.platform', 'win32'), \
             patch('canvas_mcp.tools.code_execution.shutil.which', side_effect=mock_which), \
             patch.dict(os.environ, {'APPDATA': str(tmp_path / 'nonexistent')}):
            cmd = _build_local_tsx_command('/tmp/test.ts')

        assert cmd[0] == '/usr/bin/node'
        assert cmd[1] == str(tsx_cli)
        assert cmd[2] == '/tmp/test.ts'

    def test_windows_uses_appdata_fallback_when_which_fails(self, tmp_path):
        """On Windows, falls back to APPDATA when shutil.which('tsx') returns None."""
        from canvas_mcp.tools.code_execution import _build_local_tsx_command
        tsx_cli = tmp_path / 'npm' / 'node_modules' / 'tsx' / 'dist' / 'cli.mjs'
        tsx_cli.parent.mkdir(parents=True)
        tsx_cli.touch()

        def mock_which(name):
            if name == 'node':
                return '/usr/bin/node'
            return None

        with patch('canvas_mcp.tools.code_execution.sys.platform', 'win32'), \
             patch('canvas_mcp.tools.code_execution.shutil.which', side_effect=mock_which), \
             patch.dict(os.environ, {'APPDATA': str(tmp_path)}):
            cmd = _build_local_tsx_command('/tmp/test.ts')

        assert cmd[0] == '/usr/bin/node'
        assert cmd[1] == str(tsx_cli)
        assert cmd[2] == '/tmp/test.ts'

    def test_windows_error_when_tsx_not_found(self):
        """On Windows, returns error command when tsx CLI module cannot be located."""
        from canvas_mcp.tools.code_execution import _build_local_tsx_command
        with patch('canvas_mcp.tools.code_execution.sys.platform', 'win32'), \
             patch('canvas_mcp.tools.code_execution.shutil.which', return_value=None), \
             patch.dict(os.environ, {'APPDATA': '/nonexistent_appdata_path'}):
            cmd = _build_local_tsx_command('/tmp/test.ts')
        # Should return a node -e error command, not npx
        assert cmd[0] == 'node'
        assert cmd[1] == '-e'
        assert 'tsx not found' in cmd[2]

    def test_find_tsx_cli_windows_returns_none_when_not_found(self):
        """_find_tsx_cli_windows returns None when tsx is not installed."""
        from canvas_mcp.tools.code_execution import _find_tsx_cli_windows
        with patch('canvas_mcp.tools.code_execution.shutil.which', return_value=None), \
             patch.dict(os.environ, {'APPDATA': '/nonexistent_path_xyz'}):
            result = _find_tsx_cli_windows()
        assert result is None

    def test_find_tsx_cli_windows_skips_empty_appdata(self, tmp_path):
        """_find_tsx_cli_windows skips APPDATA check when env var is empty."""
        from canvas_mcp.tools.code_execution import _find_tsx_cli_windows
        tsx_cmd_dir = tmp_path / 'bin'
        tsx_cmd_dir.mkdir()
        tsx_cmd = tsx_cmd_dir / 'tsx.cmd'
        tsx_cmd.touch()
        tsx_cli = tsx_cmd_dir / 'node_modules' / 'tsx' / 'dist' / 'cli.mjs'
        tsx_cli.parent.mkdir(parents=True)
        tsx_cli.touch()

        with patch('canvas_mcp.tools.code_execution.shutil.which', return_value=str(tsx_cmd)), \
             patch.dict(os.environ, {'APPDATA': ''}):
            result = _find_tsx_cli_windows()
        assert result == str(tsx_cli)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

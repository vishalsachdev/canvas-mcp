"""
Audit Logging Security Tests

Tests for structured audit event emission, sanitization, and file rotation.

Test Coverage:
- Data access events emitted when enabled
- Code execution events emitted when enabled
- Events disabled by default
- Endpoint sanitization in events
- ISO 8601 timestamps present
- Code hash used (not raw code)
- Audit file creation
- Audit file rotation configuration
"""

import json
import os
import tempfile

import pytest
from unittest.mock import patch

from canvas_mcp.core.audit import (
    _sanitize_endpoint,
    init_audit_logging,
    log_code_execution,
    log_data_access,
    reset_audit_state,
    _audit_logger,
    _MAX_BYTES,
    _BACKUP_COUNT,
)


@pytest.fixture(autouse=True)
def clean_audit_state():
    """Reset audit module state before each test."""
    reset_audit_state()
    yield
    reset_audit_state()


class TestAuditDataAccess:
    """Test data access audit events."""

    def test_data_access_event_emitted(self, capsys):
        """Enable LOG_ACCESS_EVENTS, call log_data_access, verify JSON on stderr."""
        with patch.dict(os.environ, {
            "LOG_ACCESS_EVENTS": "true",
            "LOG_EXECUTION_EVENTS": "false",
            "CANVAS_API_TOKEN": "test",
            "AUDIT_LOG_DIR": tempfile.mkdtemp(),
        }):
            # Reset config singleton so it picks up new env
            from canvas_mcp.core import config as cfg_mod
            old = cfg_mod._config
            cfg_mod._config = None
            try:
                init_audit_logging()
                log_data_access("GET", "/courses/12345/users/678", "success")

                captured = capsys.readouterr()
                # Parse the JSON line from stderr
                lines = [l for l in captured.err.strip().split("\n") if l.strip()]
                assert len(lines) >= 1
                event = json.loads(lines[-1])
                assert event["event_type"] == "data_access"
                assert event["method"] == "GET"
                assert event["status"] == "success"
                # Endpoint should be sanitized
                assert "12345" not in event["endpoint"]
            finally:
                cfg_mod._config = old

    def test_events_disabled_by_default(self, capsys):
        """When LOG_ACCESS_EVENTS is false, no output is emitted."""
        with patch.dict(os.environ, {
            "LOG_ACCESS_EVENTS": "false",
            "LOG_EXECUTION_EVENTS": "false",
            "CANVAS_API_TOKEN": "test",
        }):
            from canvas_mcp.core import config as cfg_mod
            old = cfg_mod._config
            cfg_mod._config = None
            try:
                init_audit_logging()
                log_data_access("GET", "/courses/123", "success")
                captured = capsys.readouterr()
                assert captured.err.strip() == ""
            finally:
                cfg_mod._config = old


class TestAuditCodeExecution:
    """Test code execution audit events."""

    def test_code_execution_event_emitted(self, capsys):
        """Enable LOG_EXECUTION_EVENTS, call log_code_execution, verify JSON."""
        with patch.dict(os.environ, {
            "LOG_ACCESS_EVENTS": "false",
            "LOG_EXECUTION_EVENTS": "true",
            "CANVAS_API_TOKEN": "test",
            "AUDIT_LOG_DIR": tempfile.mkdtemp(),
        }):
            from canvas_mcp.core import config as cfg_mod
            old = cfg_mod._config
            cfg_mod._config = None
            try:
                init_audit_logging()
                log_code_execution("abc123def456", "local", "success", 2.5)

                captured = capsys.readouterr()
                lines = [l for l in captured.err.strip().split("\n") if l.strip()]
                assert len(lines) >= 1
                event = json.loads(lines[-1])
                assert event["event_type"] == "code_execution"
                assert event["code_hash"] == "abc123def456"
                assert event["sandbox_mode"] == "local"
                assert event["status"] == "success"
                assert event["duration_sec"] == 2.5
            finally:
                cfg_mod._config = old

    def test_code_hash_not_raw_code(self, capsys):
        """Verify only hash is logged, not the actual source code."""
        with patch.dict(os.environ, {
            "LOG_ACCESS_EVENTS": "false",
            "LOG_EXECUTION_EVENTS": "true",
            "CANVAS_API_TOKEN": "test",
            "AUDIT_LOG_DIR": tempfile.mkdtemp(),
        }):
            from canvas_mcp.core import config as cfg_mod
            old = cfg_mod._config
            cfg_mod._config = None
            try:
                init_audit_logging()
                # Log with a hash, not raw code
                log_code_execution("a1b2c3d4e5f6", "local", "success", 1.0)

                captured = capsys.readouterr()
                # Ensure no raw code patterns appear
                assert "console.log" not in captured.err
                assert "import" not in captured.err
            finally:
                cfg_mod._config = old


class TestAuditSanitization:
    """Test endpoint sanitization in audit events."""

    def test_endpoint_sanitization(self):
        """/courses/12345/users/678 → /courses/***/users/***."""
        result = _sanitize_endpoint("/courses/12345/users/678")
        assert result == "/courses/***/users/***"
        assert "12345" not in result
        assert "678" not in result

    def test_event_has_timestamp(self, capsys):
        """Verify audit events contain ISO 8601 timestamp."""
        with patch.dict(os.environ, {
            "LOG_ACCESS_EVENTS": "true",
            "LOG_EXECUTION_EVENTS": "false",
            "CANVAS_API_TOKEN": "test",
            "AUDIT_LOG_DIR": tempfile.mkdtemp(),
        }):
            from canvas_mcp.core import config as cfg_mod
            old = cfg_mod._config
            cfg_mod._config = None
            try:
                init_audit_logging()
                log_data_access("POST", "/courses/1/assignments", "success")

                captured = capsys.readouterr()
                lines = [l for l in captured.err.strip().split("\n") if l.strip()]
                event = json.loads(lines[-1])
                assert "timestamp" in event
                # ISO 8601 format check
                assert "T" in event["timestamp"]
                assert event["timestamp"].endswith("+00:00") or event["timestamp"].endswith("Z")
            finally:
                cfg_mod._config = old


class TestAuditFileHandling:
    """Test audit log file creation and rotation config."""

    def test_audit_file_created(self):
        """Verify audit.jsonl is created in the audit log dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "LOG_ACCESS_EVENTS": "true",
                "LOG_EXECUTION_EVENTS": "false",
                "CANVAS_API_TOKEN": "test",
                "AUDIT_LOG_DIR": tmpdir,
            }):
                from canvas_mcp.core import config as cfg_mod
                old = cfg_mod._config
                cfg_mod._config = None
                try:
                    init_audit_logging()
                    log_data_access("GET", "/courses/1", "success")

                    audit_file = os.path.join(tmpdir, "audit.jsonl")
                    assert os.path.exists(audit_file)

                    with open(audit_file) as f:
                        content = f.read()
                    assert "data_access" in content
                finally:
                    cfg_mod._config = old

    def test_audit_file_rotation_config(self):
        """Verify RotatingFileHandler is configured with 10 MB, 5 backups."""
        from logging.handlers import RotatingFileHandler

        assert _MAX_BYTES == 10 * 1024 * 1024  # 10 MB
        assert _BACKUP_COUNT == 5

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {
                "LOG_ACCESS_EVENTS": "true",
                "LOG_EXECUTION_EVENTS": "false",
                "CANVAS_API_TOKEN": "test",
                "AUDIT_LOG_DIR": tmpdir,
            }):
                from canvas_mcp.core import config as cfg_mod
                old = cfg_mod._config
                cfg_mod._config = None
                try:
                    init_audit_logging()

                    file_handlers = [
                        h for h in _audit_logger.handlers
                        if isinstance(h, RotatingFileHandler)
                    ]
                    assert len(file_handlers) == 1
                    handler = file_handlers[0]
                    assert handler.maxBytes == 10 * 1024 * 1024
                    assert handler.backupCount == 5
                finally:
                    cfg_mod._config = old


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

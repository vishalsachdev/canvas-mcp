"""
PII Sanitization Security Tests

Tests for PII redaction in log context and URL sanitization.

Test Coverage:
- PII keys fully redacted
- ID keys truncated to last 4 chars
- Non-PII keys preserved
- Redaction disabled via env var
- URL numeric segment sanitization
"""

import os
from unittest.mock import patch

import pytest

from canvas_mcp.core.logging import _sanitize_context, sanitize_url


class TestPIISanitization:
    """Test PII sanitization in log context."""

    def test_pii_keys_redacted(self):
        """PII keys (user_id, email, name, etc.) are replaced with [REDACTED]."""
        context = {
            "user_id": 12345,
            "email": "student@university.edu",
            "name": "Jane Doe",
            "login_id": "jdoe2",
            "sis_user_id": "U00012345",
            "student_id": 99999,
            "value": "some sensitive data",
        }
        with patch.dict(os.environ, {"LOG_REDACT_PII": "true"}):
            result = _sanitize_context(context)

        for key in context:
            assert result[key] == "[REDACTED]", f"{key} should be redacted"

    def test_id_keys_truncated(self):
        """ID keys show only last 4 characters, prefixed with ***."""
        context = {
            "course_id": 123456,
            "topic_id": 78901,
            "assignment_id": 55555,
            "entry_id": 42,
            "submission_id": 9999999,
        }
        with patch.dict(os.environ, {"LOG_REDACT_PII": "true"}):
            result = _sanitize_context(context)

        assert result["course_id"] == "***3456"
        assert result["topic_id"] == "***8901"
        assert result["assignment_id"] == "***5555"
        # entry_id "42" is <= 4 chars, passes through as-is
        assert result["entry_id"] == "42"
        assert result["submission_id"] == "***9999"

    def test_non_pii_keys_preserved(self):
        """Arbitrary keys that are not PII or IDs pass through unchanged."""
        context = {
            "endpoint": "/courses/123/assignments",
            "method": "GET",
            "status_code": 200,
        }
        with patch.dict(os.environ, {"LOG_REDACT_PII": "true"}):
            result = _sanitize_context(context)

        assert result == context

    def test_redaction_disabled(self):
        """When LOG_REDACT_PII=false, all values pass through unchanged."""
        context = {
            "user_id": 12345,
            "email": "student@university.edu",
            "course_id": 123456,
        }
        with patch.dict(os.environ, {"LOG_REDACT_PII": "false"}):
            result = _sanitize_context(context)

        assert result == context

    def test_redaction_enabled_by_default(self):
        """When LOG_REDACT_PII is not set, redaction is enabled by default."""
        context = {"user_id": 12345, "name": "Jane Doe"}
        # Remove env var entirely to test default
        env = os.environ.copy()
        env.pop("LOG_REDACT_PII", None)
        with patch.dict(os.environ, env, clear=True):
            result = _sanitize_context(context)

        assert result["user_id"] == "[REDACTED]"
        assert result["name"] == "[REDACTED]"


class TestURLSanitization:
    """Test URL path segment sanitization."""

    def test_sanitize_url_numeric_segments(self):
        """/courses/12345/users/678 becomes /courses/***/users/***."""
        url = "/courses/12345/users/678"
        assert sanitize_url(url) == "/courses/***/users/***"

    def test_sanitize_url_preserves_non_numeric(self):
        """Non-numeric path segments are preserved."""
        url = "/courses/assignments/submissions"
        assert sanitize_url(url) == "/courses/assignments/submissions"

    def test_sanitize_url_full_url(self):
        """Full URLs with host and path are sanitized."""
        url = "https://canvas.example.com/api/v1/courses/12345/users/678"
        result = sanitize_url(url)
        assert "/courses/***" in result
        assert "/users/***" in result
        assert "12345" not in result
        assert "678" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

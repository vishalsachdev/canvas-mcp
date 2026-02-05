"""Tests for de-anonymization functionality."""

import sys
import pytest
from unittest.mock import patch, MagicMock

# Mock the mcp module before it gets imported
sys.modules["mcp"] = MagicMock()
sys.modules["mcp.server"] = MagicMock()
sys.modules["mcp.server.fastmcp"] = MagicMock()

from canvas_mcp.core.anonymization import (
    _store_for_deanonymization,
    deanonymize_text,
    _deanonymization_cache,
    clear_anonymization_cache,
    anonymize_user_data,
    generate_anonymous_id,
    _anonymization_cache,
)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear caches before and after each test."""
    clear_anonymization_cache()
    yield
    clear_anonymization_cache()


class TestStoreForDeanonymization:
    """Tests for _store_for_deanonymization function."""

    def test_stores_name_and_email(self):
        """Store original data for later de-anonymization."""
        _store_for_deanonymization(
            "Student_a1b2c3d4",
            {"name": "John Smith", "email": "john@university.edu"},
        )
        assert "Student_a1b2c3d4" in _deanonymization_cache
        assert _deanonymization_cache["Student_a1b2c3d4"]["name"] == "John Smith"
        assert (
            _deanonymization_cache["Student_a1b2c3d4"]["email"] == "john@university.edu"
        )

    def test_skips_empty_data(self):
        """Don't store if no meaningful PII present."""
        _store_for_deanonymization("Student_a1b2c3d4", {})
        assert "Student_a1b2c3d4" not in _deanonymization_cache

    def test_handles_partial_data_name_only(self):
        """Store partial data (name only)."""
        _store_for_deanonymization("Student_a1b2c3d4", {"name": "Jane Doe"})
        assert _deanonymization_cache["Student_a1b2c3d4"]["name"] == "Jane Doe"
        assert _deanonymization_cache["Student_a1b2c3d4"]["email"] == ""

    def test_handles_partial_data_email_only(self):
        """Store partial data (email only)."""
        _store_for_deanonymization(
            "Student_b2c3d4e5", {"email": "jane@university.edu"}
        )
        assert _deanonymization_cache["Student_b2c3d4e5"]["name"] == ""
        assert _deanonymization_cache["Student_b2c3d4e5"]["email"] == "jane@university.edu"


class TestDeanonymizeText:
    """Tests for deanonymize_text function."""

    @patch("canvas_mcp.core.config.get_config")
    def test_replaces_anonymous_name(self, mock_config):
        """De-anonymize Student_xxx patterns when enabled."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        _store_for_deanonymization(
            "Student_a1b2c3d4",
            {"name": "Jane Smith", "email": "jane@test.edu"},
        )

        result = deanonymize_text("Student_a1b2c3d4 submitted their assignment")
        assert "Jane Smith" in result
        assert "Student_a1b2c3d4" not in result

    @patch("canvas_mcp.core.config.get_config")
    def test_returns_original_when_disabled(self, mock_config):
        """Return unchanged text when de-anonymization is disabled."""
        mock_config.return_value.enable_deanonymization = False

        text = "Student_a1b2c3d4 submitted"
        result = deanonymize_text(text)
        assert result == text

    @patch("canvas_mcp.core.config.get_config")
    def test_cache_miss_returns_anonymous_id(self, mock_config):
        """Return anonymous ID unchanged on cache miss."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        result = deanonymize_text("Student_ffffffff said hello")
        assert "Student_ffffffff" in result

    @patch("canvas_mcp.core.config.get_config")
    def test_replaces_email_pattern(self, mock_config):
        """De-anonymize email patterns."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        _store_for_deanonymization(
            "Student_a1b2c3d4",
            {"name": "John", "email": "john@real.edu"},
        )

        result = deanonymize_text("Contact student_a1b2c3d4@example.edu")
        assert "john@real.edu" in result

    @patch("canvas_mcp.core.config.get_config")
    def test_handles_mixed_content(self, mock_config):
        """Handle mix of cached and uncached references."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        _store_for_deanonymization(
            "Student_a1b2c3d4", {"name": "Alice", "email": ""}
        )
        # Student_b2c3d4e5 is NOT in cache

        result = deanonymize_text("Alice: Student_a1b2c3d4, Bob: Student_b2c3d4e5")
        assert "Alice" in result
        assert "Student_b2c3d4e5" in result  # Unchanged

    @patch("canvas_mcp.core.config.get_config")
    def test_handles_multiple_same_student(self, mock_config):
        """Handle multiple references to the same student."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        _store_for_deanonymization(
            "Student_a1b2c3d4", {"name": "Bob Jones", "email": ""}
        )

        result = deanonymize_text(
            "Student_a1b2c3d4 said hello. Then Student_a1b2c3d4 left."
        )
        assert result.count("Bob Jones") == 2
        assert "Student_a1b2c3d4" not in result


class TestAnonymizeUserDataCachePopulation:
    """Tests for cache population during anonymization."""

    def test_anonymize_user_data_populates_deanonymization_cache(self):
        """Verify anonymize_user_data stores original data for de-anonymization."""
        user_data = {
            "id": 12345,
            "name": "Test Student",
            "email": "test@university.edu",
        }

        anonymized = anonymize_user_data(user_data)

        # Get the anonymous ID that was generated
        anonymous_id = generate_anonymous_id(12345)

        # Verify the de-anonymization cache was populated
        assert anonymous_id in _deanonymization_cache
        assert _deanonymization_cache[anonymous_id]["name"] == "Test Student"
        assert _deanonymization_cache[anonymous_id]["email"] == "test@university.edu"


class TestClearCache:
    """Tests for cache clearing functionality."""

    def test_clear_anonymization_cache_clears_both_caches(self):
        """Verify clear_anonymization_cache clears both forward and reverse caches."""
        # Populate both caches
        generate_anonymous_id(12345)
        _store_for_deanonymization(
            "Student_test1234", {"name": "Test", "email": "test@test.edu"}
        )

        # Verify caches are populated
        assert len(_anonymization_cache) > 0
        assert len(_deanonymization_cache) > 0

        # Clear caches
        clear_anonymization_cache()

        # Verify both are empty
        assert len(_anonymization_cache) == 0
        assert len(_deanonymization_cache) == 0


class TestAuditLogging:
    """Tests for FERPA-compliant audit logging."""

    @patch("canvas_mcp.core.config.get_config")
    @patch("canvas_mcp.core.anonymization.logging")
    def test_logs_deanonymization_access(self, mock_logging, mock_config):
        """Verify FERPA-compliant audit logging occurs."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False
        mock_audit_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_audit_logger

        _store_for_deanonymization(
            "Student_a1b2c3d4", {"name": "Test User", "email": ""}
        )
        deanonymize_text("Hello Student_a1b2c3d4")

        # Verify pii_audit logger was used
        mock_logging.getLogger.assert_called_with("pii_audit")
        mock_audit_logger.info.assert_called()
        call_args = mock_audit_logger.info.call_args[0][0]
        assert "DEANONYMIZATION_ACCESS" in call_args
        assert "Student_a1b2c3d4" in call_args

    @patch("canvas_mcp.core.config.get_config")
    @patch("canvas_mcp.core.anonymization.logging")
    def test_no_logging_on_cache_miss(self, mock_logging, mock_config):
        """Verify no audit logging when no IDs are resolved."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False
        mock_audit_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_audit_logger

        # No entries in cache
        deanonymize_text("Hello Student_unknown1")

        # Verify pii_audit logger was NOT called (no resolved IDs)
        # Note: getLogger might be called for the debug logger
        audit_calls = [
            call for call in mock_logging.getLogger.call_args_list
            if call[0][0] == "pii_audit"
        ]
        if audit_calls:
            mock_audit_logger.info.assert_not_called()

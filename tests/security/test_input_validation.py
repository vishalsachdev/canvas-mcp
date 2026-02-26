"""
Input Validation Security Tests

Tests for parameter validation, injection prevention,
and input sanitization.

Test Coverage:
- TC-5.1: Parameter Validation
- TC-5.2: Injection Testing
"""

from typing import Literal

import pytest

from canvas_mcp.core.validation import (
    _convert_to_bool,
    _convert_to_list,
    validate_parameter,
)


class TestParameterValidation:
    """Test input parameter validation."""

    def test_invalid_parameter_types(self):
        """TC-5.1.1: Test invalid parameter types."""
        # Test with wrong types - string can't convert to int
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("course_id", "not_a_number", int)

    def test_missing_required_parameters(self):
        """TC-5.1.1: Test missing required parameters."""
        # Test that None with non-optional type raises error
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("required_param", None, str)

    def test_boundary_conditions(self):
        """TC-5.1.2: Test boundary conditions."""
        # Test extremely large IDs
        large_id = 2**31  # Max 32-bit integer
        result = validate_parameter("id", str(large_id), int)
        assert isinstance(result, int)
        assert result == large_id

        # Test negative numbers
        negative_id = -1
        result = validate_parameter("id", str(negative_id), int)
        assert result == -1

    def test_special_characters(self):
        """TC-5.1.2: Test special characters in strings."""
        # Test with various special characters
        special_chars = "'; DROP TABLE students; --"
        result = validate_parameter("text", special_chars, str)

        # Verify special characters handled safely
        assert isinstance(result, str)
        assert result == special_chars  # Should pass through unchanged

    def test_empty_strings(self):
        """Test empty string handling."""
        # Test empty string - should be valid for str type
        result = validate_parameter("optional", "", str)
        assert result == ""

        # Empty string to int should fail
        with pytest.raises(ValueError):
            validate_parameter("required", "", int)

    def test_none_values(self):
        """Test None value handling."""
        # None for required (non-optional) parameter
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("required", None, str)

        # None for Optional parameter (should be OK)
        result = validate_parameter("optional", None, str | None)
        assert result is None

    def test_literal_type(self):
        """Test Literal type validation (no isinstance with subscripted generic)."""
        DetailLevel = Literal["names", "signatures", "full"]
        for v in ("names", "signatures", "full"):
            result = validate_parameter("detail_level", v, DetailLevel)
            assert result == v
        with pytest.raises(ValueError, match="allowed values"):
            validate_parameter("detail_level", "invalid", DetailLevel)


class TestInjectionPrevention:
    """Test prevention of injection attacks."""

    def test_sql_injection_attempts(self):
        """TC-5.2.1: Test SQL injection prevention."""
        # Note: Canvas MCP uses API calls, not SQL
        # But we should ensure parameters aren't used in string concatenation

        injection_attempts = [
            "'; DROP TABLE students; --",
            "1' OR '1'='1",
            "admin'--",
            "' OR 1=1--",
        ]

        for attempt in injection_attempts:
            # Validate parameter treats these as literal strings
            result = validate_parameter("param", attempt, str)
            # Should be treated as literal string, not executed
            assert isinstance(result, str)
            assert result == attempt  # Unchanged

    def test_command_injection_prevention(self):
        """TC-5.2.1: Test command injection prevention."""
        command_injections = [
            "; ls -la",
            "| cat /etc/passwd",
            "&& rm -rf /",
            "`whoami`",
            "$(whoami)",
        ]

        for injection in command_injections:
            result = validate_parameter("param", injection, str)
            # Should be treated as literal string
            assert isinstance(result, str)
            assert result == injection  # Commands should not be executed

    def test_path_traversal_prevention(self):
        """TC-5.2.2: Test path traversal prevention."""
        path_traversals = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "/etc/passwd",
            "C:\\Windows\\System32",
            "./../...//..//etc/passwd",
        ]

        for path in path_traversals:
            # Verify path traversal patterns are handled safely
            result = validate_parameter("path", path, str)
            # Implementation should sanitize or reject
            assert isinstance(result, str)

    def test_xss_injection_attempts(self):
        """TC-5.2.3: Test XSS prevention."""
        xss_attempts = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src='javascript:alert(1)'>",
            "'-alert(1)-'",
        ]

        for xss in xss_attempts:
            result = validate_parameter("content", xss, str)
            # Should be treated as literal string
            # HTML encoding should happen on output, not input
            assert isinstance(result, str)


class TestParameterSanitization:
    """Test parameter sanitization."""

    def test_whitespace_handling(self):
        """Test whitespace in parameters."""
        # Leading/trailing whitespace
        result = validate_parameter("param", "  value  ", str)
        # May or may not strip - depends on implementation
        assert isinstance(result, str)

    def test_unicode_handling(self):
        """Test Unicode character handling."""
        unicode_strings = [
            "Hello 世界",  # Chinese
            "Привет мир",  # Russian
            "مرحبا العالم",  # Arabic
            "🎉🚀💯",  # Emojis
        ]

        for unicode_str in unicode_strings:
            result = validate_parameter("text", unicode_str, str)
            assert isinstance(result, str)
            assert result == unicode_str

    def test_length_limits(self):
        """Test extremely long input handling."""
        # Very long string
        long_string = "A" * 1000000  # 1 million characters

        # Should handle gracefully (accept or reject with clear error)
        try:
            result = validate_parameter("text", long_string, str)
            assert isinstance(result, str)
            assert len(result) == 1000000
        except ValueError:
            # Length limit exceeded - acceptable
            pass


class TestTypeCoercion:
    """Test type coercion safety."""

    def test_string_to_int_coercion(self):
        """Test safe string to integer conversion."""
        # Valid integer string
        result = validate_parameter("id", "12345", int)
        assert result == 12345
        assert isinstance(result, int)

        # Invalid integer string
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("id", "not_a_number", int)

    def test_string_to_list_coercion(self):
        """Test string to list conversion."""
        # Comma-separated string to list
        # Implementation depends on validation logic
        pass

    def test_type_confusion_prevention(self):
        """Test prevention of type confusion attacks."""
        # Attempt to confuse type system
        confusing_inputs = [
            "[object Object]",
            "true",  # String "true" vs boolean
            "null",  # String "null" vs None
        ]

        for input_val in confusing_inputs:
            # Should maintain type safety - strings stay strings
            result = validate_parameter("param", input_val, str)
            assert isinstance(result, str)
            assert result == input_val

        # Dict input should be converted to string
        result = validate_parameter("param", {"__proto__": "malicious"}, str)
        assert isinstance(result, str)


class TestConvertToBool:
    """Test _convert_to_bool() edge cases."""

    def test_bool_passthrough(self):
        """Bool values pass through unchanged."""
        assert _convert_to_bool("flag", True) is True
        assert _convert_to_bool("flag", False) is False

    def test_truthy_strings(self):
        """All truthy string variants convert to True."""
        for val in ("true", "True", "TRUE", "yes", "Yes", "YES", "1", "t", "T", "y", "Y"):
            assert _convert_to_bool("flag", val) is True

    def test_falsy_strings(self):
        """All falsy string variants convert to False."""
        for val in ("false", "False", "FALSE", "no", "No", "NO", "0", "f", "F", "n", "N"):
            assert _convert_to_bool("flag", val) is False

    def test_whitespace_trimmed(self):
        """Leading/trailing whitespace is trimmed before matching."""
        assert _convert_to_bool("flag", "  true  ") is True
        assert _convert_to_bool("flag", "\tfalse\n") is False

    def test_invalid_string_raises(self):
        """Unrecognized strings raise ValueError."""
        for val in ("maybe", "2", "", "truthy", "nope", "on", "off"):
            with pytest.raises(ValueError, match="could not be converted to bool"):
                _convert_to_bool("flag", val)

    def test_int_coercion(self):
        """Integers coerce via bool(): 0 is False, nonzero is True."""
        assert _convert_to_bool("flag", 0) is False
        assert _convert_to_bool("flag", 1) is True
        assert _convert_to_bool("flag", -1) is True
        assert _convert_to_bool("flag", 42) is True

    def test_float_coercion(self):
        """Floats coerce via bool(): 0.0 is False, nonzero is True."""
        assert _convert_to_bool("flag", 0.0) is False
        assert _convert_to_bool("flag", 1.5) is True

    def test_unsupported_types_raise(self):
        """Non-bool/str/numeric types raise ValueError."""
        for val in ([], {}, None, object()):
            with pytest.raises(ValueError, match="could not be converted to bool"):
                _convert_to_bool("flag", val)


class TestConvertToList:
    """Test _convert_to_list() including JSON array handling."""

    def test_list_passthrough(self):
        """List values pass through unchanged."""
        original = [1, 2, 3]
        assert _convert_to_list("ids", original) == [1, 2, 3]

    def test_empty_list_passthrough(self):
        """Empty list passes through."""
        assert _convert_to_list("ids", []) == []

    def test_json_array_string(self):
        """Valid JSON array strings are parsed."""
        assert _convert_to_list("ids", '[1, 2, 3]') == [1, 2, 3]
        assert _convert_to_list("names", '["alice", "bob"]') == ["alice", "bob"]

    def test_empty_json_array(self):
        """Empty JSON array string parses to empty list."""
        assert _convert_to_list("ids", '[]') == []

    def test_nested_json_array(self):
        """Nested JSON arrays are preserved."""
        assert _convert_to_list("data", '[[1, 2], [3, 4]]') == [[1, 2], [3, 4]]

    def test_json_object_falls_through_to_comma_split(self):
        """A JSON object string is not a list, so falls through to comma split."""
        result = _convert_to_list("data", '{"key": "val"}')
        # Not a JSON array, so treated as comma-separated
        assert isinstance(result, list)

    def test_comma_separated_values(self):
        """Comma-separated strings split into a list."""
        assert _convert_to_list("ids", "1,2,3") == ["1", "2", "3"]

    def test_comma_separated_with_spaces(self):
        """Whitespace around comma-separated items is trimmed."""
        assert _convert_to_list("ids", " a , b , c ") == ["a", "b", "c"]

    def test_single_value_string(self):
        """A string with no commas becomes a single-element list."""
        assert _convert_to_list("ids", "hello") == ["hello"]

    def test_empty_string_produces_empty_list(self):
        """Empty string produces empty list (no non-empty items after split)."""
        assert _convert_to_list("ids", "") == []

    def test_unsupported_type_raises(self):
        """Non-list/str types raise ValueError."""
        for val in (123, 4.5, True, None):
            with pytest.raises(ValueError, match="could not be converted to list"):
                _convert_to_list("ids", val)


class TestErrorMessages:
    """Test that error messages don't leak sensitive information."""

    def test_validation_errors_safe(self):
        """Verify validation errors don't expose system details."""
        try:
            validate_parameter("secret_param", None, str)
        except Exception as e:
            error_msg = str(e)

            # Error should be clear but not expose internals
            assert "secret_param" in error_msg  # Parameter name is ok
            # Should not contain file paths or stack traces in message
            assert "File" not in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

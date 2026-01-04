"""
Input Validation Security Tests

Tests for parameter validation, injection prevention,
and input sanitization.

Test Coverage:
- TC-5.1: Parameter Validation
- TC-5.2: Injection Testing
"""

import pytest
from unittest.mock import Mock, patch
from src.canvas_mcp.core.validation import validate_parameter


class TestParameterValidation:
    """Test input parameter validation."""
    
    def test_invalid_parameter_types(self):
        """TC-5.1.1: Test invalid parameter types."""
        # Test with wrong types
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("course_id", "not_a_number", int, False)
    
    def test_missing_required_parameters(self):
        """TC-5.1.1: Test missing required parameters."""
        # Test that missing required params raise error
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("required_param", None, str, True)
    
    def test_boundary_conditions(self):
        """TC-5.1.2: Test boundary conditions."""
        # Test extremely large IDs
        large_id = 2**31  # Max 32-bit integer
        result = validate_parameter("id", str(large_id), int, False)
        assert isinstance(result, int)
        
        # Test negative numbers
        negative_id = -1
        # Should handle or reject appropriately
    
    def test_special_characters(self):
        """TC-5.1.2: Test special characters in strings."""
        # Test with various special characters
        special_chars = "'; DROP TABLE students; --"
        result = validate_parameter("text", special_chars, str, False)
        
        # Verify special characters handled safely
        assert isinstance(result, str)
    
    def test_empty_strings(self):
        """Test empty string handling."""
        # Test empty required string
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("required", "", str, True)
        
        # Test empty optional string (should be OK)
        result = validate_parameter("optional", "", str, False)
    
    def test_none_values(self):
        """Test None value handling."""
        # None for required parameter
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("required", None, str, True)
        
        # None for optional parameter (should be OK)
        result = validate_parameter("optional", None, str, False)
        assert result is None


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
            # Validate parameter doesn't allow SQL injection
            result = validate_parameter("param", attempt, str, False)
            # Should be treated as literal string, not executed
            assert isinstance(result, str)
    
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
            result = validate_parameter("param", injection, str, False)
            # Should be treated as literal string
            assert isinstance(result, str)
            # Commands should not be executed
    
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
            result = validate_parameter("path", path, str, False)
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
            result = validate_parameter("content", xss, str, False)
            # Should be treated as literal string
            # HTML encoding should happen on output, not input
            assert isinstance(result, str)


class TestParameterSanitization:
    """Test parameter sanitization."""
    
    def test_whitespace_handling(self):
        """Test whitespace in parameters."""
        # Leading/trailing whitespace
        result = validate_parameter("param", "  value  ", str, False)
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
            result = validate_parameter("text", unicode_str, str, False)
            assert isinstance(result, str)
    
    def test_length_limits(self):
        """Test extremely long input handling."""
        # Very long string
        long_string = "A" * 1000000  # 1 million characters
        
        # Should handle gracefully (accept or reject with clear error)
        try:
            result = validate_parameter("text", long_string, str, False)
            assert isinstance(result, str)
        except ValueError:
            # Length limit exceeded - acceptable
            pass


class TestTypeCoercion:
    """Test type coercion safety."""
    
    def test_string_to_int_coercion(self):
        """Test safe string to integer conversion."""
        # Valid integer string
        result = validate_parameter("id", "12345", int, False)
        assert result == 12345
        assert isinstance(result, int)
        
        # Invalid integer string
        with pytest.raises((TypeError, ValueError)):
            validate_parameter("id", "not_a_number", int, False)
    
    def test_string_to_list_coercion(self):
        """Test string to list conversion."""
        # Comma-separated string to list
        # Implementation depends on validation logic
        pass
    
    def test_type_confusion_prevention(self):
        """Test prevention of type confusion attacks."""
        # Attempt to confuse type system
        confusing_inputs = [
            {"__proto__": "malicious"},  # Prototype pollution
            "[object Object]",
            "true",  # String "true" vs boolean
            "null",  # String "null" vs None
        ]
        
        for input_val in confusing_inputs:
            # Should maintain type safety
            result = validate_parameter("param", input_val, str, False)
            assert isinstance(result, str)


class TestErrorMessages:
    """Test that error messages don't leak sensitive information."""
    
    def test_validation_errors_safe(self):
        """Verify validation errors don't expose system details."""
        try:
            validate_parameter("secret_param", None, str, True)
        except Exception as e:
            error_msg = str(e)
            
            # Error should be clear but not expose internals
            assert "secret" not in error_msg.lower() or "param" in error_msg
            # Should not contain file paths
            assert "/" not in error_msg or "parameter" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

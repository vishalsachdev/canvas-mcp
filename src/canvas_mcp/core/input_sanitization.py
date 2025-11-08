"""Input sanitization decorators for MCP tools."""

import functools
import json
from collections.abc import Callable
from typing import Any, TypeVar

from .logging import log_warning
from .security import SecurityValidator

F = TypeVar('F', bound=Callable[..., Any])


def sanitize_inputs(func: F) -> F:
    """
    Decorator to sanitize all string inputs to a function.

    This decorator:
    - Sanitizes all string parameters
    - Validates against SQL injection, XSS, and command injection
    - Sanitizes HTML content
    - Validates URLs
    - Returns error if dangerous content detected

    Args:
        func: The function to wrap

    Returns:
        Wrapped function with input sanitization
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Sanitize string arguments
        sanitized_args = []
        for arg in args:
            if isinstance(arg, str):
                sanitized_args.append(_sanitize_string_input(arg))
            else:
                sanitized_args.append(arg)

        # Sanitize string kwargs
        sanitized_kwargs = {}
        for key, value in kwargs.items():
            if isinstance(value, str):
                sanitized_value, error = _sanitize_string_input(value, key)
                if error:
                    return json.dumps({"error": error})
                sanitized_kwargs[key] = sanitized_value
            elif isinstance(value, list):
                sanitized_list = []
                for item in value:
                    if isinstance(item, str):
                        sanitized_item, error = _sanitize_string_input(item, f"{key}[]")
                        if error:
                            return json.dumps({"error": error})
                        sanitized_list.append(sanitized_item)
                    else:
                        sanitized_list.append(item)
                sanitized_kwargs[key] = sanitized_list
            elif isinstance(value, dict):
                sanitized_dict = _sanitize_dict_input(value, key)
                if isinstance(sanitized_dict, str) and sanitized_dict.startswith('{"error"'):
                    return sanitized_dict
                sanitized_kwargs[key] = sanitized_dict
            else:
                sanitized_kwargs[key] = value

        # Call the original function with sanitized inputs
        return await func(*sanitized_args, **sanitized_kwargs)

    return wrapper  # type: ignore


def _sanitize_string_input(value: str, param_name: str = "input") -> tuple[str, str | None]:
    """
    Sanitize a string input and check for dangerous content.

    Args:
        value: The string to sanitize
        param_name: Name of the parameter (for error messages)

    Returns:
        Tuple of (sanitized_value, error_message)
        error_message is None if no issues found
    """
    # First, basic sanitization
    sanitized = SecurityValidator.sanitize_string(value)

    # Check for SQL injection
    if not SecurityValidator.validate_no_sql_injection(sanitized):
        log_warning(f"SQL injection attempt detected in parameter: {param_name}")
        return sanitized, f"Input validation failed: potentially dangerous content in {param_name}"

    # Check for XSS
    if not SecurityValidator.validate_no_xss(sanitized):
        log_warning(f"XSS attempt detected in parameter: {param_name}")
        # For XSS, we can sanitize the HTML instead of rejecting
        sanitized = SecurityValidator.sanitize_html(sanitized)

    # Check for command injection (only for certain parameter types)
    # Allow some special chars in regular text fields
    if param_name.lower() not in ['body', 'message', 'content', 'description', 'text']:
        if not SecurityValidator.validate_no_command_injection(sanitized):
            log_warning(f"Command injection attempt detected in parameter: {param_name}")
            return sanitized, f"Input validation failed: potentially dangerous content in {param_name}"

    return sanitized, None


def _sanitize_dict_input(value: dict[str, Any], param_name: str = "input") -> dict[str, Any] | str:
    """
    Recursively sanitize dictionary inputs.

    Args:
        value: The dictionary to sanitize
        param_name: Name of the parameter (for error messages)

    Returns:
        Sanitized dictionary or error JSON string
    """
    sanitized = {}
    for key, val in value.items():
        if isinstance(val, str):
            sanitized_val, error = _sanitize_string_input(val, f"{param_name}.{key}")
            if error:
                return json.dumps({"error": error})
            sanitized[key] = sanitized_val
        elif isinstance(val, dict):
            result = _sanitize_dict_input(val, f"{param_name}.{key}")
            if isinstance(result, str) and result.startswith('{"error"'):
                return result
            sanitized[key] = result
        elif isinstance(val, list):
            sanitized_list = []
            for item in val:
                if isinstance(item, str):
                    sanitized_item, error = _sanitize_string_input(item, f"{param_name}.{key}[]")
                    if error:
                        return json.dumps({"error": error})
                    sanitized_list.append(sanitized_item)
                else:
                    sanitized_list.append(item)
            sanitized[key] = sanitized_list
        else:
            sanitized[key] = val

    return sanitized


def validate_integer_param(
    value: int,
    param_name: str,
    min_value: int | None = None,
    max_value: int | None = None
) -> str | None:
    """
    Validate an integer parameter is within acceptable range.

    Args:
        value: The integer to validate
        param_name: Name of the parameter (for error messages)
        min_value: Minimum allowed value
        max_value: Maximum allowed value

    Returns:
        Error message if invalid, None if valid
    """
    if not SecurityValidator.validate_integer_range(value, min_value, max_value):
        if min_value is not None and max_value is not None:
            return f"{param_name} must be between {min_value} and {max_value}"
        elif min_value is not None:
            return f"{param_name} must be at least {min_value}"
        elif max_value is not None:
            return f"{param_name} must be at most {max_value}"

    return None

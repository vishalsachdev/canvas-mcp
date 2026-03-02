"""Parameter validation system for MCP tools."""

import functools
import inspect
import json
import types
from collections.abc import Callable
from typing import (
    Any,
    Literal,
    TypeVar,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from .logging import log_debug, log_error

# Type definitions for parameter validation
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

# Boolean string constants
TRUTHY_VALUES = frozenset({"true", "yes", "1", "t", "y"})
FALSY_VALUES = frozenset({"false", "no", "0", "f", "n"})


def format_error(message: str, details: str | None = None) -> dict[str, str]:
    """
    Format an error response consistently.

    Args:
        message: Primary error message
        details: Optional additional details

    Returns:
        Standardized error dictionary

    Example:
        >>> format_error("Invalid course ID", "Course 12345 not found")
        {"error": "Invalid course ID", "details": "Course 12345 not found"}
    """
    result: dict[str, str] = {"error": message}
    if details:
        result["details"] = details
    return result


def is_error_response(response: Any) -> bool:
    """
    Check if a response is an error.

    Args:
        response: Response to check

    Returns:
        True if response contains an error
    """
    return isinstance(response, dict) and "error" in response


# ---------------------------------------------------------------------------
# Type-specific conversion / validation helpers
# ---------------------------------------------------------------------------

def _validate_optional(param_name: str, value: Any, args: tuple[Any, ...]) -> tuple[Any, Any, tuple[Any, ...]]:
    """Handle Optional types (Union[type, None]).

    Extracts the non-None type(s) from an Optional/Union-with-None and
    returns the unwrapped expected_type along with updated origin and args.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to validate
        args: The type args from the Union

    Returns:
        Tuple of (expected_type, origin, args) after unwrapping Optional
    """
    non_none_types = [t for t in args if t is not type(None)]
    if len(non_none_types) == 1:
        expected_type = non_none_types[0]
    else:
        # It's a Union of multiple types plus None
        union_type = non_none_types[0]
        for candidate in non_none_types[1:]:
            union_type = union_type | candidate
        expected_type = union_type

    origin = get_origin(expected_type)
    args = get_args(expected_type)
    return expected_type, origin, args


def _validate_union(param_name: str, value: Any, args: tuple[Any, ...]) -> Any:
    """Handle Union types by trying each type in order.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to validate and convert
        args: The type args from the Union

    Returns:
        The validated and converted value

    Raises:
        ValueError: If none of the Union types match
    """
    errors = []
    for arg_type in args:
        if arg_type is type(None) and value is None:
            return None

        try:
            return validate_parameter(param_name, value, arg_type)
        except ValueError as e:
            errors.append(str(e))

    # If we get here, none of the types worked
    type_names = ", ".join(str(t) for t in args)
    raise ValueError(f"Parameter '{param_name}' with value '{value}' (type: {type(value).__name__}) "
                    f"could not be converted to any of the expected types: {type_names}")


def _validate_literal(param_name: str, value: Any, expected_type: Any) -> Any:
    """Handle Literal types (e.g. Literal["names", "signatures", "full"]).

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to validate
        expected_type: The Literal type to validate against

    Returns:
        The value if it matches one of the allowed literals

    Raises:
        ValueError: If value is not in the allowed set
    """
    allowed = get_args(expected_type)
    if value in allowed:
        return value
    allowed_repr = ", ".join(repr(a) for a in allowed)
    raise ValueError(
        f"Parameter '{param_name}' with value {value!r} is not one of the allowed values: {allowed_repr}"
    )


def _convert_to_int(param_name: str, value: Any) -> int:
    """Convert a value to int.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to convert

    Returns:
        The integer value

    Raises:
        ValueError: If conversion fails
    """
    try:
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"Parameter '{param_name}' is an empty string, cannot convert to int")
        return int(value)
    except (ValueError, TypeError) as err:
        raise ValueError(
            f"Parameter '{param_name}' with value '{value}' could not be converted to int"
        ) from err


def _convert_to_float(param_name: str, value: Any) -> float:
    """Convert a value to float.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to convert

    Returns:
        The float value

    Raises:
        ValueError: If conversion fails
    """
    try:
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"Parameter '{param_name}' is an empty string, cannot convert to float")
        return float(value)
    except (ValueError, TypeError) as err:
        raise ValueError(
            f"Parameter '{param_name}' with value '{value}' could not be converted to float"
        ) from err


def _convert_to_bool(param_name: str, value: Any) -> bool:
    """Convert a value to bool.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to convert

    Returns:
        The boolean value

    Raises:
        ValueError: If conversion fails
    """
    if isinstance(value, bool):
        return value
    elif isinstance(value, str):
        value_lower = value.lower().strip()
        if value_lower in TRUTHY_VALUES:
            return True
        elif value_lower in FALSY_VALUES:
            return False
        else:
            raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to bool")
    elif isinstance(value, (int, float)):
        return bool(value)
    else:
        raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to bool")


def _convert_to_list(param_name: str, value: Any) -> list:
    """Convert a value to list.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to convert

    Returns:
        The list value

    Raises:
        ValueError: If conversion fails
    """
    if isinstance(value, list):
        return value
    elif isinstance(value, str):
        # Try to parse as JSON array
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            log_debug(f"JSON parse failed for list parameter '{param_name}', trying comma-separated")

        # Try comma-separated values
        return [item.strip() for item in value.split(',') if item.strip()]
    else:
        raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to list")


def _convert_to_dict(param_name: str, value: Any) -> dict:
    """Convert a value to dict.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to convert

    Returns:
        The dict value

    Raises:
        ValueError: If conversion fails
    """
    if isinstance(value, dict):
        return value
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            else:
                raise ValueError(f"Parameter '{param_name}' parsed as JSON but is not a dict")
        except json.JSONDecodeError as err:
            raise ValueError(
                f"Parameter '{param_name}' with value '{value}' could not be parsed as JSON dict"
            ) from err
    else:
        raise ValueError(f"Parameter '{param_name}' with value '{value}' could not be converted to dict")


# Type-dispatch mapping for basic types
_TYPE_DISPATCH: dict[type, Callable[[str, Any], Any]] = {
    str: lambda param_name, value: str(value),
    int: _convert_to_int,
    float: _convert_to_float,
    bool: _convert_to_bool,
    list: _convert_to_list,
    dict: _convert_to_dict,
}


def validate_parameter(param_name: str, value: Any, expected_type: Any) -> Any:
    """
    Validate and convert a parameter to the expected type.

    Args:
        param_name: Name of the parameter (for error messages)
        value: The value to validate and convert
        expected_type: The expected Python type

    Returns:
        The validated and converted value

    Raises:
        ValueError: If validation fails
    """
    # Special handling for Union types (e.g., Union[int, str])
    origin = get_origin(expected_type)
    args = get_args(expected_type)

    # Handle Optional types (which are Union[type, None])
    is_optional = False
    if origin in (Union, types.UnionType) and args and type(None) in args:
        is_optional = True
        expected_type, origin, args = _validate_optional(param_name, value, args)

    # Handle None values for optional parameters
    if value is None:
        if is_optional:
            return None
        else:
            raise ValueError(f"Parameter '{param_name}' cannot be None")

    # Handle Union types (including those extracted from Optional)
    if origin in (Union, types.UnionType):
        return _validate_union(param_name, value, args)

    # Handle Literal types (e.g. Literal["names", "signatures", "full"])
    if origin is Literal:
        return _validate_literal(param_name, value, expected_type)

    # Handle basic types with dispatch
    if expected_type in _TYPE_DISPATCH:
        return _TYPE_DISPATCH[expected_type](param_name, value)

    # For parameterized generic types (e.g. list[str], dict[str, int]),
    # dispatch on the origin type
    if origin in _TYPE_DISPATCH:
        return _TYPE_DISPATCH[origin](param_name, value)

    # For other types, just check if it's an instance
    if isinstance(value, expected_type):
        return value

    # If we get here, validation failed
    raise ValueError(f"Parameter '{param_name}' with value '{value}' (type: {type(value).__name__}) "
                    f"is not compatible with expected type: {expected_type}")


def validate_params(func: F) -> F:
    """Decorator to validate function parameters based on type hints."""
    sig = inspect.signature(func)
    type_hints = get_type_hints(func)

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Combine args and kwargs based on function signature
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()

        # Validate each parameter
        for param_name, param_value in bound_args.arguments.items():
            if param_name in type_hints:
                expected_type = type_hints[param_name]
                try:
                    # Skip return type annotation
                    if param_name != "return":
                        bound_args.arguments[param_name] = validate_parameter(param_name, param_value, expected_type)
                except ValueError as e:
                    # Return error as JSON response
                    error_message = str(e)
                    log_error(f"Parameter validation error: {error_message}", param_name=param_name, value=param_value)
                    return json.dumps({"error": error_message})

        # Call the original function with validated parameters
        return await func(**bound_args.arguments)

    return cast(F, wrapper)

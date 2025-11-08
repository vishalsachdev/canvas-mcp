"""Tests for validation utilities."""

import pytest

from canvas_mcp.core.validation import validate_params


def test_validate_params_with_valid_inputs() -> None:
    """Test validation decorator with valid inputs."""

    @validate_params
    async def test_func(course_id: str, assignment_id: int) -> str:
        return f"{course_id}-{assignment_id}"

    # Should not raise any exceptions
    result = test_func("12345", 67890)
    assert result is not None


def test_validate_params_with_empty_string() -> None:
    """Test validation decorator rejects empty strings."""

    @validate_params
    async def test_func(course_id: str) -> str:
        return course_id

    with pytest.raises(ValueError, match="cannot be empty"):
        test_func("")


def test_validate_params_with_whitespace_string() -> None:
    """Test validation decorator rejects whitespace-only strings."""

    @validate_params
    async def test_func(course_id: str) -> str:
        return course_id

    with pytest.raises(ValueError, match="cannot be empty"):
        test_func("   ")


def test_validate_params_with_none() -> None:
    """Test validation decorator rejects None values."""

    @validate_params
    async def test_func(course_id: str) -> str:
        return course_id

    with pytest.raises(ValueError, match="cannot be None or empty"):
        test_func(None)  # type: ignore


def test_validate_params_allows_optional() -> None:
    """Test validation decorator allows optional parameters."""

    @validate_params
    async def test_func(course_id: str, optional_param: str | None = None) -> str:
        return course_id

    # Should not raise exception for None optional parameter
    result = test_func("12345", None)
    assert result is not None


def test_validate_params_with_integers() -> None:
    """Test validation decorator with integer parameters."""

    @validate_params
    async def test_func(course_id: int, assignment_id: int) -> str:
        return f"{course_id}-{assignment_id}"

    # Should not raise exceptions for valid integers
    result = test_func(12345, 67890)
    assert result is not None


def test_validate_params_preserves_function_metadata() -> None:
    """Test validation decorator preserves function metadata."""

    @validate_params
    async def test_func(param: str) -> str:
        """Test function docstring."""
        return param

    assert test_func.__name__ == "test_func"
    assert test_func.__doc__ == "Test function docstring."

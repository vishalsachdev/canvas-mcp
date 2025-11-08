"""Tests for caching utilities."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.core.cache import (
    course_code_to_id_cache,
    get_course_code,
    get_course_id,
    id_to_course_code_cache,
)


@pytest.fixture(autouse=True)
def clear_caches() -> None:
    """Clear caches before each test."""
    course_code_to_id_cache.clear()
    id_to_course_code_cache.clear()


@pytest.mark.asyncio
async def test_get_course_id_from_cache() -> None:
    """Test getting course ID from cache."""
    # Populate cache
    course_code_to_id_cache["TEST_101"] = "12345"

    result = await get_course_id("TEST_101")
    assert result == "12345"


@pytest.mark.asyncio
async def test_get_course_id_from_api(mock_env: dict[str, str]) -> None:
    """Test getting course ID from API when not in cache."""
    mock_response = [
        {"id": 12345, "course_code": "TEST_101"},
        {"id": 67890, "course_code": "TEST_102"},
    ]

    with patch("canvas_mcp.core.cache.fetch_all_paginated_results") as mock_fetch:
        mock_fetch.return_value = mock_response

        result = await get_course_id("TEST_101")

        assert result == "12345"
        # Check that cache was populated
        assert course_code_to_id_cache["TEST_101"] == "12345"
        assert id_to_course_code_cache["12345"] == "TEST_101"


@pytest.mark.asyncio
async def test_get_course_id_already_numeric() -> None:
    """Test getting course ID when input is already numeric."""
    result = await get_course_id("12345")
    assert result == "12345"

    result = await get_course_id(12345)
    assert result == "12345"


@pytest.mark.asyncio
async def test_get_course_code_from_cache() -> None:
    """Test getting course code from cache."""
    # Populate cache
    id_to_course_code_cache["12345"] = "TEST_101"

    result = await get_course_code("12345")
    assert result == "TEST_101"


@pytest.mark.asyncio
async def test_get_course_code_from_api(mock_env: dict[str, str]) -> None:
    """Test getting course code from API when not in cache."""
    mock_response = {"id": 12345, "course_code": "TEST_101"}

    with patch("canvas_mcp.core.cache.make_canvas_request") as mock_request:
        mock_request.return_value = mock_response

        result = await get_course_code("12345")

        assert result == "TEST_101"
        # Check that cache was populated
        assert id_to_course_code_cache["12345"] == "TEST_101"
        assert course_code_to_id_cache["TEST_101"] == "12345"

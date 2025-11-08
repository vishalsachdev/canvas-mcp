"""Tests for course-related tools."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_strip_html_tags() -> None:
    """Test HTML tag stripping utility."""
    from canvas_mcp.tools.courses import strip_html_tags

    html = "<p>This is <strong>bold</strong> text</p>"
    result = strip_html_tags(html)
    assert result == "This is bold text"

    # Test with HTML entities
    html = "Test&nbsp;&amp;&lt;&gt;&quot;"
    result = strip_html_tags(html)
    assert result == "Test & < > \""

    # Test with empty string
    result = strip_html_tags("")
    assert result == ""

    # Test with None
    result = strip_html_tags(None)  # type: ignore
    assert result == ""


@pytest.mark.asyncio
async def test_list_courses(mock_env: dict[str, str]) -> None:
    """Test list_courses tool."""
    from canvas_mcp.tools.courses import register_course_tools
    from mcp.server.fastmcp import FastMCP

    mock_courses = [
        {
            "id": 12345,
            "name": "Test Course 1",
            "course_code": "TEST_101",
        },
        {
            "id": 67890,
            "name": "Test Course 2",
            "course_code": "TEST_102",
        },
    ]

    mcp = FastMCP("test")

    with patch("canvas_mcp.tools.courses.fetch_all_paginated_results") as mock_fetch:
        mock_fetch.return_value = mock_courses

        register_course_tools(mcp)

        # Get the registered tool
        list_courses_func = None
        for tool in mcp._tools:
            if tool.name == "list_courses":
                list_courses_func = tool.func
                break

        assert list_courses_func is not None

        result = await list_courses_func()

        assert "TEST_101" in result
        assert "TEST_102" in result
        assert "Test Course 1" in result
        assert "Test Course 2" in result


@pytest.mark.asyncio
async def test_list_courses_error(mock_env: dict[str, str]) -> None:
    """Test list_courses tool with API error."""
    from canvas_mcp.tools.courses import register_course_tools
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("test")

    with patch("canvas_mcp.tools.courses.fetch_all_paginated_results") as mock_fetch:
        mock_fetch.return_value = {"error": "API Error"}

        register_course_tools(mcp)

        # Get the registered tool
        list_courses_func = None
        for tool in mcp._tools:
            if tool.name == "list_courses":
                list_courses_func = tool.func
                break

        assert list_courses_func is not None

        result = await list_courses_func()

        assert "Error" in result


@pytest.mark.asyncio
async def test_get_course_details(mock_env: dict[str, str]) -> None:
    """Test get_course_details tool."""
    from canvas_mcp.tools.courses import register_course_tools
    from mcp.server.fastmcp import FastMCP

    mock_course = {
        "id": 12345,
        "name": "Test Course",
        "course_code": "TEST_101",
        "start_at": "2024-01-01T00:00:00Z",
        "end_at": "2024-12-31T23:59:59Z",
        "time_zone": "America/Chicago",
        "default_view": "modules",
        "is_public": False,
        "blueprint": False,
    }

    mcp = FastMCP("test")

    with patch("canvas_mcp.tools.courses.make_canvas_request") as mock_request, \
         patch("canvas_mcp.tools.courses.get_course_id") as mock_get_id:
        mock_request.return_value = mock_course
        mock_get_id.return_value = "12345"

        register_course_tools(mcp)

        # Get the registered tool
        get_details_func = None
        for tool in mcp._tools:
            if tool.name == "get_course_details":
                get_details_func = tool.func
                break

        assert get_details_func is not None

        result = await get_details_func("TEST_101")

        assert "TEST_101" in result
        assert "Test Course" in result
        assert "America/Chicago" in result

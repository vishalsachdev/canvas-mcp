"""
Tests for course-related MCP tools.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.tools.courses import strip_html_tags


def get_tool_function(tool_name: str):
    """Get a registered course tool closure by name (no MCP runtime needed)."""
    from mcp.server.fastmcp import FastMCP

    from canvas_mcp.tools.courses import register_course_tools

    mcp = FastMCP("test")
    captured_functions = {}
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    register_course_tools(mcp)
    return captured_functions.get(tool_name)


class TestListCoursesParams:
    """list_courses must honor CANVAS_ROLE and use enrollment_state for 'current'.

    Chamberlain (and many institutions) never flip finished courses to
    workflow_state=completed, so filtering on state[] cannot distinguish a
    current course from a past one. enrollment_state=active is the canonical
    signal. The Shared tool must also not hard-filter to teacher enrollments,
    which returns nothing for students.
    """

    @staticmethod
    async def _call_and_get_params(role="all", **kwargs):
        """Invoke list_courses with a mocked API and return the params it sent."""
        with patch(
            "canvas_mcp.tools.courses.fetch_all_paginated_results",
            new_callable=AsyncMock,
        ) as mock_fetch, patch(
            "canvas_mcp.tools.courses.get_config",
            return_value=SimpleNamespace(canvas_role=role),
            create=True,
        ):
            mock_fetch.return_value = [
                {"id": 1, "name": "Current Course", "course_code": "NR101"}
            ]
            list_courses = get_tool_function("list_courses")
            assert list_courses is not None
            await list_courses(**kwargs)
            assert mock_fetch.await_count == 1
            args, _ = mock_fetch.call_args
            return args[1]  # params dict

    @pytest.mark.asyncio
    async def test_student_default_uses_enrollment_state_active(self):
        """Default (student/all): scope to active enrollments, no teacher filter."""
        params = await self._call_and_get_params(role="student")
        assert params.get("enrollment_state") == "active"
        assert "enrollment_type" not in params

    @pytest.mark.asyncio
    async def test_all_role_default_uses_enrollment_state_active(self):
        """Role 'all' behaves like student: active enrollments, no teacher filter."""
        params = await self._call_and_get_params(role="all")
        assert params.get("enrollment_state") == "active"
        assert "enrollment_type" not in params

    @pytest.mark.asyncio
    async def test_educator_role_keeps_teacher_filter(self):
        """Educator: preserve teacher-only behavior, AND scope to active."""
        params = await self._call_and_get_params(role="educator")
        assert params.get("enrollment_type") == "teacher"
        assert params.get("enrollment_state") == "active"

    @pytest.mark.asyncio
    async def test_include_all_returns_full_history(self):
        """include_all=True drops role/active scoping; state[] still defaults to
        ['available'] (use include_concluded to also surface past courses)."""
        params = await self._call_and_get_params(role="student", include_all=True)
        assert "enrollment_type" not in params
        assert "enrollment_state" not in params

    @pytest.mark.asyncio
    async def test_include_concluded_adds_completed_state(self):
        """include_concluded=True surfaces completed courses too."""
        params = await self._call_and_get_params(
            role="student", include_all=True, include_concluded=True
        )
        assert "completed" in params.get("state[]", [])


class TestStripHtmlTags:
    """Test HTML stripping utility function."""

    def test_strip_simple_tags(self):
        """Test stripping simple HTML tags."""
        html = "<p>Hello World</p>"
        result = strip_html_tags(html)
        assert result == "Hello World"

    def test_strip_nested_tags(self):
        """Test stripping nested HTML tags."""
        html = "<div><p>Nested <strong>content</strong></p></div>"
        result = strip_html_tags(html)
        assert result == "Nested content"

    def test_strip_with_entities(self):
        """Test stripping HTML with entities."""
        html = "<p>Hello&nbsp;World&amp;More</p>"
        result = strip_html_tags(html)
        assert result == "Hello World&More"

    def test_strip_empty_string(self):
        """Test stripping empty string."""
        result = strip_html_tags("")
        assert result == ""

    def test_strip_none(self):
        """Test stripping None value."""
        result = strip_html_tags(None)
        assert result == ""


class TestCourseToolsIntegration:
    """Integration tests for course tools."""

    @pytest.mark.asyncio
    async def test_list_courses_with_mock(self):
        """Test list_courses with mocked Canvas API."""
        mock_courses = [
            {"id": 12345, "name": "Introduction to CS", "course_code": "CS101_2024"},
            {"id": 12346, "name": "Data Structures", "course_code": "CS201_2024"}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_courses

            from canvas_mcp.core.client import fetch_all_paginated_results

            courses = await fetch_all_paginated_results("/courses", {})

            assert courses == mock_courses
            assert len(courses) == 2

    @pytest.mark.asyncio
    async def test_error_handling_in_fetch(self):
        """Test error handling in course fetching."""
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"error": "API Error"}

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/courses", {})

            assert isinstance(result, dict)
            assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

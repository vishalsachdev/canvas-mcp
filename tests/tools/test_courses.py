"""
Tests for course-related MCP tools.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.tools.courses import strip_html_tags


def get_tool_function(tool_name: str):
    """Capture a registered course tool function by name without MCP plumbing.

    Wraps ``mcp.tool`` to grab each tool's undecorated coroutine, keyed by
    ``fn.__name__``. This relies on the ``@validate_params`` wrapper preserving
    ``__name__`` (it uses ``functools.wraps``); if that ever changes, lookups
    here would return ``None`` and the assertions below would fail loudly.
    """
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


# A syllabus longer than the 1000-char overview preview, to prove no truncation.
LONG_SYLLABUS_HTML = (
    "<h2>Course Syllabus</h2>"
    "<p>" + ("Intro content. " * 80) + "</p>"
    "<h3>Grading Policy</h3>"
    "<p>Final exam is weighted at 40% of the total grade.</p>"
)


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

    def test_strip_script_and_style_blocks(self):
        """<script>/<style> block contents must not leak into plain text."""
        html_content = (
            "<style>.a{color:red}</style><p>Real content</p>"
            "<script>alert('x')</script>"
        )
        result = strip_html_tags(html_content)
        assert "Real content" in result
        assert "color:red" not in result
        assert "alert" not in result

    def test_strip_extended_entities(self):
        """Entities beyond the old 5-entry table (smart quotes, dashes, hex) decode."""
        html_content = "<p>Weeks 1&ndash;3 use the instructor&rsquo;s &#x201C;rubric&#x201D;</p>"
        result = strip_html_tags(html_content)
        assert result == "Weeks 1–3 use the instructor’s “rubric”"

    def test_strip_empty_string(self):
        """Test stripping empty string."""
        result = strip_html_tags("")
        assert result == ""

    def test_strip_none(self):
        """Test stripping None value."""
        result = strip_html_tags(None)
        assert result == ""

    def test_block_elements_do_not_concatenate(self):
        """Adjacent block elements must be separated, not run together."""
        html = "<h3>Grading</h3><p>Final exam is 40%.</p>"
        result = strip_html_tags(html)
        # The bug: "GradingFinal exam is 40%." — block boundary must be kept.
        assert "GradingFinal" not in result
        assert "Grading" in result
        assert "Final exam is 40%." in result
        # Blocks land on separate lines.
        assert result == "Grading\nFinal exam is 40%."

    def test_list_items_separated(self):
        """List items are placed on their own lines."""
        html = "<ul><li>Homework 30%</li><li>Final 70%</li></ul>"
        result = strip_html_tags(html)
        assert "Homework 30%" in result
        assert "Final 70%" in result
        assert "30%Final" not in result


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


class TestGetSyllabus:
    """Tests for the get_syllabus tool."""

    @pytest.fixture
    def mock_api(self):
        with patch('canvas_mcp.tools.courses.get_course_id', new_callable=AsyncMock) as mock_id, \
             patch('canvas_mcp.tools.courses.make_canvas_request', new_callable=AsyncMock) as mock_req:
            mock_id.return_value = "60366"
            yield {'get_course_id': mock_id, 'make_canvas_request': mock_req}

    @pytest.mark.asyncio
    async def test_returns_full_syllabus_no_truncation(self, mock_api):
        """The full syllabus is returned, including content past the old 1000-char preview."""
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": LONG_SYLLABUS_HTML,
        }

        get_syllabus = get_tool_function('get_syllabus')
        assert get_syllabus is not None

        result = await get_syllabus("CS101")

        # The grading section lives well past 1000 chars and must not be cut.
        assert "Final exam is weighted at 40%" in result
        assert "Grading Policy" in result
        assert "[truncated" not in result  # explicit truncation marker must be absent
        # include[]=syllabus_body must be requested
        mock_api['make_canvas_request'].assert_called_once_with(
            "get", "/courses/60366", params={"include[]": "syllabus_body"}
        )

    @pytest.mark.asyncio
    async def test_html_format_returns_raw_body(self, mock_api):
        """output_format='html' returns the raw HTML, not stripped text."""
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": "<p>Hello <strong>World</strong></p>",
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101", output_format="html")

        # Raw HTML is returned verbatim; no stripped-text section in html-only mode.
        assert "<strong>World</strong>" in result
        assert "--- Plain Text ---" not in result

    @pytest.mark.asyncio
    async def test_both_format_includes_text_and_html(self, mock_api):
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": "<p>Hello World</p>",
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101", output_format="both")

        assert "Plain Text" in result
        assert "Raw HTML" in result
        assert "Hello World" in result
        assert "<p>Hello World</p>" in result

    @pytest.mark.asyncio
    async def test_format_case_insensitive(self, mock_api):
        """output_format is normalized with .lower() — 'Both' works like 'both'."""
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": "<p>Hello</p>",
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101", output_format="Both")

        assert "invalid output_format" not in result
        assert "Hello" in result
        assert "<p>Hello</p>" in result  # 'both' includes the raw HTML section

    @pytest.mark.asyncio
    async def test_max_chars_truncates_explicitly(self, mock_api):
        """max_chars truncates but flags it — no silent truncation."""
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": "<p>" + ("word " * 200) + "</p>",
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101", output_format="text", max_chars=50)

        assert "[truncated at 50 characters]" in result

    @pytest.mark.asyncio
    async def test_max_chars_zero_rejected(self, mock_api):
        """max_chars=0 is invalid and rejected before any API call."""
        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101", max_chars=0)

        assert "max_chars must be a positive integer" in result
        # Validation happens before any I/O — neither lookup nor Canvas runs.
        mock_api['get_course_id'].assert_not_called()
        mock_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_max_chars_negative_rejected(self, mock_api):
        """Negative max_chars is rejected by the same positive-int guard."""
        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101", max_chars=-5)

        assert "max_chars must be a positive integer" in result
        mock_api['get_course_id'].assert_not_called()
        mock_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_syllabus(self, mock_api):
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": "",
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101")

        assert "No syllabus content found" in result

    @pytest.mark.asyncio
    async def test_whitespace_only_syllabus(self, mock_api):
        """A whitespace-only body is treated as no content."""
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": "   \n  ",
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101")

        assert "No syllabus content found" in result

    @pytest.mark.asyncio
    async def test_null_syllabus_body(self, mock_api):
        """Canvas may return syllabus_body: null — treated as no content."""
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": None,
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101")

        assert "No syllabus content found" in result

    @pytest.mark.asyncio
    async def test_invalid_format(self, mock_api):
        mock_api['make_canvas_request'].return_value = {
            "course_code": "CS101",
            "syllabus_body": "<p>Hello</p>",
        }

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("CS101", output_format="pdf")

        assert "invalid output_format" in result
        # Validation happens before any I/O — neither lookup nor Canvas runs.
        mock_api['get_course_id'].assert_not_called()
        mock_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_api_error(self, mock_api):
        mock_api['make_canvas_request'].return_value = {"error": "Course not found"}

        get_syllabus = get_tool_function('get_syllabus')
        result = await get_syllabus("bad_course")

        assert "Error fetching syllabus" in result
        assert "Course not found" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

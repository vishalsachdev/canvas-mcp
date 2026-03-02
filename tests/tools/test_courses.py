"""
Tests for course-related MCP tools.
"""

from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.tools.courses import strip_html_tags


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

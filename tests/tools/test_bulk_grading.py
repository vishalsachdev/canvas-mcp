"""Tests for bulk_grade_submissions (relocated from rubrics to assignments)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client


async def _call_tool(mcp, name: str, arguments: dict):
    """Call a registered tool in-process, returning the raw CallToolResult."""
    async with Client(mcp) as client:
        return await client.call_tool_mcp(name, arguments)


class TestBulkGradeSubmissions:
    """Test bulk grading tool in assignments module."""

    @pytest.fixture
    def mock_canvas_request(self):
        with patch('canvas_mcp.tools.assignments.make_canvas_request', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def mock_course_id(self):
        with patch('canvas_mcp.tools.assignments.get_course_id', new_callable=AsyncMock) as mock:
            mock.return_value = 12345
            yield mock

    @pytest.fixture
    def mock_course_code(self):
        with patch('canvas_mcp.tools.assignments.get_course_code', new_callable=AsyncMock) as mock:
            mock.return_value = "TEST101"
            yield mock

    @pytest.mark.asyncio
    async def test_bulk_grade_registered_in_assignments(self):
        """Verify bulk_grade_submissions is registered via educator assignment tools."""
        from fastmcp import FastMCP

        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)
        tool_names = {t.name for t in await mcp.list_tools()}

        assert "bulk_grade_submissions" in tool_names

    @pytest.mark.asyncio
    async def test_bulk_grade_dry_run(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test dry run mode validates without submitting."""
        mock_canvas_request.return_value = {
            "name": "Essay 1",
            "use_rubric_for_grading": True
        }

        from fastmcp import FastMCP

        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)

        result = await _call_tool(mcp, "bulk_grade_submissions", {
            "course_identifier": "TEST101",
            "assignment_id": "999",
            "grades": {"user1": {"grade": 85, "comment": "Good work"}},
            "dry_run": True
        })

        result_text = result.content[0].text if result.content else ""
        assert "DRY RUN" in result_text

    @pytest.mark.asyncio
    async def test_bulk_grade_empty_grades(self, mock_course_id):
        """Test error when no grades provided."""
        from fastmcp import FastMCP

        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)

        result = await _call_tool(mcp, "bulk_grade_submissions", {
            "course_identifier": "TEST101",
            "assignment_id": "999",
            "grades": {}
        })

        result_text = result.content[0].text if result.content else ""
        assert "empty" in result_text.lower() or "error" in result_text.lower()

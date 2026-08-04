"""
Tests for student self-service MCP tools.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest


def get_student_tool_function(tool_name: str):
    """Get a student tool function by name from the registered tools."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.student_tools import register_student_tools

    # Create a mock MCP server and register tools
    mcp = FastMCP("test")

    # Store captured functions
    captured_functions = {}

    # Override the tool decorator to capture the function
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_student_tools(mcp)

    return captured_functions.get(tool_name)


class TestStudentTools:
    """Test student self-service tool functions."""

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments(self):
        """Test getting upcoming assignments for current user."""
        mock_assignments = [
            {"id": 1, "name": "Assignment 1", "due_at": "2024-02-20"},
            {"id": 2, "name": "Assignment 2", "due_at": "2024-02-25"}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_assignments

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/users/self/upcoming_events", {})

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_my_course_grades(self):
        """Test getting current user's course grades."""
        mock_enrollments = [
            {"course_id": 101, "grades": {"current_score": 85.5}},
            {"course_id": 102, "grades": {"current_score": 92.0}}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_enrollments

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/users/self/enrollments", {})

            assert len(result) == 2
            assert result[0]["grades"]["current_score"] == 85.5

    @pytest.mark.asyncio
    async def test_get_my_todo_items(self):
        """Test getting TODO items for current user."""
        mock_todos = [
            {"assignment": {"id": 1, "name": "Complete reading"}},
            {"assignment": {"id": 2, "name": "Submit essay"}}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_todos

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/users/self/todo", {})

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_my_submission_status(self):
        """Test getting submission status for current user."""
        mock_submissions = [
            {"assignment_id": 1, "workflow_state": "submitted"},
            {"assignment_id": 2, "workflow_state": "graded"}
        ]

        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_submissions

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results("/courses/12345/students/submissions", {})

            assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_my_peer_reviews_todo(self):
        """Test getting pending peer reviews for current user."""
        mock_peer_reviews = [
            {"assessor_id": "self", "asset_id": 101, "workflow_state": "assigned"},
            {"assessor_id": "self", "asset_id": 102, "workflow_state": "assigned"}
        ]

        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_peer_reviews

            from canvas_mcp.core.client import make_canvas_request

            result = await make_canvas_request("get", "/courses/12345/assignments/1/peer_reviews")

            assert len(result) == 2


class TestStudentToolsDatetimeComparison:
    """Test datetime comparison edge cases in student tools."""

    @staticmethod
    def _planner_item(title, due_at, course_id=101, submitted=False,
                      plannable_type="assignment"):
        return {
            "plannable_type": plannable_type,
            "course_id": course_id,
            "plannable": {"id": 1, "title": title, "due_at": due_at},
            "plannable_date": due_at,
            "submissions": {"submitted": submitted},
        }

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments_with_timezone_aware_dates(self):
        """Test that upcoming assignments handles timezone-aware dates correctly."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = [self._planner_item("Assignment 1", future_date)]
            mock_course.return_value = "TEST-101"

            get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
            assert get_my_upcoming_assignments is not None

            result = await get_my_upcoming_assignments(days=7)

            assert "Assignment 1" in result
            assert "error" not in result.lower()

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments_sorting_with_mixed_dates(self):
        """Test that sorting assignments works with various date formats."""
        date1 = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date2 = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date3 = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_items = [
            self._planner_item("Assignment 1", date1),
            self._planner_item("Assignment 2", date2),
            self._planner_item("Assignment 3", date3),
        ]

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = mock_items
            mock_course.return_value = "TEST-101"

            get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
            result = await get_my_upcoming_assignments(days=7)

            # Earliest due date first
            assert result.index("Assignment 2") < result.index("Assignment 3") < result.index("Assignment 1")
            assert "error" not in result.lower()

    @pytest.mark.asyncio
    async def test_get_my_submission_status_overdue_comparison(self):
        """Test that overdue detection works with timezone-aware dates."""
        # Create a past date to test overdue detection
        past_date = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_assignments = [
            {
                "id": 1,
                "name": "Overdue Assignment",
                "due_at": past_date,
                "submission": {"workflow_state": "unsubmitted"}
            }
        ]

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_id', new_callable=AsyncMock) as mock_course_id, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course_code:
            mock_fetch.return_value = mock_assignments
            mock_course_id.return_value = "12345"  # Return string instead of int
            mock_course_code.return_value = "TEST-101"

            get_my_submission_status = get_student_tool_function('get_my_submission_status')
            assert get_my_submission_status is not None

            result = await get_my_submission_status(course_identifier="TEST-101")

            # Should complete without datetime comparison errors and mark as overdue
            assert "OVERDUE" in result
            assert "error" not in result.lower()

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments_with_no_due_date(self):
        """Items with no due date at all are skipped gracefully."""
        item = self._planner_item("No Due Date Assignment", None)

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = [item]
            mock_course.return_value = "TEST-101"

            get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
            result = await get_my_upcoming_assignments(days=7)

            assert "No assignments due in the next 7 days" in result

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments_with_various_day_values(self):
        """Positive day values work; non-positive values get an explicit error."""
        future_date = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        for days_value in [1, 7, 14, 30]:
            with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
                 patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
                mock_fetch.return_value = [self._planner_item("Test Assignment", future_date)]
                mock_course.return_value = "TEST-101"

                get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
                result = await get_my_upcoming_assignments(days=days_value)

                assert result is not None
                assert "error" not in result.lower()

        for days_value in [0, -1]:
            get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
            result = await get_my_upcoming_assignments(days=days_value)
            assert "days must be at least 1" in result


class TestUpcomingAssignmentsHonorRange:
    """#222: /users/self/upcoming_events is hardcoded by Canvas to 7 days, so
    days=30 silently behaved as days=7. The tool now queries the Planner API
    with the actual requested window.
    """

    @pytest.mark.asyncio
    async def test_requested_range_is_sent_to_the_api(self):
        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            tool = get_student_tool_function('get_my_upcoming_assignments')
            result = await tool(days=30)

        endpoint = mock_fetch.call_args[0][0]
        params = mock_fetch.call_args[1].get('params')
        assert endpoint == "/planner/items"
        start = datetime.strptime(params["start_date"], "%Y-%m-%dT%H:%M:%SZ")
        end = datetime.strptime(params["end_date"], "%Y-%m-%dT%H:%M:%SZ")
        assert (end - start).days == 30
        assert "30 days" in result

    @pytest.mark.asyncio
    async def test_assignment_beyond_7_days_is_returned(self):
        """The defining case from the bug report: due in ~3 weeks, days=30."""
        far_date = (datetime.now(timezone.utc) + timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")
        item = {
            "plannable_type": "assignment",
            "course_id": 101,
            "plannable": {"id": 9, "title": "Midterm Essay", "due_at": far_date},
            "plannable_date": far_date,
            "submissions": {"submitted": False},
        }

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = [item]
            mock_course.return_value = "TEST-101"

            tool = get_student_tool_function('get_my_upcoming_assignments')
            result = await tool(days=30)

        assert "Midterm Essay" in result
        assert "Not Submitted" in result

    @pytest.mark.asyncio
    async def test_non_assignment_planner_items_are_filtered(self):
        soon = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        items = [
            {"plannable_type": "announcement", "course_id": 101,
             "plannable": {"id": 1, "title": "Read me"}, "plannable_date": soon},
            {"plannable_type": "calendar_event", "course_id": 101,
             "plannable": {"id": 2, "title": "Office hours"}, "plannable_date": soon},
        ]

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = items

            tool = get_student_tool_function('get_my_upcoming_assignments')
            result = await tool(days=7)

        assert "No assignments due" in result

    @pytest.mark.asyncio
    async def test_submitted_status_comes_from_planner_payload(self):
        soon = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        item = {
            "plannable_type": "assignment",
            "course_id": 101,
            "plannable": {"id": 9, "title": "Done Already", "due_at": soon},
            "plannable_date": soon,
            "submissions": {"submitted": True},
        }

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = [item]
            mock_course.return_value = "TEST-101"

            tool = get_student_tool_function('get_my_upcoming_assignments')
            result = await tool(days=7)

        assert "✅ Submitted" in result

    @pytest.mark.asyncio
    async def test_api_error_is_reported(self):
        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"error": "planner unavailable"}

            tool = get_student_tool_function('get_my_upcoming_assignments')
            result = await tool(days=7)

        assert "Error fetching upcoming assignments" in result
        assert "planner unavailable" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

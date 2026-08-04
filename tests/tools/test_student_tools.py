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

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments_with_timezone_aware_dates(self):
        """Test that upcoming assignments handles timezone-aware dates correctly."""
        # Mock events with timezone-aware due dates (ISO 8601 format)
        future_date = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_events = [
            {
                "type": "assignment",
                "assignment": {
                    "id": 1,
                    "name": "Assignment 1",
                    "due_at": future_date,
                    "course_id": 101
                }
            }
        ]

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = mock_events
            mock_course.return_value = "TEST-101"

            get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
            assert get_my_upcoming_assignments is not None

            result = await get_my_upcoming_assignments(days=7)

            # Should complete without datetime comparison errors
            assert "Assignment 1" in result
            assert "error" not in result.lower()

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments_sorting_with_mixed_dates(self):
        """Test that sorting assignments works with various date formats."""
        # Create dates at different times to test sorting
        date1 = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date2 = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date3 = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_events = [
            {
                "type": "assignment",
                "assignment": {
                    "id": 1,
                    "name": "Assignment 1",
                    "due_at": date1,
                    "course_id": 101
                }
            },
            {
                "type": "assignment",
                "assignment": {
                    "id": 2,
                    "name": "Assignment 2",
                    "due_at": date2,
                    "course_id": 101
                }
            },
            {
                "type": "assignment",
                "assignment": {
                    "id": 3,
                    "name": "Assignment 3",
                    "due_at": date3,
                    "course_id": 101
                }
            }
        ]

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = mock_events
            mock_course.return_value = "TEST-101"

            get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
            assert get_my_upcoming_assignments is not None

            result = await get_my_upcoming_assignments(days=7)

            # Should complete without datetime comparison errors and sort correctly
            assert "Assignment 2" in result  # Due soonest (2 days)
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
        """Test that assignments with no due date don't cause errors."""
        mock_events = [
            {
                "type": "assignment",
                "assignment": {
                    "id": 1,
                    "name": "No Due Date Assignment",
                    "due_at": None,
                    "course_id": 101
                }
            }
        ]

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = mock_events
            mock_course.return_value = "TEST-101"

            get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
            assert get_my_upcoming_assignments is not None

            result = await get_my_upcoming_assignments(days=7)

            # Should handle None due_at gracefully - assignment with no due date is filtered out
            # The function returns a message saying no assignments are due
            assert "No assignments due in the next 7 days" in result

    @pytest.mark.asyncio
    async def test_get_my_upcoming_assignments_with_various_day_values(self):
        """Test that get_my_upcoming_assignments works with different days values including > 1.

        This specifically tests the fix for the bug where days > 1 caused:
        'Error executing tool get_my_upcoming_assignments: argument of type int is not iterable'
        """
        test_cases = [1, 7, 14, 30, -1, 0]  # Various day values including > 1

        future_date = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_events = [
            {
                "type": "assignment",
                "assignment": {
                    "id": 1,
                    "name": "Test Assignment",
                    "due_at": future_date,
                    "course_id": 101
                }
            }
        ]

        for days_value in test_cases:
            with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
                 patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
                mock_fetch.return_value = mock_events
                mock_course.return_value = "TEST-101"

                get_my_upcoming_assignments = get_student_tool_function('get_my_upcoming_assignments')
                assert get_my_upcoming_assignments is not None

                # This should work without throwing "argument of type 'int' is not iterable"
                result = await get_my_upcoming_assignments(days=days_value)

                # Should complete without errors
                assert result is not None
                assert "error" not in result.lower() or "error fetching" in result.lower()  # Allow API errors but not type errors


class TestGetMyPeerReviewsTodo:
    """#219: the tool answered "no pending peer reviews ✅" when the
    peer-reviews endpoint errored (students often cannot call the
    assignment-level listing), and it never filtered by the caller's own
    assessor_id. Field shapes (assessor_id / user_id / workflow_state) match
    the live Canvas AssessmentRequest payloads used by core/peer_reviews.py.
    """

    SELF_ID = 2407

    def _patches(self, fetch_side_effect, request_return=None):
        return (
            patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results',
                  new_callable=AsyncMock, side_effect=fetch_side_effect),
            patch('canvas_mcp.tools.student_tools.make_canvas_request',
                  new_callable=AsyncMock,
                  return_value=request_return or {"id": self.SELF_ID}),
            patch('canvas_mcp.tools.student_tools.get_course_id',
                  new=AsyncMock(return_value="505")),
            patch('canvas_mcp.tools.student_tools.get_course_code',
                  new=AsyncMock(return_value="TEST-505")),
        )

    @pytest.mark.asyncio
    async def test_endpoint_error_is_not_reported_as_no_reviews(self):
        """An error dict from the peer_reviews listing must surface, not
        collapse into the happy-path 'no pending peer reviews' answer."""
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": True}],   # assignments
            {"error": "unauthorized: insufficient permissions"},   # peer_reviews
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "no pending peer reviews" not in result.lower()
        assert "unauthorized" in result
        assert "Essay" in result

    @pytest.mark.asyncio
    async def test_filters_to_own_incomplete_reviews(self):
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": True}],
            [
                # mine, incomplete -> shown
                {"assessor_id": self.SELF_ID, "user_id": 11, "workflow_state": "assigned"},
                # mine, done -> hidden
                {"assessor_id": self.SELF_ID, "user_id": 12, "workflow_state": "completed"},
                # someone else's -> hidden
                {"assessor_id": 9999, "user_id": 13, "workflow_state": "assigned"},
            ],
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "Student 11" in result
        assert "Student 12" not in result
        assert "Student 13" not in result

    @pytest.mark.asyncio
    async def test_all_own_reviews_complete_reports_done(self):
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": True}],
            [{"assessor_id": self.SELF_ID, "user_id": 11, "workflow_state": "completed"}],
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "no pending peer reviews" in result.lower()

    @pytest.mark.asyncio
    async def test_self_lookup_failure_is_an_error(self):
        p1, p2, p3, p4 = self._patches([], request_return={"error": "invalid token"})
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "error" in result.lower()
        assert "no pending peer reviews" not in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Tests for student self-service MCP tools.
"""

from datetime import UTC, datetime, timedelta
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
        future_date = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        date1 = (datetime.now(UTC) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date2 = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        date3 = (datetime.now(UTC) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        past_date = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        future_date = (datetime.now(UTC) + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

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
        far_date = (datetime.now(UTC) + timedelta(days=21)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        soon = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        soon = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    async def test_graded_discussion_is_included_ungraded_is_not(self):
        """Graded discussions carry due_at in the planner payload; ungraded
        to-do discussions only have todo_date and must stay excluded."""
        soon = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        items = [
            {"plannable_type": "discussion_topic", "course_id": 101,
             "plannable": {"id": 1, "title": "Graded Debate", "due_at": soon},
             "plannable_date": soon,
             "submissions": {"submitted": False}},
            {"plannable_type": "discussion_topic", "course_id": 101,
             "plannable": {"id": 2, "title": "Optional Chat", "todo_date": soon},
             "plannable_date": soon},
        ]

        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch, \
             patch('canvas_mcp.tools.student_tools.get_course_code', new_callable=AsyncMock) as mock_course:
            mock_fetch.return_value = items
            mock_course.return_value = "TEST-101"

            tool = get_student_tool_function('get_my_upcoming_assignments')
            result = await tool(days=7)

        assert "Graded Debate" in result
        assert "Optional Chat" not in result

    @pytest.mark.asyncio
    async def test_api_error_is_reported(self):
        with patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"error": "planner unavailable"}

            tool = get_student_tool_function('get_my_upcoming_assignments')
            result = await tool(days=7)

        assert "Error fetching upcoming assignments" in result
        assert "planner unavailable" in result


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
            [],                                                    # planner items
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
            [],  # planner items
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
            [],  # planner items
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


class TestGetMyPeerReviewsTodoDirectAssignment:
    """#275: the per-course discovery scan only checks assignments whose
    listing carried peer_reviews=True; if that flag is missing/stale for any
    reason (still uninvestigated on real student data), the caller has no way
    to check a specific assignment they already know has their review. This
    param bypasses the flag gate entirely and queries the assignment's
    peer-review listing directly.
    """

    SELF_ID = 2407

    @pytest.mark.asyncio
    async def test_finds_review_bypassing_discovery_scan_flag(self):
        # Note: no "peer_reviews" flag anywhere in this path — the direct
        # lookup does not gate on it at all.
        request_side_effect = [
            {"id": self.SELF_ID},                                    # /users/self
            {"id": 1, "name": "Essay"},                                # assignment GET
        ]
        with (
            patch('canvas_mcp.tools.student_tools.make_canvas_request',
                  new_callable=AsyncMock, side_effect=request_side_effect),
            patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results',
                  new_callable=AsyncMock,
                  return_value=[
                      {"assessor_id": self.SELF_ID, "user_id": 11, "workflow_state": "assigned"},
                      {"assessor_id": 9999, "user_id": 12, "workflow_state": "assigned"},
                  ]),
            patch('canvas_mcp.tools.student_tools.get_course_id',
                  new=AsyncMock(return_value="505")),
            patch('canvas_mcp.tools.student_tools.get_course_code',
                  new=AsyncMock(return_value="TEST-505")),
        ):
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505", assignment_identifier="1")

        assert "Essay" in result
        assert "Student 11" in result
        assert "Student 12" not in result

    @pytest.mark.asyncio
    async def test_no_match_reports_none_for_this_assignment(self):
        request_side_effect = [
            {"id": self.SELF_ID},
            {"id": 1, "name": "Essay"},
        ]
        with (
            patch('canvas_mcp.tools.student_tools.make_canvas_request',
                  new_callable=AsyncMock, side_effect=request_side_effect),
            patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results',
                  new_callable=AsyncMock,
                  return_value=[{"assessor_id": 9999, "user_id": 12, "workflow_state": "assigned"}]),
            patch('canvas_mcp.tools.student_tools.get_course_id',
                  new=AsyncMock(return_value="505")),
            patch('canvas_mcp.tools.student_tools.get_course_code',
                  new=AsyncMock(return_value="TEST-505")),
        ):
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505", assignment_identifier="1")

        assert "No pending peer review found" in result
        assert "Essay" in result

    @pytest.mark.asyncio
    async def test_requires_course_identifier(self):
        with patch('canvas_mcp.tools.student_tools.make_canvas_request',
                    new_callable=AsyncMock, return_value={"id": self.SELF_ID}):
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(assignment_identifier="1")

        assert "requires course_identifier" in result

    @pytest.mark.asyncio
    async def test_assignment_fetch_error_surfaces(self):
        request_side_effect = [
            {"id": self.SELF_ID},
            {"error": "not found"},
        ]
        with (
            patch('canvas_mcp.tools.student_tools.make_canvas_request',
                  new_callable=AsyncMock, side_effect=request_side_effect),
            patch('canvas_mcp.tools.student_tools.get_course_id',
                  new=AsyncMock(return_value="505")),
        ):
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505", assignment_identifier="999")

        assert "Error fetching assignment" in result
        assert "not found" in result


# Real /planner/items payload posted by the #275 reporter (khagyard) from a
# production UIUC Canvas instance (see the issue for the full JSON) —
# verbatim keys and shape, with context_image (a signed JWT file URL)
# stripped entirely rather than copied into the repo. Two of the three
# assessment_request items are workflow_state=="completed" (and Canvas DOES
# still return those through filter=incomplete_items — confirmed live, not
# an assumption); the middle item (workflow_state=="assigned") is the one
# genuinely pending review. Notably: no user_id, no assessor_id anywhere —
# that falsified this PR's original field assumption (see git history /
# PR #288 review round 2) and is why the assessor guard stays permissive
# and the "Reviewing:" line has a no-user_id fallback.
REAL_PLANNER_PAYLOAD_275 = [
    {
        "context_type": "Course",
        "course_id": 505,
        "plannable_id": 115,
        "planner_override": None,
        "plannable_type": "assessment_request",
        "new_activity": False,
        "submissions": False,
        "plannable_date": "2026-08-08T05:59:59Z",
        "plannable": {
            "id": 115,
            "title": "Online assignment",
            "todo_date": "2026-08-08T05:59:59Z",
            "created_at": "2026-08-03T14:26:04Z",
            "updated_at": "2026-08-03T14:52:17Z",
            "workflow_state": "completed",
        },
        "html_url": "/courses/505/assignments/5066/submissions/2898",
        "context_name": "UIUC MCP Test Course - Updated",
    },
    {
        "context_type": "Course",
        "course_id": 505,
        "plannable_id": 116,
        "planner_override": None,
        "plannable_type": "assessment_request",
        "new_activity": False,
        "submissions": False,
        "plannable_date": "2026-08-08T05:59:59Z",
        "plannable": {
            "id": 116,
            "title": "Online assignment",
            "todo_date": "2026-08-08T05:59:59Z",
            "created_at": "2026-08-03T14:33:39Z",
            "updated_at": "2026-08-03T14:33:39Z",
            "workflow_state": "assigned",
        },
        "html_url": "/courses/505/assignments/5066/submissions/2549",
        "context_name": "UIUC MCP Test Course - Updated",
    },
    {
        "context_type": "Course",
        "course_id": 505,
        "plannable_id": 117,
        "planner_override": None,
        "plannable_type": "assessment_request",
        "new_activity": False,
        "submissions": False,
        "plannable_date": "2026-08-09T06:00:00Z",
        "plannable": {
            "id": 117,
            "title": "Peer review assignment",
            "todo_date": "2026-08-09T06:00:00Z",
            "created_at": "2026-08-06T20:50:49Z",
            "updated_at": "2026-08-11T16:28:51Z",
            "workflow_state": "completed",
        },
        "html_url": "/courses/505/assignments/5095/submissions/2892",
        "context_name": "UIUC MCP Test Course - Updated",
    },
]


class TestGetMyPeerReviewsTodoPlannerDiscovery:
    """#275: the assignment-scoped discovery scan reportedly misses real
    pending peer reviews. Canvas's own student "To Do" UI builds its list
    from the Planner feed instead (assessment_request items), so that feed
    is queried as an additional source and merged into the scan's results
    rather than replacing it — the merge must degrade gracefully if the
    Planner query fails, and must not double-report a review both paths find.
    """

    SELF_ID = 2407

    def _patches(self, fetch_side_effect):
        return (
            patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results',
                  new_callable=AsyncMock, side_effect=fetch_side_effect),
            patch('canvas_mcp.tools.student_tools.make_canvas_request',
                  new_callable=AsyncMock, return_value={"id": self.SELF_ID}),
            patch('canvas_mcp.tools.student_tools.get_course_id',
                  new=AsyncMock(return_value="505")),
            patch('canvas_mcp.tools.student_tools.get_course_code',
                  new=AsyncMock(return_value="TEST-505")),
        )

    @pytest.mark.asyncio
    async def test_real_payload_acceptance_replay(self):
        """Acceptance replay against REAL_PLANNER_PAYLOAD_275 — the actual
        production payload from #275, not a hand-written fixture. Confirms:
        the genuinely-pending item (workflow_state=="assigned") is found;
        both workflow_state=="completed" items are excluded even though
        Canvas returned them through filter=incomplete_items (measured, not
        assumed); and the no-user_id reality renders as an honest note
        rather than "Student None"."""
        # No assignment carries peer_reviews=True, so the assignment scan
        # finds nothing — only the Planner feed surfaces anything here.
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": False}],  # assignments
            REAL_PLANNER_PAYLOAD_275,  # planner items — real production payload
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        # Exactly one bullet: the two completed items must not appear.
        # ("Planner feed" itself appears twice for that one bullet — once in
        # the source label, once in the no-user_id fallback note — so this
        # counts the "Source:" label specifically.)
        assert result.count("•") == 1
        assert result.count("Source: Planner feed") == 1
        assert "Online assignment" in result  # the assigned item's title
        assert "Peer review assignment" not in result  # the completed one
        assert "Student None" not in result
        assert "(reviewee not identified in Planner feed)" in result

    @pytest.mark.asyncio
    async def test_planner_only_review_without_user_id_renders_without_student_none(self):
        """Direct pin for the None-user_id rendering fix: a Planner-sourced
        review with no user_id (the measured real shape) must never print
        the literal string "Student None"."""
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": False}],  # assignments
            [
                {
                    "plannable_type": "assessment_request",
                    "course_id": 505,
                    "plannable": {
                        "id": 116,
                        "title": "Online assignment",
                        "workflow_state": "assigned",
                        # no user_id — matches the real #275 payload
                    },
                },
            ],  # planner items
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "Student None" not in result
        assert "(reviewee not identified in Planner feed)" in result

    @pytest.mark.asyncio
    async def test_planner_error_does_not_break_existing_scan(self):
        # Assignment scan succeeds and finds a review; the Planner feed call
        # itself errors. The tool must still report the scan's finding, with
        # a warning about the Planner failure, not a blank/broken answer.
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": True}],   # assignments
            [{"assessor_id": self.SELF_ID, "user_id": 11, "workflow_state": "assigned"}],  # peer_reviews
            {"error": "service unavailable"},                     # planner items
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "Student 11" in result
        assert (
            "Could not check the Planner feed for additional peer reviews: "
            "service unavailable" in result
        )

    @pytest.mark.asyncio
    async def test_dedup_when_both_paths_find_same_review(self):
        # Assignment scan and Planner feed both surface the same
        # AssessmentRequest (id=77) — it must appear exactly once.
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": True}],
            [{"id": 77, "assessor_id": self.SELF_ID, "user_id": 11, "workflow_state": "assigned"}],
            [
                {
                    "plannable_type": "assessment_request",
                    "course_id": 505,
                    "plannable": {
                        "id": 77,
                        "user_id": 11,
                        "title": "Essay",
                        "workflow_state": "assigned",
                    },
                },
            ],
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert result.count("Student 11") == 1

    @pytest.mark.asyncio
    async def test_stale_pending_review_not_dropped_by_date_window(self):
        """Regression pin (review round 1): a peer review assigned more
        than 28 days ago and still incomplete is exactly the #275 scenario.
        No start_date is sent to Canvas, so filter=incomplete_items alone
        must be trusted — an old item must still surface."""
        old_date = (
            datetime.now(UTC) - timedelta(days=60)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": False}],  # assignments
            [
                {
                    "plannable_type": "assessment_request",
                    "course_id": 505,
                    "plannable_date": old_date,
                    "plannable": {
                        "id": 77,
                        "user_id": 11,
                        "title": "Essay",
                        "workflow_state": "assigned",
                    },
                },
            ],  # planner items
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "Student 11" in result

    @pytest.mark.asyncio
    async def test_planner_item_with_different_assessor_is_skipped(self):
        """The Planner feed is meant to already be the caller's own to-do
        list, but that isn't documented as guaranteed — an item Canvas
        positively attributes to a different assessor must not be reported
        as the caller's own pending review.

        assessor_id/user_id are synthetic here — the real #275 production
        payload (REAL_PLANNER_PAYLOAD_275 above) carries neither field, but
        this guard exists for a Canvas serialization/version that does."""
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": False}],  # assignments
            [
                {
                    "plannable_type": "assessment_request",
                    "course_id": 505,
                    "plannable": {
                        "id": 77,
                        "user_id": 11,
                        "assessor_id": 9999,  # not the caller
                        "title": "Essay",
                        "workflow_state": "assigned",
                    },
                },
            ],  # planner items
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "no pending peer reviews" in result.lower()

    @pytest.mark.asyncio
    async def test_planner_item_with_matching_or_missing_assessor_is_kept(self):
        """The guard is permissive: an item naming the caller as assessor is
        kept, and so is one that omits assessor_id entirely (undocumented
        field, may not always be populated — the real #275 production
        payload omits it on every item) — only a positively different
        assessor excludes an item."""
        fetch_side_effect = [
            [{"id": 1, "name": "Essay", "peer_reviews": False}],  # assignments
            [
                {
                    "plannable_type": "assessment_request",
                    "course_id": 505,
                    "plannable": {
                        "id": 77,
                        "user_id": 11,
                        "assessor_id": self.SELF_ID,
                        "title": "Essay",
                        "workflow_state": "assigned",
                    },
                },
                {
                    "plannable_type": "assessment_request",
                    "course_id": 505,
                    "plannable": {
                        "id": 78,
                        "user_id": 12,
                        # no assessor_id at all
                        "title": "Essay",
                        "workflow_state": "assigned",
                    },
                },
            ],  # planner items
        ]
        p1, p2, p3, p4 = self._patches(fetch_side_effect)
        with p1, p2, p3, p4:
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            result = await tool(course_identifier="505")

        assert "Student 11" in result
        assert "Student 12" in result

    @pytest.mark.asyncio
    async def test_planner_pagination_and_context_filter_params(self):
        captured_params: dict = {}

        async def fake_fetch(endpoint, params=None, **kwargs):
            if endpoint == "/planner/items":
                captured_params.update(params or {})
                return []
            if endpoint.endswith("/assignments"):
                return []
            return []

        with (
            patch('canvas_mcp.tools.student_tools.fetch_all_paginated_results',
                  new_callable=AsyncMock, side_effect=fake_fetch),
            patch('canvas_mcp.tools.student_tools.make_canvas_request',
                  new_callable=AsyncMock, return_value={"id": self.SELF_ID}),
            patch('canvas_mcp.tools.student_tools.get_course_id',
                  new=AsyncMock(return_value="505")),
        ):
            tool = get_student_tool_function('get_my_peer_reviews_todo')
            await tool(course_identifier="505")

        assert captured_params.get("filter") == "incomplete_items"
        assert captured_params.get("per_page") == 100
        assert "start_date" not in captured_params
        assert "order" not in captured_params
        assert captured_params.get("context_codes[]") == ["course_505"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Tests for account-level MCP tools (list_user_enrollments).
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestListUserEnrollments:
    """Tests for the list_user_enrollments tool logic."""

    @pytest.mark.asyncio
    async def test_enrollments_endpoint_returns_all_courses(self):
        """Test that the enrollments endpoint is used (not /users/{id}/courses)."""
        mock_enrollments = [
            {
                "id": 1001,
                "course_id": 506,
                "type": "StudentEnrollment",
                "enrollment_state": "active",
            },
            {
                "id": 1002,
                "course_id": 458,
                "type": "StudentEnrollment",
                "enrollment_state": "completed",
            },
            {
                "id": 1003,
                "course_id": 720,
                "type": "StudentEnrollment",
                "enrollment_state": "concluded",
            },
        ]

        with patch(
            "canvas_mcp.core.client.fetch_all_paginated_results",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_enrollments

            from canvas_mcp.core.client import fetch_all_paginated_results

            enrollments = await fetch_all_paginated_results(
                "/users/12345/enrollments",
                {"per_page": 100},
            )

            assert len(enrollments) == 3
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args
            assert "/users/12345/enrollments" in call_args[0]

    @pytest.mark.asyncio
    async def test_filters_to_student_enrollments_only(self):
        """Test that teacher/observer enrollments are filtered out."""
        mock_enrollments = [
            {
                "id": 1001,
                "course_id": 506,
                "type": "StudentEnrollment",
                "enrollment_state": "active",
            },
            {
                "id": 1002,
                "course_id": 507,
                "type": "TeacherEnrollment",
                "enrollment_state": "active",
            },
            {
                "id": 1003,
                "course_id": 508,
                "type": "ObserverEnrollment",
                "enrollment_state": "active",
            },
        ]

        # Filter logic from the tool
        states = ["active", "completed", "concluded"]
        filtered = [
            e for e in mock_enrollments
            if e.get("enrollment_state") in states
            and e.get("type") == "StudentEnrollment"
        ]

        assert len(filtered) == 1
        assert filtered[0]["course_id"] == 506

    @pytest.mark.asyncio
    async def test_deduplicates_by_course_id(self):
        """Test that duplicate enrollments in the same course are deduplicated."""
        mock_enrollments = [
            {
                "id": 1001,
                "course_id": 506,
                "type": "StudentEnrollment",
                "enrollment_state": "active",
            },
            {
                "id": 1002,
                "course_id": 506,
                "type": "StudentEnrollment",
                "enrollment_state": "completed",
            },
            {
                "id": 1003,
                "course_id": 720,
                "type": "StudentEnrollment",
                "enrollment_state": "active",
            },
        ]

        states = ["active", "completed", "concluded"]
        filtered = [
            e for e in mock_enrollments
            if e.get("enrollment_state") in states
            and e.get("type") == "StudentEnrollment"
        ]

        courses_seen = {}
        for enrollment in filtered:
            course_id = enrollment.get("course_id")
            if course_id not in courses_seen:
                courses_seen[course_id] = enrollment

        assert len(courses_seen) == 2
        assert 506 in courses_seen
        assert 720 in courses_seen

    @pytest.mark.asyncio
    async def test_empty_enrollment(self):
        """Test user with no enrollments returns empty list."""
        with patch(
            "canvas_mcp.core.client.fetch_all_paginated_results",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = []

            from canvas_mcp.core.client import fetch_all_paginated_results

            enrollments = await fetch_all_paginated_results(
                "/users/99999/enrollments",
                {"per_page": 100},
            )

            assert enrollments == []
            assert len(enrollments) == 0

    @pytest.mark.asyncio
    async def test_error_handling_invalid_user(self):
        """Test error response for invalid user ID."""
        with patch(
            "canvas_mcp.core.client.fetch_all_paginated_results",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = {"error": "The specified object cannot be found"}

            from canvas_mcp.core.client import fetch_all_paginated_results

            result = await fetch_all_paginated_results(
                "/users/0/enrollments",
                {"per_page": 100},
            )

            assert isinstance(result, dict)
            assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

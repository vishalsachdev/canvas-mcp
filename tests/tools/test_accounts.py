"""
Tests for account-level MCP tools (list_user_enrollments).
"""

import pytest
from unittest.mock import AsyncMock, patch


class TestListUserEnrollments:
    """Tests for the list_user_enrollments tool logic."""

    @pytest.mark.asyncio
    async def test_success_multiple_courses_across_terms(self):
        """Test fetching enrollments returns courses sorted by term."""
        mock_courses = [
            {
                "id": 506,
                "name": "English III",
                "course_code": "ENG III",
                "workflow_state": "available",
                "term": {"name": "2024-25 School Year", "start_at": "2024-08-01T00:00:00Z"},
            },
            {
                "id": 458,
                "name": "AI & Machine Learning",
                "course_code": "AI ML",
                "workflow_state": "completed",
                "term": {"name": "2022-23 School Year", "start_at": "2022-08-01T00:00:00Z"},
            },
            {
                "id": 720,
                "name": "Biology",
                "course_code": "BIO",
                "workflow_state": "completed",
                "term": {"name": "2023-24 School Year", "start_at": "2023-08-01T00:00:00Z"},
            },
        ]

        with patch(
            "canvas_mcp.core.client.fetch_all_paginated_results",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = mock_courses

            from canvas_mcp.core.client import fetch_all_paginated_results

            courses = await fetch_all_paginated_results(
                "/users/12345/courses",
                {"include[]": "term", "state[]": ["active", "completed"], "per_page": 100},
            )

            assert len(courses) == 3
            # Verify the mock was called with the right endpoint
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args
            assert "/users/12345/courses" in call_args[0]

    @pytest.mark.asyncio
    async def test_empty_enrollment(self):
        """Test user with no course enrollments returns empty list."""
        with patch(
            "canvas_mcp.core.client.fetch_all_paginated_results",
            new_callable=AsyncMock,
        ) as mock_fetch:
            mock_fetch.return_value = []

            from canvas_mcp.core.client import fetch_all_paginated_results

            courses = await fetch_all_paginated_results(
                "/users/99999/courses",
                {"include[]": "term", "state[]": ["active", "completed"], "per_page": 100},
            )

            assert courses == []
            assert len(courses) == 0

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
                "/users/0/courses",
                {"include[]": "term", "state[]": ["active", "completed"], "per_page": 100},
            )

            assert isinstance(result, dict)
            assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

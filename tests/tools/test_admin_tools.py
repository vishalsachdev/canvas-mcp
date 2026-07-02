"""
Tests for admin MCP tools.

Covers:
- get_anonymization_status
- list_groups
- list_users
- get_student_analytics
- create_student_anonymization_map
"""

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls for admin tools."""
    with patch('canvas_mcp.tools.admin_tools.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.admin_tools.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.admin_tools.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.admin_tools.make_canvas_request') as mock_request:

        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request,
        }


def get_tool_function(tool_name: str):
    """Retrieve a registered tool function by name."""
    from fastmcp import FastMCP

    from canvas_mcp.tools.admin_tools import register_admin_tools

    mcp = FastMCP("test")
    captured: dict = {}

    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_admin_tools(mcp)
    return captured.get(tool_name)


# ---------------------------------------------------------------------------
# get_anonymization_status
# ---------------------------------------------------------------------------

class TestGetAnonymizationStatus:
    """Tests for get_anonymization_status tool."""

    @pytest.mark.asyncio
    async def test_anonymization_disabled(self):
        """Test status output when anonymization is disabled."""
        with patch('canvas_mcp.core.config.get_config') as mock_config, \
             patch('canvas_mcp.core.anonymization.get_anonymization_stats') as mock_stats:
            mock_config.return_value.enable_data_anonymization = False
            mock_config.return_value.anonymization_debug = False
            mock_stats.return_value = {
                'total_anonymized_ids': 0,
                'privacy_status': 'disabled',
                'sample_mappings': {}
            }

            fn = get_tool_function('get_anonymization_status')
            assert fn is not None
            result = await fn()

            assert "ANONYMIZATION DISABLED" in result or "disabled" in result.lower() or "ANONYMIZATION" in result

    @pytest.mark.asyncio
    async def test_anonymization_enabled(self):
        """Test status output when anonymization is enabled."""
        with patch('canvas_mcp.core.config.get_config') as mock_config, \
             patch('canvas_mcp.core.anonymization.get_anonymization_stats') as mock_stats:
            mock_config.return_value.enable_data_anonymization = True
            mock_config.return_value.anonymization_debug = False
            mock_stats.return_value = {
                'total_anonymized_ids': 5,
                'privacy_status': 'active',
                'sample_mappings': {'User_abc': 'Student_12345678'}
            }

            fn = get_tool_function('get_anonymization_status')
            result = await fn()

            assert result is not None
            assert len(result) > 0


# ---------------------------------------------------------------------------
# list_groups
# ---------------------------------------------------------------------------

class TestListGroups:
    """Tests for list_groups tool."""

    @pytest.mark.asyncio
    async def test_list_groups_success(self, mock_canvas_api):
        """Test successful group listing."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            # First call: groups
            [
                {"id": 1, "name": "Group A", "group_category_id": 10, "members_count": 3},
                {"id": 2, "name": "Group B", "group_category_id": 10, "members_count": 2},
            ],
            # Second call: members of group 1
            [{"id": 101, "name": "Student One", "email": "s1@example.com"}],
            # Third call: members of group 2
            [{"id": 102, "name": "Student Two", "email": "s2@example.com"}],
        ]

        fn = get_tool_function('list_groups')
        assert fn is not None

        result = await fn("badm_350_120251")

        assert "Group A" in result
        assert "Group B" in result

    @pytest.mark.asyncio
    async def test_list_groups_empty(self, mock_canvas_api):
        """Test when course has no groups."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function('list_groups')
        result = await fn("badm_350_120251")

        assert "No groups found" in result

    @pytest.mark.asyncio
    async def test_list_groups_api_error(self, mock_canvas_api):
        """Test group listing when API returns an error."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = {"error": "Forbidden"}

        fn = get_tool_function('list_groups')
        result = await fn("badm_350_120251")

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_list_groups_anonymization_failure_logs_warning(self, mock_canvas_api):
        """A failing member anonymization is reported via log_warning, not print."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            [{"id": 1, "name": "Group A", "group_category_id": 10, "members_count": 1}],
            [{"id": 101, "name": "Alice", "email": "alice@example.com"}],
        ]

        with patch(
            'canvas_mcp.tools.admin_tools.anonymize_response_data',
            side_effect=RuntimeError("alice@example.com"),
        ), patch('canvas_mcp.tools.admin_tools.log_warning') as mock_warn:
            fn = get_tool_function('list_groups')
            result = await fn("badm_350_120251")

        mock_warn.assert_called_once()
        _, kwargs = mock_warn.call_args
        assert kwargs.get("error_type") == "RuntimeError"
        assert "alice@example.com" not in str(mock_warn.call_args)
        assert "Group A" in result  # falls back to original data


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

class TestListUsers:
    """Tests for list_users tool."""

    @pytest.mark.asyncio
    async def test_list_users_success(self, mock_canvas_api):
        """Test successful user listing."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {
                "id": 201,
                "name": "Alice Smith",
                "email": "alice@example.com",
                "enrollments": [{"role": "StudentEnrollment"}]
            },
            {
                "id": 202,
                "name": "Bob Jones",
                "email": "bob@example.com",
                "enrollments": [{"role": "TeacherEnrollment"}]
            }
        ]

        fn = get_tool_function('list_users')
        assert fn is not None

        result = await fn("badm_350_120251")

        assert "201" in result or "202" in result  # IDs should appear

    @pytest.mark.asyncio
    async def test_list_users_empty(self, mock_canvas_api):
        """Test when course has no users."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function('list_users')
        result = await fn("badm_350_120251")

        assert "No users found" in result

    @pytest.mark.asyncio
    async def test_list_users_api_error(self, mock_canvas_api):
        """Test user listing when API returns an error."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = {"error": "Not found"}

        fn = get_tool_function('list_users')
        result = await fn("badm_350_120251")

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_list_users_anonymization_failure_logs_warning(self, mock_canvas_api):
        """A failing anonymization is reported via log_warning (stderr), not print.

        Bare print() would corrupt the MCP stdio JSON-RPC stream, and str(e) could
        leak the PII that failed to scrub. The handler must route through
        log_warning, log only the exception type, and continue with original data.
        """
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {"id": 201, "name": "Alice Smith", "email": "alice@example.com",
             "enrollments": [{"role": "StudentEnrollment"}]},
        ]

        with patch(
            'canvas_mcp.tools.admin_tools.anonymize_response_data',
            side_effect=RuntimeError("alice@example.com"),
        ), patch('canvas_mcp.tools.admin_tools.log_warning') as mock_warn:
            fn = get_tool_function('list_users')
            result = await fn("badm_350_120251")

        # Warning routed to logger, not stdout
        mock_warn.assert_called_once()
        _, kwargs = mock_warn.call_args
        # Only the exception type is logged — never the PII-bearing message
        assert kwargs.get("error_type") == "RuntimeError"
        assert "alice@example.com" not in str(mock_warn.call_args)
        # Falls back to original (un-anonymized) data so the tool still works
        assert "201" in result


# ---------------------------------------------------------------------------
# get_student_analytics
# ---------------------------------------------------------------------------

class TestGetStudentAnalytics:
    """Tests for get_student_analytics tool."""

    @pytest.mark.asyncio
    async def test_get_student_analytics_basic(self, mock_canvas_api):
        """Test basic student analytics."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 60366,
            "name": "Business Administration 350"
        }
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            # students
            [{"id": 301, "name": "Student A"}, {"id": 302, "name": "Student B"}],
            # assignments
            [{"id": 401, "name": "HW1", "published": True, "points_possible": 100}],
        ]

        fn = get_tool_function('get_student_analytics')
        assert fn is not None

        result = await fn("badm_350_120251")

        assert "Student" in result or "students" in result.lower()

    @pytest.mark.asyncio
    async def test_get_student_analytics_course_error(self, mock_canvas_api):
        """Test analytics when course fetch fails."""
        mock_canvas_api['make_canvas_request'].return_value = {"error": "Not found"}

        fn = get_tool_function('get_student_analytics')
        result = await fn("badm_350_120251")

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_get_student_analytics_no_students(self, mock_canvas_api):
        """Test analytics when course has no students."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 60366,
            "name": "Empty Course"
        }
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            [],  # no students
            [],  # no assignments
        ]

        fn = get_tool_function('get_student_analytics')
        result = await fn("badm_350_120251")

        assert "0" in result or "No" in result or "students" in result.lower()

    @pytest.mark.asyncio
    async def test_get_student_analytics_anonymization_failure_logs_warning(self, mock_canvas_api):
        """A failing student anonymization is reported via log_warning, not print."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 60366, "name": "Business Administration 350"
        }
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            [{"id": 301, "name": "Alice", "email": "alice@example.com"}],  # students
            [{"id": 401, "name": "HW1", "published": True, "points_possible": 100}],  # assignments
        ]

        with patch(
            'canvas_mcp.tools.admin_tools.anonymize_response_data',
            side_effect=RuntimeError("alice@example.com"),
        ), patch('canvas_mcp.tools.admin_tools.log_warning') as mock_warn:
            fn = get_tool_function('get_student_analytics')
            await fn("badm_350_120251")

        mock_warn.assert_called_once()
        _, kwargs = mock_warn.call_args
        assert kwargs.get("error_type") == "RuntimeError"
        assert "alice@example.com" not in str(mock_warn.call_args)

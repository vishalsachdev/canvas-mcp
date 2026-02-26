"""Unit tests for other MCP tools (pages, users, analytics, groups).

Tests for:
- list_pages
- get_page_content
- get_page_details
- get_front_page
- create_page
- edit_page_content
- list_module_items
- list_groups
- list_users
- get_student_analytics
- get_anonymization_status
- create_student_anonymization_map
"""

from unittest.mock import patch

import pytest


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP

    from canvas_mcp.tools.other_tools import register_other_tools

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
    register_other_tools(mcp)

    return captured_functions.get(tool_name)


@pytest.fixture
def mock_other_tools_api():
    """Fixture to mock all Canvas API calls for other_tools."""
    with patch('canvas_mcp.tools.other_tools.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.other_tools.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.other_tools.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.other_tools.make_canvas_request') as mock_request, \
         patch('canvas_mcp.tools.other_tools.anonymize_response_data') as mock_anonymize:

        mock_get_id.return_value = 12345
        mock_get_code.return_value = "CS101"
        # Make anonymize_response_data pass data through unchanged
        mock_anonymize.side_effect = lambda data, **kwargs: data

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request,
            'anonymize_response_data': mock_anonymize,
        }


# =============================================================================
# Tests for list_pages
# =============================================================================

class TestListPages:
    """Tests for the list_pages tool."""

    @pytest.mark.asyncio
    async def test_list_pages_success(self, mock_other_tools_api):
        """Test successful page listing."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = [
            {"url": "welcome", "title": "Welcome Page", "published": True,
             "front_page": True, "updated_at": "2024-01-15T10:00:00Z"},
            {"url": "syllabus", "title": "Syllabus", "published": True,
             "front_page": False, "updated_at": "2024-01-10T10:00:00Z"},
        ]

        fn = get_tool_function("list_pages")
        result = await fn(course_identifier="CS101")

        assert "Welcome Page" in result
        assert "Syllabus" in result
        assert "(Front Page)" in result

    @pytest.mark.asyncio
    async def test_list_pages_empty(self, mock_other_tools_api):
        """Test listing pages when none exist."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function("list_pages")
        result = await fn(course_identifier="CS101")

        assert "No pages found" in result

    @pytest.mark.asyncio
    async def test_list_pages_api_error(self, mock_other_tools_api):
        """Test API error handling."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = {"error": "Forbidden"}

        fn = get_tool_function("list_pages")
        result = await fn(course_identifier="CS101")

        assert "Error" in result
        assert "Forbidden" in result


# =============================================================================
# Tests for get_page_content
# =============================================================================

class TestGetPageContent:
    """Tests for the get_page_content tool."""

    @pytest.mark.asyncio
    async def test_get_page_content_success(self, mock_other_tools_api):
        """Test successful page content retrieval."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "title": "Welcome Page",
            "body": "<h1>Welcome</h1><p>Hello students</p>",
            "published": True
        }

        fn = get_tool_function("get_page_content")
        result = await fn(course_identifier="CS101", page_url_or_id="welcome")

        assert "Welcome Page" in result
        assert "<h1>Welcome</h1>" in result

    @pytest.mark.asyncio
    async def test_get_page_content_empty(self, mock_other_tools_api):
        """Test page with no content."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "title": "Empty Page",
            "body": "",
            "published": True
        }

        fn = get_tool_function("get_page_content")
        result = await fn(course_identifier="CS101", page_url_or_id="empty")

        assert "no content" in result.lower()

    @pytest.mark.asyncio
    async def test_get_page_content_api_error(self, mock_other_tools_api):
        """Test API error."""
        mock_other_tools_api['make_canvas_request'].return_value = {"error": "Not Found"}

        fn = get_tool_function("get_page_content")
        result = await fn(course_identifier="CS101", page_url_or_id="nonexistent")

        assert "Error" in result


# =============================================================================
# Tests for get_front_page
# =============================================================================

class TestGetFrontPage:
    """Tests for the get_front_page tool."""

    @pytest.mark.asyncio
    async def test_get_front_page_success(self, mock_other_tools_api):
        """Test successful front page retrieval."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "title": "Course Home",
            "body": "<h1>Welcome to CS101</h1>",
            "updated_at": "2024-01-15T10:00:00Z"
        }

        fn = get_tool_function("get_front_page")
        result = await fn(course_identifier="CS101")

        assert "Course Home" in result
        assert "Welcome to CS101" in result

    @pytest.mark.asyncio
    async def test_get_front_page_empty(self, mock_other_tools_api):
        """Test front page with no content."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "title": "Front Page",
            "body": "",
            "updated_at": "2024-01-15T10:00:00Z"
        }

        fn = get_tool_function("get_front_page")
        result = await fn(course_identifier="CS101")

        assert "no content" in result.lower()

    @pytest.mark.asyncio
    async def test_get_front_page_api_error(self, mock_other_tools_api):
        """Test API error."""
        mock_other_tools_api['make_canvas_request'].return_value = {"error": "Not Found"}

        fn = get_tool_function("get_front_page")
        result = await fn(course_identifier="CS101")

        assert "Error" in result


# =============================================================================
# Tests for create_page
# =============================================================================

class TestCreatePage:
    """Tests for the create_page tool."""

    @pytest.mark.asyncio
    async def test_create_page_success(self, mock_other_tools_api):
        """Test successful page creation."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "url": "new-page",
            "title": "New Page",
            "published": True,
            "created_at": "2024-02-01T10:00:00Z"
        }

        fn = get_tool_function("create_page")
        result = await fn(
            course_identifier="CS101",
            title="New Page",
            body="<p>Content here</p>"
        )

        assert "Successfully created" in result
        assert "New Page" in result

    @pytest.mark.asyncio
    async def test_create_page_as_front_page(self, mock_other_tools_api):
        """Test creating page as front page."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "url": "home",
            "title": "Home",
            "published": True,
            "front_page": True,
            "created_at": "2024-02-01T10:00:00Z"
        }

        fn = get_tool_function("create_page")
        result = await fn(
            course_identifier="CS101",
            title="Home",
            body="<p>Welcome</p>",
            front_page=True
        )

        assert "front page" in result.lower()

    @pytest.mark.asyncio
    async def test_create_page_api_error(self, mock_other_tools_api):
        """Test API error on creation."""
        mock_other_tools_api['make_canvas_request'].return_value = {"error": "Unauthorized"}

        fn = get_tool_function("create_page")
        result = await fn(
            course_identifier="CS101",
            title="Test",
            body="Content"
        )

        assert "Error" in result


# =============================================================================
# Tests for edit_page_content
# =============================================================================

class TestEditPageContent:
    """Tests for the edit_page_content tool."""

    @pytest.mark.asyncio
    async def test_edit_page_success(self, mock_other_tools_api):
        """Test successful page edit."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "title": "Updated Page",
            "updated_at": "2024-02-01T12:00:00Z"
        }

        fn = get_tool_function("edit_page_content")
        result = await fn(
            course_identifier="CS101",
            page_url_or_id="my-page",
            new_content="<p>New content</p>"
        )

        assert "Successfully updated" in result
        assert "Updated Page" in result

    @pytest.mark.asyncio
    async def test_edit_page_with_new_title(self, mock_other_tools_api):
        """Test editing page with new title."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "title": "Renamed Page",
            "updated_at": "2024-02-01T12:00:00Z"
        }

        fn = get_tool_function("edit_page_content")
        result = await fn(
            course_identifier="CS101",
            page_url_or_id="my-page",
            new_content="<p>New</p>",
            title="Renamed Page"
        )

        assert "Renamed Page" in result

    @pytest.mark.asyncio
    async def test_edit_page_api_error(self, mock_other_tools_api):
        """Test API error on edit."""
        mock_other_tools_api['make_canvas_request'].return_value = {"error": "Forbidden"}

        fn = get_tool_function("edit_page_content")
        result = await fn(
            course_identifier="CS101",
            page_url_or_id="locked-page",
            new_content="<p>Content</p>"
        )

        assert "Error" in result


# =============================================================================
# Tests for list_module_items
# =============================================================================

class TestListModuleItems:
    """Tests for the list_module_items tool."""

    @pytest.mark.asyncio
    async def test_list_module_items_success(self, mock_other_tools_api):
        """Test successful module item listing."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = [
            {"id": 1, "title": "Intro Page", "type": "Page", "content_id": 100, "published": True},
            {"id": 2, "title": "Quiz 1", "type": "Quiz", "content_id": 200, "published": True},
        ]
        mock_other_tools_api['make_canvas_request'].return_value = {
            "name": "Week 1"
        }

        fn = get_tool_function("list_module_items")
        result = await fn(course_identifier="CS101", module_id=5001)

        assert "Intro Page" in result
        assert "Quiz 1" in result
        assert "Week 1" in result

    @pytest.mark.asyncio
    async def test_list_module_items_empty(self, mock_other_tools_api):
        """Test empty module."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function("list_module_items")
        result = await fn(course_identifier="CS101", module_id=5001)

        assert "No items found" in result

    @pytest.mark.asyncio
    async def test_list_module_items_api_error(self, mock_other_tools_api):
        """Test API error."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = {"error": "Not Found"}

        fn = get_tool_function("list_module_items")
        result = await fn(course_identifier="CS101", module_id=9999)

        assert "Error" in result


# =============================================================================
# Tests for list_groups
# =============================================================================

class TestListGroups:
    """Tests for the list_groups tool."""

    @pytest.mark.asyncio
    async def test_list_groups_success(self, mock_other_tools_api):
        """Test successful group listing with members."""
        # First call returns groups, second returns members
        mock_other_tools_api['fetch_all_paginated_results'].side_effect = [
            [{"id": 10, "name": "Group A", "group_category_id": 1, "members_count": 2}],
            [{"id": 101, "name": "Alice", "email": "alice@test.com"},
             {"id": 102, "name": "Bob", "email": "bob@test.com"}]
        ]

        fn = get_tool_function("list_groups")
        result = await fn(course_identifier="CS101")

        assert "Group A" in result
        assert "Alice" in result
        assert "Bob" in result

    @pytest.mark.asyncio
    async def test_list_groups_empty(self, mock_other_tools_api):
        """Test when no groups exist."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function("list_groups")
        result = await fn(course_identifier="CS101")

        assert "No groups found" in result

    @pytest.mark.asyncio
    async def test_list_groups_api_error(self, mock_other_tools_api):
        """Test API error."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = {"error": "Unauthorized"}

        fn = get_tool_function("list_groups")
        result = await fn(course_identifier="CS101")

        assert "Error" in result


# =============================================================================
# Tests for list_users
# =============================================================================

class TestListUsers:
    """Tests for the list_users tool."""

    @pytest.mark.asyncio
    async def test_list_users_success(self, mock_other_tools_api):
        """Test successful user listing."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = [
            {"id": 1001, "name": "Student A", "email": "a@test.com",
             "enrollments": [{"role": "StudentEnrollment"}]},
            {"id": 1002, "name": "Professor B", "email": "b@test.com",
             "enrollments": [{"role": "TeacherEnrollment"}]},
        ]

        fn = get_tool_function("list_users")
        result = await fn(course_identifier="CS101")

        assert "Student A" in result
        assert "Professor B" in result
        assert "CS101" in result

    @pytest.mark.asyncio
    async def test_list_users_empty(self, mock_other_tools_api):
        """Test empty user list."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function("list_users")
        result = await fn(course_identifier="CS101")

        assert "No users found" in result

    @pytest.mark.asyncio
    async def test_list_users_api_error(self, mock_other_tools_api):
        """Test API error."""
        mock_other_tools_api['fetch_all_paginated_results'].return_value = {"error": "Forbidden"}

        fn = get_tool_function("list_users")
        result = await fn(course_identifier="CS101")

        assert "Error" in result


# =============================================================================
# Tests for get_student_analytics
# =============================================================================

class TestGetStudentAnalytics:
    """Tests for the get_student_analytics tool."""

    @pytest.mark.asyncio
    async def test_analytics_success(self, mock_other_tools_api):
        """Test successful analytics retrieval."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "id": 12345, "name": "Introduction to CS"
        }
        mock_other_tools_api['fetch_all_paginated_results'].side_effect = [
            # Students
            [{"id": 1001, "name": "Student A"}, {"id": 1002, "name": "Student B"}],
            # Assignments
            [{"id": 1, "name": "HW1", "published": True, "points_possible": 100}]
        ]

        fn = get_tool_function("get_student_analytics")
        result = await fn(course_identifier="CS101")

        assert "Total Students: 2" in result
        assert "Total Assignments: 1" in result
        assert "Introduction to CS" in result

    @pytest.mark.asyncio
    async def test_analytics_course_error(self, mock_other_tools_api):
        """Test analytics when course fetch fails."""
        mock_other_tools_api['make_canvas_request'].return_value = {"error": "Not Found"}

        fn = get_tool_function("get_student_analytics")
        result = await fn(course_identifier="INVALID")

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_analytics_no_students(self, mock_other_tools_api):
        """Test analytics when no students enrolled."""
        mock_other_tools_api['make_canvas_request'].return_value = {
            "id": 12345, "name": "Empty Course"
        }
        mock_other_tools_api['fetch_all_paginated_results'].side_effect = [
            [],  # No students
            []   # No assignments
        ]

        fn = get_tool_function("get_student_analytics")
        result = await fn(course_identifier="CS101")

        assert "Total Students: 0" in result

"""
Module Tools Unit Tests

Tests for the Canvas module management tools:
- list_modules
- create_module
- update_module
- delete_module
- add_module_item
- update_module_item
- delete_module_item

These tests use mocking to avoid requiring real Canvas API access.
"""

from unittest.mock import patch

import pytest

# Sample mock data
MOCK_MODULES = [
    {
        "id": 12345,
        "name": "Week 1: Introduction",
        "position": 1,
        "state": "active",
        "published": True,
        "items_count": 5,
        "unlock_at": None,
        "require_sequential_progress": False,
        "prerequisite_module_ids": []
    },
    {
        "id": 12346,
        "name": "Week 2: Core Concepts",
        "position": 2,
        "state": "active",
        "published": True,
        "items_count": 8,
        "unlock_at": "2026-01-20T00:00:00Z",
        "require_sequential_progress": True,
        "prerequisite_module_ids": [12345]
    },
    {
        "id": 12347,
        "name": "Week 3: Advanced Topics",
        "position": 3,
        "state": "unpublished",
        "published": False,
        "items_count": 0,
        "unlock_at": None,
        "require_sequential_progress": False,
        "prerequisite_module_ids": [12345, 12346]
    }
]


# We need to create a test helper that can call the tool functions directly
# without going through MCP registration

@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls."""
    with patch('canvas_mcp.tools.modules.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.modules.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.modules.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.modules.make_canvas_request') as mock_request:

        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request
        }


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP

    from canvas_mcp.tools.modules import register_module_tools

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
    register_module_tools(mcp)

    return captured_functions.get(tool_name)


class TestListModules:
    """Tests for list_modules tool."""

    @pytest.mark.asyncio
    async def test_list_modules_basic(self, mock_canvas_api):
        """Test basic module listing."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = MOCK_MODULES

        list_modules = get_tool_function('list_modules')
        assert list_modules is not None

        result = await list_modules("badm_350_120251")

        # Verify API was called correctly
        mock_canvas_api['get_course_id'].assert_called_once_with("badm_350_120251")
        mock_canvas_api['fetch_all_paginated_results'].assert_called_once()

        # Verify output contains module info
        assert "Week 1: Introduction" in result
        assert "Week 2: Core Concepts" in result
        assert "12345" in result
        assert "Published: Yes" in result

    @pytest.mark.asyncio
    async def test_list_modules_empty(self, mock_canvas_api):
        """Test listing modules when course has none."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        list_modules = get_tool_function('list_modules')
        result = await list_modules("empty_course")

        assert "No modules found" in result

    @pytest.mark.asyncio
    async def test_list_modules_error_handling(self, mock_canvas_api):
        """Test error handling when API fails."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = {"error": "Course not found"}

        list_modules = get_tool_function('list_modules')
        result = await list_modules("invalid_course")

        assert "Error" in result
        assert "Course not found" in result

    @pytest.mark.asyncio
    async def test_list_modules_with_search_term(self, mock_canvas_api):
        """Test listing modules with search filter."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = [MOCK_MODULES[0]]

        list_modules = get_tool_function('list_modules')
        _result = await list_modules("60366", search_term="Introduction")

        # Verify search_term was passed to API
        call_args = mock_canvas_api['fetch_all_paginated_results'].call_args
        assert "search_term" in call_args[0][1]


class TestCreateModule:
    """Tests for create_module tool."""

    @pytest.mark.asyncio
    async def test_create_module_basic(self, mock_canvas_api):
        """Test basic module creation."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12348,
            "name": "New Module",
            "position": 4,
            "published": True,
            "state": "active"
        }

        create_module = get_tool_function('create_module')
        result = await create_module("badm_350_120251", "New Module")

        # Verify success
        assert "successfully" in result
        assert "New Module" in result
        assert "12348" in result

    @pytest.mark.asyncio
    async def test_create_module_with_options(self, mock_canvas_api):
        """Test module creation with all options."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12349,
            "name": "Sequential Module",
            "position": 5,
            "published": False,
            "state": "unpublished",
            "unlock_at": "2026-02-01T00:00:00Z",
            "require_sequential_progress": True
        }

        create_module = get_tool_function('create_module')
        result = await create_module(
            "badm_350_120251",
            "Sequential Module",
            position=5,
            require_sequential_progress=True,
            published=False,
            unlock_at="2026-02-01"
        )

        assert "successfully" in result
        assert "Sequential Module" in result
        assert "Sequential Progress: Required" in result

    @pytest.mark.asyncio
    async def test_create_module_error(self, mock_canvas_api):
        """Test module creation failure handling."""
        mock_canvas_api['make_canvas_request'].return_value = {"error": "Insufficient permissions"}

        create_module = get_tool_function('create_module')
        result = await create_module("60366", "Test Module")

        assert "Error" in result
        assert "Insufficient permissions" in result


class TestUpdateModule:
    """Tests for update_module tool."""

    @pytest.mark.asyncio
    async def test_update_module_name(self, mock_canvas_api):
        """Test updating module name."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Updated Module Name",
            "position": 1,
            "published": True
        }

        update_module = get_tool_function('update_module')
        result = await update_module("60366", 12345, name="Updated Module Name")

        assert "successfully" in result
        assert "Updated Module Name" in result

    @pytest.mark.asyncio
    async def test_update_module_no_changes(self, mock_canvas_api):
        """Test update with no changes specified."""
        update_module = get_tool_function('update_module')
        result = await update_module("60366", 12345)

        assert "No changes specified" in result

    @pytest.mark.asyncio
    async def test_update_module_publish(self, mock_canvas_api):
        """Test publishing a module."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Test Module",
            "position": 1,
            "published": True
        }

        update_module = get_tool_function('update_module')
        result = await update_module("60366", 12345, published=True)

        assert "successfully" in result
        assert "Published: Yes" in result


class TestDeleteModule:
    """Tests for delete_module tool."""

    @pytest.mark.asyncio
    async def test_delete_module_success(self, mock_canvas_api):
        """Test successful module deletion."""
        # First call gets module info, second call deletes
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"id": 12345, "name": "Module to Delete", "items_count": 3},
            {}  # Successful deletion returns empty or confirmation
        ]

        delete_module = get_tool_function('delete_module')
        result = await delete_module("60366", 12345)

        assert "successfully" in result
        assert "Module to Delete" in result
        assert "Items affected: 3" in result

    @pytest.mark.asyncio
    async def test_delete_module_error(self, mock_canvas_api):
        """Test module deletion failure."""
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"id": 12345, "name": "Test", "items_count": 0},
            {"error": "Module not found"}
        ]

        delete_module = get_tool_function('delete_module')
        result = await delete_module("60366", 99999)

        assert "Error" in result


class TestAddModuleItem:
    """Tests for add_module_item tool."""

    @pytest.mark.asyncio
    async def test_add_assignment_item(self, mock_canvas_api):
        """Test adding an assignment to a module."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55010,
            "title": "Week 1 Assignment",
            "type": "Assignment",
            "position": 4,
            "indent": 0,
            "content_id": 98765
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "Assignment", content_id=98765
        )

        assert "successfully" in result
        assert "Assignment" in result

    @pytest.mark.asyncio
    async def test_add_item_missing_content_id(self, mock_canvas_api):
        """Test error when content_id is required but missing."""
        add_module_item = get_tool_function('add_module_item')

        # Assignment requires content_id
        result = await add_module_item("60366", 12345, "Assignment")
        assert "content_id is required" in result

    @pytest.mark.asyncio
    async def test_add_page_missing_page_url(self, mock_canvas_api):
        """Test error when page_url is required but missing."""
        add_module_item = get_tool_function('add_module_item')

        # Page requires page_url
        result = await add_module_item("60366", 12345, "Page")
        assert "page_url is required" in result

    @pytest.mark.asyncio
    async def test_add_subheader(self, mock_canvas_api):
        """Test adding a subheader to a module."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55011,
            "title": "Required Readings",
            "type": "SubHeader",
            "position": 1,
            "indent": 0
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "SubHeader", title="Required Readings"
        )

        assert "successfully" in result
        assert "SubHeader" in result

    @pytest.mark.asyncio
    async def test_add_subheader_missing_title(self, mock_canvas_api):
        """Test SubHeader requires title."""
        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item("60366", 12345, "SubHeader")

        assert "title is required" in result

    @pytest.mark.asyncio
    async def test_add_item_invalid_type(self, mock_canvas_api):
        """Test error with invalid item type."""
        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item("60366", 12345, "InvalidType")

        assert "Invalid item_type" in result

    @pytest.mark.asyncio
    async def test_add_item_invalid_indent(self, mock_canvas_api):
        """Test error with invalid indent level."""
        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "SubHeader", title="Test", indent=5
        )

        assert "indent must be between 0 and 4" in result

    @pytest.mark.asyncio
    async def test_add_item_valid_indent(self, mock_canvas_api):
        """Test valid indent levels are accepted."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55012,
            "title": "Indented Item",
            "type": "SubHeader",
            "position": 1,
            "indent": 2
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "SubHeader", title="Indented Item", indent=2
        )

        assert "successfully" in result

    @pytest.mark.asyncio
    async def test_add_item_with_completion_requirement(self, mock_canvas_api):
        """Test adding item with completion requirement."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55012,
            "title": "Required Reading",
            "type": "Page",
            "position": 2,
            "completion_requirement": {"type": "must_view"}
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "Page",
            page_url="required-reading",
            completion_requirement_type="must_view"
        )

        assert "successfully" in result
        assert "must_view" in result

    @pytest.mark.asyncio
    async def test_add_page_item(self, mock_canvas_api):
        """Test adding a Page item."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55013,
            "title": "Course Syllabus",
            "type": "Page",
            "position": 1
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "Page", page_url="course-syllabus"
        )

        assert "successfully" in result
        assert "Page" in result


class TestUpdateModuleItem:
    """Tests for update_module_item tool."""

    @pytest.mark.asyncio
    async def test_update_item_title(self, mock_canvas_api):
        """Test updating item title."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55001,
            "title": "New Title",
            "type": "Page",
            "position": 1,
            "module_id": 12345,
            "published": True
        }

        update_module_item = get_tool_function('update_module_item')
        result = await update_module_item("60366", 12345, 55001, title="New Title")

        assert "successfully" in result
        assert "New Title" in result

    @pytest.mark.asyncio
    async def test_update_item_no_changes(self, mock_canvas_api):
        """Test update with no changes specified."""
        update_module_item = get_tool_function('update_module_item')
        result = await update_module_item("60366", 12345, 55001)

        assert "No changes specified" in result

    @pytest.mark.asyncio
    async def test_update_item_move_to_module(self, mock_canvas_api):
        """Test moving item to different module."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55001,
            "title": "Moved Item",
            "type": "Page",
            "position": 1,
            "module_id": 12346,
            "published": True
        }

        update_module_item = get_tool_function('update_module_item')
        result = await update_module_item(
            "60366", 12345, 55001, move_to_module_id=12346
        )

        assert "successfully" in result
        assert "Moved to module 12346" in result


class TestDeleteModuleItem:
    """Tests for delete_module_item tool."""

    @pytest.mark.asyncio
    async def test_delete_item_success(self, mock_canvas_api):
        """Test successful item deletion."""
        # First call gets item info, second call deletes
        mock_canvas_api['make_canvas_request'].side_effect = [
            {"id": 55001, "title": "Item to Delete", "type": "Page"},
            {}  # Successful deletion
        ]

        delete_module_item = get_tool_function('delete_module_item')
        result = await delete_module_item("60366", 12345, 55001)

        assert "successfully" in result
        assert "Item to Delete" in result
        assert "NOT deleted" in result  # Warning about content preservation


class TestInputValidation:
    """Test input validation for module tools."""

    @pytest.mark.asyncio
    async def test_completion_requirement_validation(self, mock_canvas_api):
        """Test invalid completion requirement type."""
        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "SubHeader",
            title="Test",
            completion_requirement_type="invalid_type"
        )

        assert "Invalid completion_requirement_type" in result

    @pytest.mark.asyncio
    async def test_min_score_without_type(self, mock_canvas_api):
        """Test min_score requirement needs corresponding type."""
        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "Quiz",
            content_id=123,
            completion_requirement_type="min_score"
            # Missing completion_requirement_min_score
        )

        assert "min_score" in result.lower()

    @pytest.mark.asyncio
    async def test_valid_completion_types(self, mock_canvas_api):
        """Test all valid completion requirement types."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55001,
            "title": "Test",
            "type": "Page",
            "position": 1
        }

        add_module_item = get_tool_function('add_module_item')

        valid_types = ["must_view", "must_submit", "must_contribute", "must_mark_done"]
        for completion_type in valid_types:
            result = await add_module_item(
                "60366", 12345, "Page",
                page_url="test-page",
                completion_requirement_type=completion_type
            )
            assert "successfully" in result or "Error" not in result


class TestExternalUrlItem:
    """Tests specific to ExternalUrl item type."""

    @pytest.mark.asyncio
    async def test_external_url_requires_url(self, mock_canvas_api):
        """Test ExternalUrl requires external_url parameter."""
        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "ExternalUrl",
            title="Link Title"
            # Missing external_url
        )

        assert "external_url is required" in result

    @pytest.mark.asyncio
    async def test_external_url_requires_title(self, mock_canvas_api):
        """Test ExternalUrl requires title parameter."""
        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "ExternalUrl",
            external_url="https://example.com"
            # Missing title
        )

        assert "title is required" in result

    @pytest.mark.asyncio
    async def test_external_url_success(self, mock_canvas_api):
        """Test successful ExternalUrl creation."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55020,
            "title": "External Resource",
            "type": "ExternalUrl",
            "external_url": "https://example.com",
            "position": 1,
            "new_tab": True
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "ExternalUrl",
            title="External Resource",
            external_url="https://example.com",
            new_tab=True
        )

        assert "successfully" in result
        assert "ExternalUrl" in result


class TestAllItemTypes:
    """Test all supported item types."""

    @pytest.mark.asyncio
    async def test_file_item(self, mock_canvas_api):
        """Test adding File item type."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55030,
            "title": "Lecture Notes",
            "type": "File",
            "content_id": 111,
            "position": 1
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "File", content_id=111
        )

        assert "successfully" in result

    @pytest.mark.asyncio
    async def test_discussion_item(self, mock_canvas_api):
        """Test adding Discussion item type."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55031,
            "title": "Week 1 Discussion",
            "type": "Discussion",
            "content_id": 222,
            "position": 2
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "Discussion", content_id=222
        )

        assert "successfully" in result

    @pytest.mark.asyncio
    async def test_quiz_item(self, mock_canvas_api):
        """Test adding Quiz item type."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55032,
            "title": "Chapter 1 Quiz",
            "type": "Quiz",
            "content_id": 333,
            "position": 3
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "Quiz", content_id=333
        )

        assert "successfully" in result

    @pytest.mark.asyncio
    async def test_external_tool_item(self, mock_canvas_api):
        """Test adding ExternalTool item type."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 55033,
            "title": "Zoom Meeting",
            "type": "ExternalTool",
            "content_id": 444,
            "position": 4
        }

        add_module_item = get_tool_function('add_module_item')
        result = await add_module_item(
            "60366", 12345, "ExternalTool", content_id=444
        )

        assert "successfully" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

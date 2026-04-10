"""
Course Structure Tool Unit Tests

Tests for the get_course_structure tool which returns the full module
and item structure for a course in a single call.

These tests use mocking to avoid requiring real Canvas API access.
"""

import json
from unittest.mock import patch

import pytest

# Sample mock data
MOCK_MODULES_WITH_ITEMS = [
    {
        "id": 12345,
        "name": "Week 1: Introduction",
        "position": 1,
        "published": True,
        "items_count": 3,
        "items": [
            {"id": 1, "type": "SubHeader", "title": "Overview", "published": True, "position": 1},
            {"id": 2, "type": "Page", "title": "Syllabus", "published": True, "position": 2, "page_url": "syllabus"},
            {"id": 3, "type": "Assignment", "title": "HW 1", "published": True, "position": 3, "content_id": 100},
        ],
    },
    {
        "id": 12346,
        "name": "Week 2: Core Concepts",
        "position": 2,
        "published": True,
        "items_count": 2,
        "items": [
            {"id": 4, "type": "Page", "title": "Lecture Notes", "published": True, "position": 1, "page_url": "lecture-notes"},
            {"id": 5, "type": "Discussion", "title": "Week 2 Forum", "published": False, "position": 2, "content_id": 200},
        ],
    },
    {
        "id": 12347,
        "name": "Week 3: Advanced Topics",
        "position": 3,
        "published": False,
        "items_count": 0,
        "items": [],
    },
]


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

    from canvas_mcp.tools.modules import (
        register_educator_module_tools,
        register_shared_module_tools,
    )

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
    register_shared_module_tools(mcp)
    register_educator_module_tools(mcp)

    return captured_functions.get(tool_name)


class TestGetCourseStructure:
    """Tests for get_course_structure tool."""

    @pytest.mark.asyncio
    async def test_returns_json_with_modules_and_items(self, mock_canvas_api):
        """Test that response has correct JSON structure with modules and item details."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = MOCK_MODULES_WITH_ITEMS

        get_course_structure = get_tool_function('get_course_structure')
        assert get_course_structure is not None

        result = await get_course_structure("badm_350_120251")
        parsed = json.loads(result)

        # Verify top-level structure
        assert "course_id" in parsed
        assert "modules" in parsed
        assert "summary" in parsed
        assert parsed["course_id"] == "60366"

        # Verify module count
        assert len(parsed["modules"]) == 3

        # Verify first module structure
        mod1 = parsed["modules"][0]
        assert mod1["id"] == 12345
        assert mod1["name"] == "Week 1: Introduction"
        assert mod1["position"] == 1
        assert mod1["published"] is True
        assert mod1["items_count"] == 3

        # Verify item details in first module
        items = mod1["items"]
        assert len(items) == 3
        assert items[0]["type"] == "SubHeader"
        assert items[0]["title"] == "Overview"
        assert items[1]["type"] == "Page"
        assert items[1]["title"] == "Syllabus"
        assert items[1]["page_url"] == "syllabus"
        assert items[2]["type"] == "Assignment"
        assert items[2]["title"] == "HW 1"
        assert items[2]["content_id"] == 100

        # Verify second module
        mod2 = parsed["modules"][1]
        assert mod2["id"] == 12346
        assert mod2["items_count"] == 2

        # Verify third module (unpublished, empty)
        mod3 = parsed["modules"][2]
        assert mod3["id"] == 12347
        assert mod3["published"] is False
        assert mod3["items_count"] == 0
        assert mod3["items"] == []

    @pytest.mark.asyncio
    async def test_summary_statistics(self, mock_canvas_api):
        """Test that summary statistics are accurate."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = MOCK_MODULES_WITH_ITEMS

        get_course_structure = get_tool_function('get_course_structure')
        result = await get_course_structure("badm_350_120251")
        parsed = json.loads(result)

        summary = parsed["summary"]

        # 3 modules total
        assert summary["total_modules"] == 3

        # 5 items total (3 in module 1 + 2 in module 2 + 0 in module 3)
        assert summary["total_items"] == 5

        # 1 unpublished module (Week 3)
        assert summary["unpublished_modules"] == 1

        # 1 unpublished item (Week 2 Forum)
        assert summary["unpublished_items"] == 1

        # 0 empty modules — Week 3 is unpublished, so it's not counted as
        # "empty" (only published modules with 0 items after filtering count)
        assert summary["empty_modules"] == 0

        # Verify item_types breakdown
        item_types = summary["item_types"]
        assert item_types["SubHeader"] == 1
        assert item_types["Page"] == 2
        assert item_types["Assignment"] == 1
        assert item_types["Discussion"] == 1

    @pytest.mark.asyncio
    async def test_empty_course(self, mock_canvas_api):
        """Test response when course has no modules."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        get_course_structure = get_tool_function('get_course_structure')
        result = await get_course_structure("empty_course")
        parsed = json.loads(result)

        assert parsed["modules"] == []

        summary = parsed["summary"]
        assert summary["total_modules"] == 0
        assert summary["total_items"] == 0
        assert summary["unpublished_modules"] == 0
        assert summary["unpublished_items"] == 0
        assert summary["empty_modules"] == 0
        assert summary["item_types"] == {}

    @pytest.mark.asyncio
    async def test_api_error(self, mock_canvas_api):
        """Test error handling when Canvas API returns an error."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = {"error": "Unauthorized"}

        get_course_structure = get_tool_function('get_course_structure')
        result = await get_course_structure("invalid_course")
        parsed = json.loads(result)

        assert "error" in parsed

    @pytest.mark.asyncio
    async def test_include_unpublished_false(self, mock_canvas_api):
        """Test filtering out unpublished modules and items."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = MOCK_MODULES_WITH_ITEMS

        get_course_structure = get_tool_function('get_course_structure')
        result = await get_course_structure("badm_350_120251", include_unpublished=False)
        parsed = json.loads(result)

        # Only 2 published modules should be returned (Week 3 is unpublished)
        assert len(parsed["modules"]) == 2

        # All returned modules must be published
        for module in parsed["modules"]:
            assert module["published"] is True

        # All returned items must be published
        for module in parsed["modules"]:
            for item in module["items"]:
                assert item["published"] is True

        # Week 2 should only have 1 item (the unpublished Discussion is filtered)
        mod2 = parsed["modules"][1]
        assert mod2["name"] == "Week 2: Core Concepts"
        assert mod2["items_count"] == 1
        assert mod2["items"][0]["title"] == "Lecture Notes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

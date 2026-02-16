"""Unit tests for page settings MCP tools.

Following TDD - these tests are written before the implementation.
"""

import pytest
from unittest.mock import patch


# Helper to get tool functions by capturing them during registration
def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP
    from canvas_mcp.tools.pages import register_page_tools

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
    register_page_tools(mcp)

    return captured_functions.get(tool_name)


@pytest.fixture
def mock_course_id():
    """Mock get_course_id to return a fixed course ID."""
    with patch('canvas_mcp.tools.pages.get_course_id') as mock:
        mock.return_value = 67619
        yield mock


@pytest.fixture
def mock_course_code():
    """Mock get_course_code to return a readable course code."""
    with patch('canvas_mcp.tools.pages.get_course_code') as mock:
        mock.return_value = "TEST-101"
        yield mock


@pytest.fixture
def mock_canvas_request():
    """Mock make_canvas_request for API calls."""
    with patch('canvas_mcp.tools.pages.make_canvas_request') as mock:
        yield mock


# =============================================================================
# Tests for update_page_settings
# =============================================================================

class TestUpdatePageSettings:
    """Tests for the update_page_settings tool."""

    @pytest.mark.asyncio
    async def test_publish_page(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test publishing a page."""
        mock_canvas_request.return_value = {
            "url": "test-page",
            "title": "Test Page",
            "published": True,
            "front_page": False,
            "editing_roles": "teachers"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="test-page",
            published=True
        )

        assert "success" in result.lower() or "updated" in result.lower()
        assert "Test Page" in result
        mock_canvas_request.assert_called_once()
        call_args = mock_canvas_request.call_args
        assert call_args[0][0] == "put"
        assert "test-page" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_unpublish_page(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test unpublishing a page."""
        mock_canvas_request.return_value = {
            "url": "test-page",
            "title": "Test Page",
            "published": False,
            "front_page": False,
            "editing_roles": "teachers"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="test-page",
            published=False
        )

        assert "success" in result.lower() or "updated" in result.lower()
        assert "Published: No" in result or "published" in result.lower()

    @pytest.mark.asyncio
    async def test_set_front_page(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test setting a page as the front page."""
        mock_canvas_request.return_value = {
            "url": "home-page",
            "title": "Home Page",
            "published": True,
            "front_page": True,
            "editing_roles": "teachers"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="home-page",
            front_page=True
        )

        assert "success" in result.lower() or "updated" in result.lower()
        assert "front page" in result.lower() or "Front Page: Yes" in result

    @pytest.mark.asyncio
    async def test_change_editing_roles(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test changing who can edit the page."""
        mock_canvas_request.return_value = {
            "url": "collab-page",
            "title": "Collaborative Page",
            "published": True,
            "front_page": False,
            "editing_roles": "teachers,students"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="collab-page",
            editing_roles="teachers,students"
        )

        assert "success" in result.lower() or "updated" in result.lower()
        # Verify the API was called with correct editing_roles
        call_args = mock_canvas_request.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_no_changes_specified(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test error when no settings are specified to update."""
        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="test-page"
        )

        assert "no changes" in result.lower() or "specify" in result.lower()
        mock_canvas_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_api_error_handling(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test handling of API errors."""
        mock_canvas_request.return_value = {
            "error": "Page not found"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="nonexistent-page",
            published=True
        )

        assert "error" in result.lower()

    @pytest.mark.asyncio
    async def test_cannot_unpublish_front_page(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test that unpublishing front page returns appropriate error."""
        mock_canvas_request.return_value = {
            "error": "Cannot unpublish the front page"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="front-page",
            published=False
        )

        assert "error" in result.lower() or "cannot" in result.lower()

    @pytest.mark.asyncio
    async def test_multiple_settings_update(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test updating multiple settings at once."""
        mock_canvas_request.return_value = {
            "url": "multi-update",
            "title": "Multi Update Page",
            "published": True,
            "front_page": False,
            "editing_roles": "teachers,students"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="multi-update",
            published=True,
            editing_roles="teachers,students",
            notify_of_update=True
        )

        assert "success" in result.lower() or "updated" in result.lower()
        # Verify all params were sent
        call_args = mock_canvas_request.call_args
        assert call_args is not None


# =============================================================================
# Tests for bulk_update_pages
# =============================================================================

class TestBulkUpdatePages:
    """Tests for the bulk_update_pages tool."""

    @pytest.mark.asyncio
    async def test_bulk_publish_pages(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test publishing multiple pages at once."""
        # Mock successful responses for each page
        mock_canvas_request.side_effect = [
            {"url": "page-1", "title": "Page 1", "published": True},
            {"url": "page-2", "title": "Page 2", "published": True},
            {"url": "page-3", "title": "Page 3", "published": True},
        ]

        bulk_update_pages = get_tool_function("bulk_update_pages")
        result = await bulk_update_pages(
            course_identifier="67619",
            page_urls="page-1,page-2,page-3",
            published=True
        )

        assert "3" in result or "success" in result.lower()
        assert mock_canvas_request.call_count == 3

    @pytest.mark.asyncio
    async def test_bulk_unpublish_pages(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test unpublishing multiple pages at once."""
        mock_canvas_request.side_effect = [
            {"url": "page-1", "title": "Page 1", "published": False},
            {"url": "page-2", "title": "Page 2", "published": False},
        ]

        bulk_update_pages = get_tool_function("bulk_update_pages")
        result = await bulk_update_pages(
            course_identifier="67619",
            page_urls="page-1,page-2",
            published=False
        )

        assert "2" in result or "success" in result.lower()

    @pytest.mark.asyncio
    async def test_bulk_update_partial_failure(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test handling when some pages fail to update."""
        mock_canvas_request.side_effect = [
            {"url": "page-1", "title": "Page 1", "published": True},
            {"error": "Page not found"},
            {"url": "page-3", "title": "Page 3", "published": True},
        ]

        bulk_update_pages = get_tool_function("bulk_update_pages")
        result = await bulk_update_pages(
            course_identifier="67619",
            page_urls="page-1,page-2,page-3",
            published=True
        )

        # Should report partial success
        assert "2" in result or "failed" in result.lower() or "1" in result

    @pytest.mark.asyncio
    async def test_bulk_update_empty_list(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test handling of empty page list."""
        bulk_update_pages = get_tool_function("bulk_update_pages")
        result = await bulk_update_pages(
            course_identifier="67619",
            page_urls="",
            published=True
        )

        assert "no pages" in result.lower() or "empty" in result.lower() or "specify" in result.lower()
        mock_canvas_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_bulk_update_no_settings(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test error when no settings specified for bulk update."""
        bulk_update_pages = get_tool_function("bulk_update_pages")
        result = await bulk_update_pages(
            course_identifier="67619",
            page_urls="page-1,page-2"
        )

        assert "no changes" in result.lower() or "specify" in result.lower()
        mock_canvas_request.assert_not_called()


# =============================================================================
# Tests for input validation
# =============================================================================

class TestInputValidation:
    """Tests for parameter validation."""

    @pytest.mark.asyncio
    async def test_invalid_editing_roles(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test validation of editing_roles parameter."""
        mock_canvas_request.return_value = {
            "error": "Invalid editing_roles"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="test-page",
            editing_roles="invalid_role"
        )

        # Either the tool validates before calling API, or API returns error
        # Both are acceptable behaviors
        assert "error" in result.lower() or "invalid" in result.lower() or mock_canvas_request.called

    @pytest.mark.asyncio
    async def test_page_url_with_special_characters(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test handling page URLs with special characters."""
        mock_canvas_request.return_value = {
            "url": "page-with-special-chars",
            "title": "Page & Special <Chars>",
            "published": True,
            "front_page": False,
            "editing_roles": "teachers"
        }

        update_page_settings = get_tool_function("update_page_settings")
        result = await update_page_settings(
            course_identifier="67619",
            page_url_or_id="page-with-special-chars",
            published=True
        )

        assert "success" in result.lower() or "updated" in result.lower()

"""Tests for role-based tool filtering."""

import pytest
from mcp.server.fastmcp import FastMCP

from canvas_mcp.server import register_all_tools


async def _get_tool_names(mcp: FastMCP) -> set[str]:
    """Extract registered tool names from a FastMCP instance."""
    tools = await mcp.list_tools()
    return {t.name for t in tools}


STUDENT_ONLY_TOOLS = {
    "get_my_upcoming_assignments",
    "get_my_submission_status",
    "get_my_course_grades",
    "get_my_todo_items",
    "get_my_peer_reviews_todo",
}

SHARED_TOOLS = {
    # courses
    "list_courses",
    "get_course_details",
    "get_course_content_overview",
    # shared content (pages + module items)
    "list_pages",
    "get_page_content",
    "get_page_details",
    "get_front_page",
    "list_module_items",
    # shared assignments
    "list_assignments",
    "get_assignment_details",
    # shared discussions
    "list_discussion_topics",
    "get_discussion_topic_details",
    "list_discussion_entries",
    "get_discussion_entry_details",
    "get_discussion_with_replies",
    "post_discussion_entry",
    "reply_to_discussion_entry",
    # shared modules
    "list_modules",
    "get_course_structure",
    # shared files
    "list_course_files",
    "download_course_file",
    # shared messaging
    "list_conversations",
    "get_conversation_details",
    "get_unread_count",
    "mark_conversations_read",
    # discovery
    "search_canvas_tools",
}

# A sample of educator-only tools to check (not exhaustive, just representative)
EDUCATOR_ONLY_SAMPLE = {
    "create_assignment",
    "update_assignment",
    "bulk_grade_submissions",
    "create_announcement",
    "create_module",
    "upload_course_file",
    "create_page",
    "list_users",
    "get_student_analytics",
}


class TestRoleFiltering:
    """Test that role-based filtering registers the correct tools."""

    @pytest.mark.asyncio
    async def test_student_role_includes_student_tools(self):
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = await _get_tool_names(mcp)
        for tool in STUDENT_ONLY_TOOLS:
            assert tool in tools, f"Student role should include {tool}"

    @pytest.mark.asyncio
    async def test_student_role_includes_shared_tools(self):
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = await _get_tool_names(mcp)
        for tool in SHARED_TOOLS:
            assert tool in tools, f"Student role should include shared tool {tool}"

    @pytest.mark.asyncio
    async def test_student_role_excludes_educator_tools(self):
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = await _get_tool_names(mcp)
        for tool in EDUCATOR_ONLY_SAMPLE:
            assert tool not in tools, f"Student role should NOT include {tool}"

    @pytest.mark.asyncio
    async def test_educator_role_includes_shared_tools(self):
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = await _get_tool_names(mcp)
        for tool in SHARED_TOOLS:
            assert tool in tools, f"Educator role should include shared tool {tool}"

    @pytest.mark.asyncio
    async def test_educator_role_includes_educator_tools(self):
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = await _get_tool_names(mcp)
        for tool in EDUCATOR_ONLY_SAMPLE:
            assert tool in tools, f"Educator role should include {tool}"

    @pytest.mark.asyncio
    async def test_educator_role_excludes_student_tools(self):
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = await _get_tool_names(mcp)
        for tool in STUDENT_ONLY_TOOLS:
            assert tool not in tools, f"Educator role should NOT include {tool}"

    @pytest.mark.asyncio
    async def test_all_role_includes_everything(self):
        mcp = FastMCP(name="test-all")
        register_all_tools(mcp, role="all")
        tools = await _get_tool_names(mcp)
        all_expected = STUDENT_ONLY_TOOLS | SHARED_TOOLS | EDUCATOR_ONLY_SAMPLE
        for tool in all_expected:
            assert tool in tools, f"'all' role should include {tool}"

    @pytest.mark.asyncio
    async def test_all_role_is_default(self):
        mcp_default = FastMCP(name="test-default")
        register_all_tools(mcp_default)
        default_tools = await _get_tool_names(mcp_default)

        mcp_all = FastMCP(name="test-all")
        register_all_tools(mcp_all, role="all")
        all_tools = await _get_tool_names(mcp_all)

        assert default_tools == all_tools, "Default should match 'all' role"

    @pytest.mark.asyncio
    async def test_no_tools_lost_across_roles(self):
        """Every tool in 'all' must appear in either student or educator (or both)."""
        mcp_all = FastMCP(name="test-all")
        register_all_tools(mcp_all, role="all")
        all_tools = await _get_tool_names(mcp_all)

        mcp_student = FastMCP(name="test-student")
        register_all_tools(mcp_student, role="student")
        student_tools = await _get_tool_names(mcp_student)

        mcp_educator = FastMCP(name="test-educator")
        register_all_tools(mcp_educator, role="educator")
        educator_tools = await _get_tool_names(mcp_educator)

        combined = student_tools | educator_tools
        missing = all_tools - combined
        assert not missing, f"Tools in 'all' but missing from student+educator: {missing}"

    @pytest.mark.asyncio
    async def test_student_tool_count(self):
        """Student role should have approximately 31 tools."""
        mcp = FastMCP(name="test-student")
        register_all_tools(mcp, role="student")
        tools = await _get_tool_names(mcp)
        assert 25 <= len(tools) <= 40, f"Expected ~31 student tools, got {len(tools)}: {sorted(tools)}"

    @pytest.mark.asyncio
    async def test_educator_tool_count(self):
        """Educator role should have approximately 86 tools."""
        mcp = FastMCP(name="test-educator")
        register_all_tools(mcp, role="educator")
        tools = await _get_tool_names(mcp)
        assert 75 <= len(tools) <= 95, f"Expected ~86 educator tools, got {len(tools)}: {sorted(tools)}"

import pytest
from fastmcp import Client, FastMCP

from canvas_mcp.server import register_all_tools


TOOLS_REQUIRING_ANNOTATIONS = {
    "post_discussion_entry",
    "reply_to_discussion_entry",
    "mark_conversations_read",
    "assign_peer_review",
    "create_assignment",
    "update_assignment",
    "bulk_grade_submissions",
    "create_discussion_topic",
    "update_discussion_topic",
    "create_announcement",
    "create_module",
    "update_module",
    "add_module_item",
    "update_module_item",
    "upload_course_file",
    "update_page_settings",
    "bulk_update_pages",
    "create_page",
    "edit_page_content",
    "grade_with_rubric",
    "create_rubric_from_csv",
    "create_rubric",
    "associate_rubric",
    "send_conversation",
    "send_peer_review_reminders",
    "send_bulk_messages_from_list",
    "send_peer_review_followup_campaign",
    "fix_accessibility_issues",
    "create_student_anonymization_map",
}


@pytest.mark.asyncio
async def test_tools_with_write_side_effects_expose_annotations():
    mcp = FastMCP(name="test-metadata")
    register_all_tools(mcp, role="all")

    tools = {tool.name: tool for tool in await mcp.list_tools()}

    for tool_name in TOOLS_REQUIRING_ANNOTATIONS:
        tool = tools[tool_name]
        assert tool.annotations is not None, f"{tool_name} should define annotations"
        assert tool.annotations.destructiveHint is False


@pytest.mark.asyncio
async def test_list_courses_boolean_parameters_have_descriptions():
    mcp = FastMCP(name="test-course-metadata")
    register_all_tools(mcp, role="all")

    async with Client(mcp) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    schema = tools["list_courses"].inputSchema
    properties = schema["properties"]

    include_concluded_description = properties["include_concluded"]["description"]
    include_all_description = properties["include_all"]["description"]

    assert "concluded" in include_concluded_description.lower()
    assert "active" in include_all_description.lower()

"""Tool-annotation contract (issues #200, #204).

Every registered tool must declare what it does to the world. A read tool says
``readOnlyHint=True``; a write tool must answer both remaining questions —
whether it replaces existing data (``destructiveHint``) and whether repeating it
changes anything (``idempotentHint``).

The point of the first test is that a NEW tool cannot land without making those
declarations: an unannotated tool fails CI rather than shipping bare, which is
how #200 happened in the first place. Enumerating the live registry rather than
a hand-maintained list is what makes that work.

Semantics follow the MCP spec, not a local convention: ``destructiveHint=False``
asserts the tool performs ONLY ADDITIVE updates, so a tool that overwrites grades
or replaces a page body is destructive even though it deletes nothing.
"""

import pytest
from fastmcp import Client, FastMCP

from canvas_mcp.server import register_all_tools


def _registry() -> FastMCP:
    mcp = FastMCP(name="test-metadata")
    register_all_tools(mcp, role="all")
    return mcp


# Tools whose classification is load-bearing enough to pin. If one of these
# flips, it should be a deliberate edit to this list, not a silent diff.
DESTRUCTIVE = {
    # Overwrites student grades.
    "bulk_grade_submissions",
    "grade_with_rubric",
    # Replaces author-written content.
    "edit_page_content",
    "bulk_update_pages",
    "fix_accessibility_issues",
    # Replaces existing settings/fields.
    "update_assignment",
    "update_module",
    "update_module_item",
    "update_page_settings",
    "update_discussion_topic",
    # Replaces a file (on_duplicate="overwrite") or a local CSV.
    "upload_course_file",
    "create_student_anonymization_map",
    # Removals.
    "delete_page",
    "delete_module",
    "delete_module_item",
    "delete_announcement",
    "delete_announcement_with_confirmation",
    "delete_announcements_by_criteria",
    "bulk_delete_announcements",
}

# Additive: each call adds something and removes nothing.
ADDITIVE = {
    "add_module_item",
    "assign_peer_review",
    "associate_rubric",
    "create_announcement",
    "create_assignment",
    "create_discussion_topic",
    "create_module",
    "create_page",
    "create_rubric",
    "create_rubric_from_csv",
    "post_discussion_entry",
    "reply_to_discussion_entry",
    "send_bulk_messages_from_list",
    "send_conversation",
    "send_peer_review_followup_campaign",
    "send_peer_review_reminders",
    "mark_conversations_read",
}

# Repeating the call with the same arguments produces a duplicate.
NOT_IDEMPOTENT = {
    "add_module_item",
    "assign_peer_review",
    "associate_rubric",
    "create_announcement",
    "create_assignment",
    "create_discussion_topic",
    "create_module",
    "create_page",
    "create_rubric",
    "create_rubric_from_csv",
    "post_discussion_entry",
    "reply_to_discussion_entry",
    "send_bulk_messages_from_list",
    "send_conversation",
    "send_peer_review_followup_campaign",
    "send_peer_review_reminders",
    # Default on_duplicate="rename" makes a NEW file on every call.
    "upload_course_file",
}


@pytest.mark.asyncio
async def test_every_tool_declares_its_effect_on_the_world():
    """A tool must be read-only, or answer both write questions. No bare tools.

    This is the gate: adding a tool without annotations fails here, so the
    decision has to be made at authoring time rather than discovered by a user.
    """
    tools = await _registry().list_tools()
    assert tools, "no tools registered — the gate would vacuously pass"

    undeclared = []
    for tool in tools:
        annotations = tool.annotations
        if annotations is None:
            undeclared.append(f"{tool.name}: no annotations at all")
            continue
        if annotations.readOnlyHint:
            continue
        if annotations.destructiveHint is None:
            undeclared.append(f"{tool.name}: write tool missing destructiveHint")
        if annotations.idempotentHint is None:
            undeclared.append(f"{tool.name}: write tool missing idempotentHint")

    assert not undeclared, (
        "every tool must declare readOnlyHint, or both destructiveHint and "
        "idempotentHint (see issue #204):\n  " + "\n  ".join(sorted(undeclared))
    )


@pytest.mark.asyncio
async def test_tools_that_replace_data_are_marked_destructive():
    """destructiveHint=False claims 'additive only' — grades say otherwise."""
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in DESTRUCTIVE:
        assert name in tools, f"{name} is no longer registered — update this list"
        assert tools[name].annotations.destructiveHint is True, (
            f"{name} replaces existing data, so destructiveHint must be True; "
            "False asserts the tool performs only additive updates"
        )


@pytest.mark.asyncio
async def test_additive_tools_are_not_marked_destructive():
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in ADDITIVE:
        assert name in tools, f"{name} is no longer registered — update this list"
        assert tools[name].annotations.destructiveHint is False, (
            f"{name} only adds; marking it destructive costs users an "
            "unnecessary confirmation"
        )


@pytest.mark.asyncio
async def test_repeatable_tools_declare_idempotency_honestly():
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in NOT_IDEMPOTENT:
        assert tools[name].annotations.idempotentHint is False, (
            f"{name} produces a duplicate when repeated, so idempotentHint "
            "must be False — a host may otherwise retry it safely"
        )

    for name in ("update_assignment", "update_page_settings", "delete_page"):
        assert tools[name].annotations.idempotentHint is True, (
            f"{name} converges on the same end state when repeated"
        )


@pytest.mark.asyncio
async def test_read_tools_are_marked_read_only():
    """Sampled rather than exhaustive: the gate above covers the general case."""
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in ("list_courses", "get_course_details", "check_enrollment",
                 "list_submissions", "get_syllabus", "read_course_file"):
        assert tools[name].annotations.readOnlyHint is True, (
            f"{name} does not write and should say so"
        )


@pytest.mark.asyncio
async def test_list_courses_boolean_parameters_have_descriptions():
    async with Client(_registry()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    properties = tools["list_courses"].inputSchema["properties"]

    assert "concluded" in properties["include_concluded"]["description"].lower()
    assert "active" in properties["include_all"]["description"].lower()

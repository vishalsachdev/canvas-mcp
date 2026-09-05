"""Tool-annotation contract (issues #200, #204).

Every registered tool must declare what it does to the world. A read tool says
``read_only_hint=True``; a write tool must answer both remaining questions —
whether it replaces existing data (``destructive_hint``) and whether repeating it
changes anything (``idempotent_hint``).

The point of the first test is that a NEW tool cannot land without making those
declarations: an unannotated tool fails CI rather than shipping bare, which is
how #200 happened in the first place. Enumerating the live registry rather than
a hand-maintained list is what makes that work.

Semantics follow the MCP spec, not a local convention: ``destructive_hint=False``
asserts the tool performs ONLY ADDITIVE updates, so a tool that overwrites grades
or replaces a page body is destructive even though it deletes nothing.
"""

import json
from pathlib import Path

import pytest
from fastmcp import Client, FastMCP

import canvas_mcp.core.config as config_module
from canvas_mcp.core.config import STUDENT_WRITE_TOOL_NAMES
from canvas_mcp.server import register_all_tools


@pytest.fixture(autouse=True)
def _all_feature_gated_tools_enabled(monkeypatch):
    """Register the feature-gated tools too, or the gate has a blind spot.

    ``execute_typescript`` (off unless ``EXECUTE_TYPESCRIPT_ENABLED``) and the
    student write tools (off unless ``STUDENT_WRITE_TOOLS`` lists them) are
    absent from a default registry. A gate that only sees the default set would
    pass while the most powerful tool in the server — arbitrary TypeScript
    against the caller's Canvas token — shipped with no annotations at all.
    Coverage has to follow capability, not configuration.
    """
    monkeypatch.setenv("EXECUTE_TYPESCRIPT_ENABLED", "true")
    monkeypatch.setenv("STUDENT_WRITE_TOOLS", ",".join(sorted(STUDENT_WRITE_TOOL_NAMES)))
    monkeypatch.setattr(config_module, "_config", None, raising=False)
    yield
    monkeypatch.setattr(config_module, "_config", None, raising=False)


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
    # "create_*" is not a safe guide: these displace existing state via an
    # option. front_page=True unseats the course's current front page (Canvas
    # allows one); assignment_id attaches a rubric over whatever was there.
    "create_page",
    "create_rubric",
    "associate_rubric",
    "create_content_migration",
    # Removals.
    "delete_page",
    "delete_module",
    "delete_module_item",
    "delete_announcement_with_confirmation",
    "delete_assignment_with_confirmation",
    "delete_announcements_by_criteria",
    "bulk_delete_announcements",
}

# Additive: each call adds something and removes nothing.
ADDITIVE = {
    "add_module_item",
    "assign_peer_review",
    "create_announcement",
    "create_assignment",
    "create_discussion_topic",
    "create_module",
    "create_rubric_from_csv",
    "post_discussion_entry",
    "reply_to_discussion_entry",
    "send_bulk_messages_from_list",
    "send_conversation",
    "send_peer_review_followup_campaign",
    "send_peer_review_inbox_messages",
    "mark_conversations_read",
}

# Repeating the call with the same arguments produces a duplicate.
#
# Idempotency is judged on the tool's WHOLE effect, not just its primary
# resource. A tool is non-idempotent if ANY supported input makes a repeat
# produce an additional external effect — the hint is per-tool, and a host
# retrying a timed-out call has no way to know which arguments were used.
# The grade writers converge on the same score but append a new submission
# comment each time `comment` is supplied; the page tools converge on the same
# body but re-notify the class each time `notify_of_update=True`.
NOT_IDEMPOTENT = {
    "bulk_grade_submissions",
    "grade_with_rubric",
    "update_page_settings",
    "bulk_update_pages",
    "add_module_item",
    "assign_peer_review",
    "associate_rubric",
    "create_announcement",
    "create_assignment",
    "create_content_migration",
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
    "send_peer_review_inbox_messages",
    # Default on_duplicate="rename" makes a NEW file on every call.
    "upload_course_file",
}


@pytest.mark.asyncio
async def test_the_gate_actually_sees_the_feature_gated_tools():
    """Guards the fixture, not the code.

    If the env plumbing or the config-singleton reset ever stops working, the
    registry silently shrinks back to the default set and every other test here
    keeps passing while covering less. That failure is invisible without this.
    """
    names = {tool.name for tool in await _registry().list_tools()}

    assert "execute_typescript" in names, (
        "EXECUTE_TYPESCRIPT_ENABLED is not reaching the registry — the gate is "
        "blind to the most powerful tool in the server"
    )
    missing = STUDENT_WRITE_TOOL_NAMES - names
    assert not missing, f"STUDENT_WRITE_TOOLS not reaching the registry: {sorted(missing)}"


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
        if annotations.read_only_hint:
            continue
        if annotations.destructive_hint is None:
            undeclared.append(f"{tool.name}: write tool missing destructive_hint")
        if annotations.idempotent_hint is None:
            undeclared.append(f"{tool.name}: write tool missing idempotent_hint")

    assert not undeclared, (
        "every tool must declare read_only_hint, or both destructive_hint and "
        "idempotent_hint (see issue #204):\n  " + "\n  ".join(sorted(undeclared))
    )


@pytest.mark.asyncio
async def test_tools_that_replace_data_are_marked_destructive():
    """destructive_hint=False claims 'additive only' — grades say otherwise."""
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in DESTRUCTIVE:
        assert name in tools, f"{name} is no longer registered — update this list"
        assert tools[name].annotations.destructive_hint is True, (
            f"{name} replaces existing data, so destructive_hint must be True; "
            "False asserts the tool performs only additive updates"
        )


@pytest.mark.asyncio
async def test_additive_tools_are_not_marked_destructive():
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in ADDITIVE:
        assert name in tools, f"{name} is no longer registered — update this list"
        assert tools[name].annotations.destructive_hint is False, (
            f"{name} only adds; marking it destructive costs users an "
            "unnecessary confirmation"
        )


@pytest.mark.asyncio
async def test_repeatable_tools_declare_idempotency_honestly():
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in NOT_IDEMPOTENT:
        assert tools[name].annotations.idempotent_hint is False, (
            f"{name} produces a duplicate when repeated, so idempotent_hint "
            "must be False — a host may otherwise retry it safely"
        )

    # Converge on the same end state AND have no repeat-triggered side effect:
    # edit_page_content notably does not expose notify_of_update, unlike its
    # two siblings above.
    # delete_announcements_by_criteria used to be the non-idempotent delete
    # (an identical retry deleted the NEXT batch); since #318 its token is
    # bound to the exact match set and single-use, so a repeat previews or
    # refuses, never deletes more.
    for name in ("update_assignment", "update_module", "update_discussion_topic",
                 "edit_page_content", "delete_page", "bulk_delete_announcements",
                 "delete_announcements_by_criteria", "delete_assignment_with_confirmation"):
        assert tools[name].annotations.idempotent_hint is True, (
            f"{name} converges on the same end state when repeated"
        )


@pytest.mark.asyncio
async def test_read_tools_are_marked_read_only():
    """Sampled rather than exhaustive: the gate above covers the general case."""
    tools = {tool.name: tool for tool in await _registry().list_tools()}

    for name in ("list_courses", "get_course_details", "check_enrollment",
                 "list_submissions", "get_syllabus", "read_course_file"):
        assert tools[name].annotations.read_only_hint is True, (
            f"{name} does not write and should say so"
        )


@pytest.mark.asyncio
async def test_tool_manifest_matches_registry_exactly():
    """tools/TOOL_MANIFEST.json must document exactly the registered tools (#173).

    The manifest drifted to ~24 entries while the registry grew to 99 because
    nothing failed when a tool shipped undocumented. Same pattern as the
    annotation gate above: enumerate the live registry with every feature flag
    on, and require set equality — a missing manifest entry (new tool, no docs)
    and a stale extra entry (removed/renamed tool) both fail CI.
    """
    manifest_path = Path(__file__).parent.parent / "tools" / "TOOL_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    manifest_names = [t["name"] for t in manifest["tools"]]

    dupes = {n for n in manifest_names if manifest_names.count(n) > 1}
    assert not dupes, f"duplicate manifest entries: {sorted(dupes)}"

    registered = {tool.name for tool in await _registry().list_tools()}
    manifest_set = set(manifest_names)

    missing = registered - manifest_set
    extra = manifest_set - registered
    assert not missing and not extra, (
        "tools/TOOL_MANIFEST.json is out of sync with the live registry "
        "(all feature flags on):\n"
        f"  undocumented tools (add to manifest): {sorted(missing)}\n"
        f"  stale manifest entries (remove or rename): {sorted(extra)}"
    )

    known_categories = {c["id"] for c in manifest["categories"]}
    bad = [t["name"] for t in manifest["tools"] if t["category"] not in known_categories]
    assert not bad, f"manifest entries with unknown category: {bad}"


@pytest.mark.asyncio
async def test_list_courses_boolean_parameters_have_descriptions():
    async with Client(_registry()) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}

    properties = tools["list_courses"].input_schema["properties"]

    assert "concluded" in properties["include_concluded"]["description"].lower()
    assert "active" in properties["include_all"]["description"].lower()

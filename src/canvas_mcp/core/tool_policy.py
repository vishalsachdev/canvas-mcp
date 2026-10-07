"""Operator-controlled allowlist for tools that change anything.

Why this exists (GHSA-hmr8-mvr2-mvw5): a student can plant instructions in
content the instructor's assistant later reads (an Inbox message, a discussion
post, a submission). If the model follows them, it can gather course data with
read tools and send it out, or change grades. Previews and confirmation tokens
do not stop that: the model receives its own token and can redeem it, so a token
binds a request to a specific change, not to a human's approval. The boundary a
prompt injection cannot talk its way past is one the model has no hand in: which
tools exist at all, fixed by the operator in the server's environment.

Every registered tool is classified here by what it can change. Read tools are
always available. Tools with side effects are available only when the operator
allows them through ``ALLOWED_WRITE_TOOLS``:

- unset: on the HTTP transport, none (the hosted default is read-only); on
  stdio, everything, which is the behaviour before this policy existed
- set but empty (blank, spaces or only commas): the same as ``none``
- ``none``: no side-effect tools on either transport
- ``all``: every Canvas-write and local-write tool, but NOT code execution
- a comma- or space-separated list of tool names: exactly those (add
  ``execute_typescript`` here to allow code execution, on top of its own
  ``EXECUTE_TYPESCRIPT_ENABLED`` flag)

The policy only removes tools after registration. It can never bring back a
tool that a registration gate (``CANVAS_ROLE``, ``STUDENT_WRITE_TOOLS``,
``EXECUTE_TYPESCRIPT_ENABLED``) left out, and no tool can change it at runtime.
A removed tool is gone from the registry, so it is neither listed nor callable
by name. ``read_only_hint`` is not trusted on its own: the classification below
is explicit, and ``tests/security/test_tool_policy.py`` requires it to cover
every tool and to agree with the annotations.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from fastmcp import FastMCP

ALLOWLIST_ENV = "ALLOWED_WRITE_TOOLS"

Transport = Literal["stdio", "http"]


class Effect(StrEnum):
    """What a tool can change."""

    READ = "read"
    # Changes Canvas state, including sending messages.
    CANVAS_WRITE = "canvas_write"
    # Writes to the server's own filesystem (these tools refuse on HTTP anyway).
    LOCAL_WRITE = "local_write"
    # Runs caller-supplied code with the caller's Canvas token.
    CODE_EXEC = "code_exec"


TOOL_EFFECTS: dict[str, Effect] = {
    # --- READ (67) ---
    "analyze_peer_review_quality": Effect.READ,
    "calculate_grade_scenarios": Effect.READ,
    "check_enrollment": Effect.READ,
    "fetch_ufixit_report": Effect.READ,
    "format_accessibility_summary": Effect.READ,
    "generate_peer_review_feedback_report": Effect.READ,
    "get_anonymization_status": Effect.READ,
    "get_assignment_analytics": Effect.READ,
    "get_assignment_details": Effect.READ,
    "get_content_migration_status": Effect.READ,
    "get_conversation_details": Effect.READ,
    "get_course_content_overview": Effect.READ,
    "get_course_details": Effect.READ,
    "get_course_structure": Effect.READ,
    "get_discussion_entry_details": Effect.READ,
    "get_discussion_topic_details": Effect.READ,
    "get_discussion_with_replies": Effect.READ,
    "get_front_page": Effect.READ,
    "get_my_activity_stream": Effect.READ,
    "get_group_members": Effect.READ,
    "get_my_assignment_scores": Effect.READ,
    "get_my_course_grades": Effect.READ,
    "get_my_enrollments": Effect.READ,
    "get_my_peer_reviews_todo": Effect.READ,
    "get_my_profile": Effect.READ,
    "get_my_submission": Effect.READ,
    "get_my_submission_status": Effect.READ,
    "get_my_todo_items": Effect.READ,
    "get_my_upcoming_assignments": Effect.READ,
    "get_page_content": Effect.READ,
    "get_page_details": Effect.READ,
    "get_peer_review_assignments": Effect.READ,
    "get_peer_review_comments": Effect.READ,
    "get_peer_review_completion_analytics": Effect.READ,
    "get_peer_review_followup_list": Effect.READ,
    "get_quiz_details": Effect.READ,
    "get_rubric": Effect.READ,
    "get_rubric_assessment": Effect.READ,
    "get_student_analytics": Effect.READ,
    "get_syllabus": Effect.READ,
    "get_unread_count": Effect.READ,
    "identify_problematic_peer_reviews": Effect.READ,
    "list_announcements": Effect.READ,
    "list_assignments": Effect.READ,
    "list_code_api_modules": Effect.READ,
    "list_conversations": Effect.READ,
    "list_course_files": Effect.READ,
    "list_courses": Effect.READ,
    "list_discussion_entries": Effect.READ,
    "list_discussion_topics": Effect.READ,
    "list_group_discussion_topics": Effect.READ,
    "list_group_files": Effect.READ,
    "list_groups": Effect.READ,
    "list_module_items": Effect.READ,
    "list_modules": Effect.READ,
    "list_my_announcements": Effect.READ,
    "list_my_groups": Effect.READ,
    "list_pages": Effect.READ,
    "list_peer_reviews": Effect.READ,
    "list_quizzes": Effect.READ,
    "list_rubrics": Effect.READ,
    "list_submissions": Effect.READ,
    "list_users": Effect.READ,
    "parse_ufixit_violations": Effect.READ,
    "read_course_file": Effect.READ,
    "scan_course_content_accessibility": Effect.READ,
    "search_canvas_tools": Effect.READ,
    # --- CANVAS_WRITE (41) ---
    "add_module_item": Effect.CANVAS_WRITE,
    "assign_peer_review": Effect.CANVAS_WRITE,
    "associate_rubric": Effect.CANVAS_WRITE,
    "bulk_delete_announcements": Effect.CANVAS_WRITE,
    "bulk_grade_submissions": Effect.CANVAS_WRITE,
    "bulk_update_pages": Effect.CANVAS_WRITE,
    "comment_on_my_submission": Effect.CANVAS_WRITE,
    "create_announcement": Effect.CANVAS_WRITE,
    "create_assignment": Effect.CANVAS_WRITE,
    "create_content_migration": Effect.CANVAS_WRITE,
    "create_discussion_topic": Effect.CANVAS_WRITE,
    "create_module": Effect.CANVAS_WRITE,
    "create_page": Effect.CANVAS_WRITE,
    "create_rubric": Effect.CANVAS_WRITE,
    "create_rubric_from_csv": Effect.CANVAS_WRITE,
    "delete_announcement_with_confirmation": Effect.CANVAS_WRITE,
    "delete_announcements_by_criteria": Effect.CANVAS_WRITE,
    "delete_assignment_with_confirmation": Effect.CANVAS_WRITE,
    "delete_module": Effect.CANVAS_WRITE,
    "delete_module_item": Effect.CANVAS_WRITE,
    "delete_page": Effect.CANVAS_WRITE,
    "edit_page_content": Effect.CANVAS_WRITE,
    "fix_accessibility_issues": Effect.CANVAS_WRITE,
    "grade_with_rubric": Effect.CANVAS_WRITE,
    "mark_conversations_read": Effect.CANVAS_WRITE,
    "mark_module_item_done": Effect.CANVAS_WRITE,
    "post_discussion_entry": Effect.CANVAS_WRITE,
    "reply_to_discussion_entry": Effect.CANVAS_WRITE,
    "send_bulk_messages_from_list": Effect.CANVAS_WRITE,
    "send_conversation": Effect.CANVAS_WRITE,
    "send_peer_review_followup_campaign": Effect.CANVAS_WRITE,
    "send_peer_review_inbox_messages": Effect.CANVAS_WRITE,
    "submit_assignment": Effect.CANVAS_WRITE,
    "update_assignment": Effect.CANVAS_WRITE,
    "update_discussion_topic": Effect.CANVAS_WRITE,
    "update_module": Effect.CANVAS_WRITE,
    "update_module_item": Effect.CANVAS_WRITE,
    "update_page_settings": Effect.CANVAS_WRITE,
    "update_rubric": Effect.CANVAS_WRITE,
    "update_syllabus": Effect.CANVAS_WRITE,
    "upload_course_file": Effect.CANVAS_WRITE,
    # --- LOCAL_WRITE (4) ---
    "create_student_anonymization_map": Effect.LOCAL_WRITE,
    "download_course_file": Effect.LOCAL_WRITE,
    "extract_peer_review_dataset": Effect.LOCAL_WRITE,
    "generate_peer_review_report": Effect.LOCAL_WRITE,
    # --- CODE_EXEC (1) ---
    "execute_typescript": Effect.CODE_EXEC,
}

SIDE_EFFECT_TOOLS = frozenset(
    name for name, effect in TOOL_EFFECTS.items() if effect is not Effect.READ
)
_ALL_KEYWORD_TOOLS = frozenset(
    name
    for name, effect in TOOL_EFFECTS.items()
    if effect in (Effect.CANVAS_WRITE, Effect.LOCAL_WRITE)
)


class ToolPolicyError(ValueError):
    """ALLOWED_WRITE_TOOLS cannot be interpreted; the server must not start."""


@dataclass(frozen=True)
class ToolPolicy:
    """The resolved policy for this process.

    ``enforced`` False means no side-effect tool is removed (the stdio default).
    """

    enforced: bool
    allowed: frozenset[str]
    source: str


def resolve_tool_policy(raw: str | None, transport: Transport) -> ToolPolicy:
    """Turn the ALLOWED_WRITE_TOOLS value into a policy, or refuse clearly.

    Raises:
        ToolPolicyError: unknown tool names, read tools named as if they needed
            allowing, or ``none`` combined with anything else.
    """
    if raw is None:
        if transport == "http":
            return ToolPolicy(True, frozenset(), "default for the HTTP transport (read-only)")
        return ToolPolicy(False, SIDE_EFFECT_TOOLS, "default for the stdio transport")

    names = {part.strip() for part in raw.replace(",", " ").split() if part.strip()}
    if not names:
        # Set but empty is NOT the same as unset. A generated allowlist that
        # became empty must fail closed, not restore unrestricted stdio access.
        return ToolPolicy(True, frozenset(), f"{ALLOWLIST_ENV} set but empty (treated as none)")

    keywords = {name for name in names if name.lower() in ("none", "all")}
    requested = names - keywords
    lowered = {name.lower() for name in keywords}

    if "none" in lowered:
        others = {name for name in names if name.lower() != "none"}
        if others:
            raise ToolPolicyError(
                f"{ALLOWLIST_ENV}: 'none' cannot be combined with other entries "
                f"(got: {', '.join(sorted(names))})"
            )
        return ToolPolicy(True, frozenset(), f"{ALLOWLIST_ENV}=none")

    unknown = requested - TOOL_EFFECTS.keys()
    if unknown:
        raise ToolPolicyError(
            f"{ALLOWLIST_ENV} names unknown tools: {', '.join(sorted(unknown))}"
        )
    reads = {name for name in requested if TOOL_EFFECTS[name] is Effect.READ}
    if reads:
        raise ToolPolicyError(
            f"{ALLOWLIST_ENV} lists read-only tools, which are always available: "
            f"{', '.join(sorted(reads))}. List only tools that change something."
        )

    allowed = set(requested)
    if "all" in lowered:
        allowed |= _ALL_KEYWORD_TOOLS
    return ToolPolicy(True, frozenset(allowed), ALLOWLIST_ENV)


async def apply_tool_policy(mcp: FastMCP, policy: ToolPolicy) -> list[str]:
    """Remove every side-effect tool the policy does not allow.

    A registered tool missing from TOOL_EFFECTS is treated as a side effect and
    removed (fail closed); the completeness test keeps that from happening in a
    release. Returns the removed tool names, sorted.
    """
    if not policy.enforced:
        return []
    removed = []
    for tool in await mcp.list_tools(run_middleware=False):
        if TOOL_EFFECTS.get(tool.name) is Effect.READ:
            continue
        if tool.name in policy.allowed:
            continue
        mcp.local_provider.remove_tool(tool.name)
        removed.append(tool.name)
    return sorted(removed)

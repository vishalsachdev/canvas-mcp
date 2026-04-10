# Role-Based Tool Filtering

**Date:** 2026-04-08
**Status:** Draft
**Author:** Chris dePaola (Promithius-DR)

## Problem

Canvas MCP registers all 91 tools for every user regardless of their Canvas role. Students see 53 educator-only tools they can never use (grading, rubric management, analytics, announcements). Educators see 5 student-specific tools ("my grades", "my submissions") that aren't relevant to them. This creates unnecessary token overhead for LLMs and makes it harder for users to manage tools in their MCP client settings.

## Solution

Add a `CANVAS_ROLE` configuration option that controls which tools are registered at startup. Only tools relevant to the selected role are exposed to the MCP client. Tools outside the role are never registered — they don't appear in the client, don't consume tokens, and can't be invoked.

## Roles

| Role | Description | Tool count |
|------|-------------|------------|
| `student` | Student-specific + shared read/post tools | 31 |
| `educator` | Everything except student-specific tools | 86 |
| `all` | All tools (default, backwards compatible) | 91 |

## Configuration

### Env var (`.env`)

```
CANVAS_ROLE=student
```

### CLI flag

```
canvas-mcp-server --role student
```

**Precedence:** CLI flag > env var > default (`all`).

**Validation:** `validate_config()` warns if `CANVAS_ROLE` is set to an unrecognized value and falls back to `all`.

## Tool Categorization

### Student role (29 tools)

Student-specific self-endpoints:
- `get_my_upcoming_assignments`
- `get_my_submission_status`
- `get_my_course_grades`
- `get_my_todo_items`
- `get_my_peer_reviews_todo`

Shared course tools:
- `list_courses`
- `get_course_details`
- `get_course_content_overview`

Shared assignment tools (read-only):
- `list_assignments`
- `get_assignment_details`

Shared discussion tools (read + post):
- `list_discussion_topics`
- `get_discussion_topic_details`
- `list_discussion_entries`
- `get_discussion_entry_details`
- `get_discussion_with_replies`
- `post_discussion_entry`
- `reply_to_discussion_entry`

Shared module tools (read-only):
- `list_modules`
- `get_course_structure`

Shared page tools (read-only, moved from other_tools.py):
- `list_pages`
- `get_page_content`
- `get_page_details`
- `get_front_page`
- `list_module_items`

Shared file tools (read-only):
- `list_course_files`
- `download_course_file`

Shared messaging tools (own conversations):
- `list_conversations`
- `get_conversation_details`
- `get_unread_count`
- `mark_conversations_read`

Tool discovery:
- `search_canvas_tools`

### Educator role (86 tools)

All tools except the 5 student-specific self-endpoints. Educators use the Canvas UI or direct API for their own data — the `get_my_*` tools are designed for student self-service workflows.

### All role (91 tools)

Every tool registered. Default behavior. Fully backwards compatible.

## Categorization Rationale

The categorization follows Canvas LMS API permissions:

- **Student-accessible endpoints** use `/users/self` or return only published/visible content. Students can read published assignments, discussions, modules, pages, and files. They can post to discussions, submit assignments, and manage their own conversations.
- **Educator-only endpoints** require permissions like `manage_assignments_add`, `manage_grades`, `moderate_forum`, `manage_rubrics`, `manage_course_content_*`, `manage_wiki_*`, `manage_files_add`. These return 403 when called with a student token.
- **Shared endpoints** work for both roles, potentially with different visibility (students see published content only, educators see all including drafts).

## File Changes

### Modified files

| File | Change |
|------|--------|
| `core/config.py` | Add `canvas_role` property |
| `server.py` | Add `--role` CLI arg, pass role to `register_all_tools()`, conditional registration |
| `tools/__init__.py` | Update exports for new/split registration functions |
| `tools/assignments.py` | Split into `register_shared_assignment_tools()` + `register_educator_assignment_tools()` |
| `tools/discussions.py` | Split into `register_shared_discussion_tools()` + `register_educator_discussion_tools()` |
| `tools/modules.py` | Split into `register_shared_module_tools()` + `register_educator_module_tools()` |
| `tools/files.py` | Split into `register_shared_file_tools()` + `register_educator_file_tools()` |
| `tools/messaging.py` | Split into `register_shared_messaging_tools()` + `register_educator_messaging_tools()` |
| `tools/pages.py` | Receives `create_page`, `edit_page_content`, `delete_page` from other_tools.py |
| `tools/courses.py` | Receives `list_pages`, `get_page_content`, `get_page_details`, `get_front_page`, `list_module_items` from other_tools.py |

### New files

| File | Contents |
|------|----------|
| `tools/admin_tools.py` | `list_groups`, `list_users`, `get_student_analytics`, `get_anonymization_status`, `create_student_anonymization_map` |

### Deleted files

| File | Reason |
|------|--------|
| `tools/other_tools.py` | All 13 tools moved to proper category files |

### Test updates

- Update import paths in any test referencing `other_tools`
- New tests for role filtering: verify student gets 31 tools, educator gets 86, all gets 91
- Verify no tool is accidentally dropped (union of student + educator-only = all)

### Doc updates

- `tools/TOOL_MANIFEST.json` — update categories to match complete 91-tool mapping
- `AGENTS.md` — document `CANVAS_ROLE` / `--role`
- `env.template` — add `CANVAS_ROLE` with comment

### Not touched

- `README.md` (per CLAUDE.md: update on major releases only)

## Implementation Approach

**Conditional registration (Approach B).** Each tool module exports one or two registration functions. `register_all_tools()` checks the role and calls only the relevant functions. No dependency on FastMCP-specific features like `tags` or `disable()`.

For modules that contain both shared and educator-only tools (`assignments.py`, `discussions.py`, `modules.py`, `files.py`, `messaging.py`), the registration function is split into two: a shared function (called for both student and educator roles) and an educator function (called only for educator and all roles). Tools stay in the same file, grouped by domain.

```python
def register_all_tools(mcp: FastMCP, role: str = "all") -> None:
    # Always registered (shared)
    register_course_tools(mcp)
    register_shared_assignment_tools(mcp)
    register_shared_discussion_tools(mcp)
    register_shared_module_tools(mcp)
    register_shared_file_tools(mcp)
    register_shared_messaging_tools(mcp)
    register_discovery_tools(mcp)

    # Student-specific
    if role in ("student", "all"):
        register_student_tools(mcp)

    # Educator-specific
    if role in ("educator", "all"):
        register_educator_assignment_tools(mcp)
        register_educator_discussion_tools(mcp)
        register_educator_module_tools(mcp)
        register_educator_file_tools(mcp)
        register_page_tools(mcp)
        register_rubric_tools(mcp)
        register_peer_review_tools(mcp)
        register_peer_review_comment_tools(mcp)
        register_educator_messaging_tools(mcp)
        register_accessibility_tools(mcp)
        register_code_execution_tools(mcp)
        register_admin_tools(mcp)

    # Always last
    register_resources_and_prompts(mcp)
```

## Backwards Compatibility

- Default role is `all` — no config change needed for existing users
- No tools are renamed or have their signatures changed
- No changes to the Canvas API client or core utilities
- Existing MCP client configs work unchanged

# Architecture & Key Components

> Design reference extracted from CLAUDE.md.

## Architecture Overview

### Core Design Patterns
- **FastMCP framework**: Built on FastMCP for robust MCP server implementation with proper tool registration
- **Type-driven validation**: All MCP tools use `@validate_params` decorator with sophisticated Union/Optional type handling
- **Dual-layer caching**: Bidirectional course code ↔ ID mapping via `course_code_to_id_cache` and `id_to_course_code_cache`
- **Flexible identifiers**: Support for Canvas IDs, course codes, and SIS IDs through `get_course_id()` abstraction
- **ISO 8601 standardization**: All dates converted via `format_date()` and `parse_date()` functions

### MCP Tool Organization
- **Progressive disclosure**: List → Details → Content → Analytics pattern
- **Functional grouping**: Tools organized by Canvas entity (courses, assignments, discussions, messaging, etc.)
- **Consistent naming**: `{action}_{entity}[_{specifier}]` pattern
- **Educational analytics focus**: Student performance, completion rates, missing work identification
- **Discussion workflow**: Browse → View → Read → Reply pattern for student interaction
- **Messaging workflow**: Analytics → Target → Template → Send pattern for automated communications

### API Layer Architecture
- **Centralized requests**: All Canvas API calls go through `make_canvas_request()`
- **Form data support**: Messaging endpoints use `use_form_data=True` for Canvas compatibility
- **Automatic pagination**: `fetch_all_paginated_results()` handles Canvas pagination transparently
- **Async throughout**: All I/O operations use async/await
- **Graceful error handling**: Returns JSON error responses rather than raising exceptions
- **Privacy protection**: Student data anonymization via configurable `anonymize_response_data()`

## Key Components

### Tool Annotations (MCP hints)

Every `@mcp.tool()` must declare what it does to the world. `tests/test_tool_metadata.py`
enforces this: a tool is read-only, or it answers **both** write questions. A bare
`@mcp.tool()` fails CI — which is how [#200](https://github.com/vishalsachdev/canvas-mcp/issues/200)
reached a user in the first place.

The gate enumerates the **live registry with every feature gate switched on**
(`EXECUTE_TYPESCRIPT_ENABLED`, `STUDENT_WRITE_TOOLS`), because coverage has to follow
capability rather than default configuration. Checking only the default set would
have passed while `execute_typescript` — arbitrary TypeScript against the caller's
Canvas token — shipped with no annotations at all. A separate test asserts those
tools really are present, so the fixture cannot silently stop working and shrink
what the gate covers.

| Hint | Set when |
|------|----------|
| `readOnlyHint=True` | The tool performs no writes. Nothing else needs setting. |
| `destructiveHint` | **`False` means "performs only additive updates"** — the MCP spec's wording, not "doesn't delete". |
| `idempotentHint` | `True` when repeating the call with the same arguments has no additional effect. |

**`destructiveHint` follows the spec, not a local convention** ([#204](https://github.com/vishalsachdev/canvas-mcp/issues/204)).
The convention had been "destructive == deletes", which left `bulk_grade_submissions`
and `edit_page_content` claiming to be additive-only while they overwrite grades and
page bodies. A client has no way to know the server meant something narrower, so the
tools that *replace* data are marked destructive even though they delete nothing:

- **Destructive**: `bulk_grade_submissions`, `grade_with_rubric`, `edit_page_content`,
  `bulk_update_pages`, `fix_accessibility_issues`, all `update_*`, `upload_course_file`
  (`on_duplicate="overwrite"`), `create_student_anonymization_map` (rewrites its local
  CSV), `execute_typescript`, and every `delete_*`.
- **Additive**: `create_announcement`, `create_assignment`, `create_discussion_topic`,
  `create_module`, `create_rubric_from_csv`, `post_*`/`reply_*`, `send_*`,
  `add_module_item`, `assign_peer_review`, `mark_conversations_read`.

**The `create_` prefix is not a safe guide.** Three creators displace existing state
through an option and are therefore destructive: `create_page` with `front_page=True`
unseats the course's current front page (Canvas allows exactly one), and both
`create_rubric` with an `assignment_id` and `associate_rubric` attach a rubric over
whatever was already associated — the latter also overwriting `use_for_grading` and
`purpose` even when re-associating the same rubric. Classify by what the call *does*
to existing state, never by the verb in its name.

`mark_conversations_read` is a deliberate, documented exception. It replaces a read
flag, so a strict reading would call it destructive — but nothing user-authored is
lost, the prior state is restorable through the same API, and marking an inbox read
is the archetypal benign toggle. Over-flagging costs real signal: a client that
prompts for everything trains users to click through the prompts that matter. Revisit
if a client ever surfaces these hints differently.

Idempotency is a separate axis, and it is judged on the tool's **whole effect, not
just its primary resource**. A tool is non-idempotent if *any* supported input makes
a repeat produce an additional external effect — the hint is per-tool, and a host
retrying a timed-out call cannot know which arguments were used. Concretely:

- `update_*`, most `delete_*` and `edit_page_content` converge on the same end state → idempotent.
- `delete_announcements_by_criteria` is the exception among deletes: it re-queries by
  criteria and slices `matched[:limit]`, so an identical retry deletes the **next**
  batch, up to twice the requested limit. Its sibling `bulk_delete_announcements`
  takes explicit ids (its `limit` is only a refusal threshold) and stays idempotent.
  The lesson generalises: a tool that **re-derives its target set at call time** is
  rarely idempotent, however idempotent the underlying operation looks.
- Anything that creates a record does not — including `upload_course_file`, whose
  default `on_duplicate="rename"` writes a new file every call.
- `bulk_grade_submissions` and `grade_with_rubric` settle on the same *score*, but
  append a **new submission comment** whenever `comment` is supplied → **not** idempotent.
- `update_page_settings` and `bulk_update_pages` settle on the same *body*, but
  re-notify the whole course whenever `notify_of_update=True` → **not** idempotent.
  (`edit_page_content` does not expose that option, which is why it differs from its
  two siblings.)

A retry that silently duplicates feedback to every student in a course, or notifies
a class twice, is exactly the harm this hint exists to prevent.

### Parameter Validation System
- `validate_parameter()`: Runtime type coercion supporting complex types
- `@validate_params`: Automatic validation decorator for all MCP tools
- Handles Union types, Optional types, string→JSON conversion, comma-separated lists

### Course Identifier Handling
- `get_course_id()`: Converts any identifier type to Canvas ID
- `get_course_code()`: Reverse lookup from ID to human-readable code
- `refresh_course_cache()`: Rebuilds identifier mapping from Canvas API

### Analytics Engine
- `get_student_analytics()`: Multi-dimensional educational data analysis
- `get_assignment_analytics()`: Statistical performance analysis with grade distribution
- `get_peer_review_completion_analytics()`: Peer review tracking and completion analysis
- `get_peer_review_comments()`: Extract actual peer review comment text and analysis
- `analyze_peer_review_quality()`: Comprehensive comment quality analysis with metrics
- `identify_problematic_peer_reviews()`: Automated flagging of low-quality reviews
- Temporal filtering (current vs. all assignments)
- Risk identification and performance categorization

### Messaging System
- `send_conversation()`: Core Canvas messaging with form data support
- `send_peer_review_reminders()`: Automated peer review reminder workflow
- `send_peer_review_followup_campaign()`: Complete analytics → messaging pipeline
- `MessageTemplates`: Flexible template system for various communication types
- Privacy-aware: Works with anonymization while preserving functional user IDs

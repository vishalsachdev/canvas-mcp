# Destructive Operation Guards

**Date:** 2026-04-25
**Status:** Approved
**Scope:** Lightweight

## Problem

The Canvas MCP server has 13 tools that perform DELETE operations against the Canvas API, plus 3 additional operations that use HTTP DELETE internally (enrollment lifecycle, group membership). A misunderstood agent command could accidentally delete course modules, pages, assignments, or other critical content. 8 of these delete tools have **zero built-in safeguards** — no dry-run, no confirmation, no title matching.

Since all Canvas API operations flow through a single function (`make_canvas_request()`), a centralized guard can protect against accidental deletion without modifying each tool individually.

## Requirements

### R1: Delete Guard (Hard Block)

- Add `CANVAS_ALLOW_DELETES` boolean env var to the config system
- **Default: `true`** (deletes enabled) for backward compatibility
- When set to `false`, **all** `make_canvas_request(method="delete", ...)` calls are blocked before reaching Canvas — including enrollment lifecycle operations (`conclude_enrollment`, `deactivate_enrollment`) and group membership changes that use HTTP DELETE internally
- Blocked requests return a clear, actionable error message (not a crash):
  - What was blocked (which endpoint)
  - Why (the env var setting)
  - How to enable deletes (set `CANVAS_ALLOW_DELETES=true` in `.env`)
- Guard lives at the `make_canvas_request()` chokepoint so it automatically covers all current and future delete tools
- Log blocked delete attempts at WARNING level for audit trail
- Use case-insensitive method comparison (`.lower()`) consistent with existing client code

### R2: Overwrite Awareness (Soft Guard)

- Not a hard block — agents using this MCP should confirm with the user before overwriting existing content (updates/PUTs), but the MCP server itself does not block these
- Ensure delete tools' docstrings and error messages clearly state that the operation is destructive and permanent
- No code changes required for this — it's a convention enforced by the calling agent's interaction loop (e.g., Claude Code already prompts before destructive actions)

## Non-Goals

- Full read-only mode (blocking all writes) — not needed currently
- Per-tool granular delete permissions (e.g., allow page deletes but not module deletes)
- Confirmation prompts within the MCP server itself (that's the calling agent's responsibility)
- Exempting specific DELETE operations (enrollment, membership) from the guard — keep it uniform and simple

## Affected Components

- `src/canvas_mcp/core/config.py` — Add `CANVAS_ALLOW_DELETES` config field (uses existing `_bool_env()` helper)
- `src/canvas_mcp/core/client.py` — Add guard in `make_canvas_request()` before DELETE execution (~5 lines)
- `.env` / documentation — Document the new env var

## Affected Tools (auto-protected by the guard)

| Tool | File | Existing Safety |
|------|------|-----------------|
| `delete_assignment` | `tools/assignments.py` | dry_run=True default |
| `delete_module` | `tools/modules.py` | None |
| `delete_module_item` | `tools/modules.py` | None |
| `delete_page` | `tools/other_tools.py` | Optional title match |
| `delete_discussion_entry` | `tools/discussions.py` | None |
| `delete_discussion_topic` | `tools/discussions.py` | Type guard (rejects announcements) |
| `delete_announcement` | `tools/discussions.py` | None |
| `bulk_delete_announcements` | `tools/discussions.py` | None |
| `delete_announcement_with_confirmation` | `tools/discussions.py` | dry_run + title match |
| `delete_announcements_by_criteria` | `tools/discussions.py` | dry_run=True default |
| `delete_group` | `tools/groups.py` | None |
| `delete_rubric` | `tools/rubrics.py` | None |
| `delete_file` | `tools/files.py` | None |
| `conclude_enrollment` | `tools/enrollments.py` | Uses HTTP DELETE internally |
| `deactivate_enrollment` | `tools/enrollments.py` | Uses HTTP DELETE internally |
| `update_group_members` | `tools/groups.py` | Uses HTTP DELETE internally |

## Success Criteria

- Setting `CANVAS_ALLOW_DELETES=false` blocks all DELETE HTTP requests to Canvas
- Blocked attempts return a helpful error message (not an exception)
- Blocked attempts are logged at WARNING level
- Existing behavior unchanged when env var is not set or set to `true`
- Future delete tools are automatically covered without any extra work

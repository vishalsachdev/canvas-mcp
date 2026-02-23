# Session History

Archived session log entries from canvas-mcp CLAUDE.md.

## Session Log

### 2026-01-25
- Added `update_assignment` tool:
  - PUT /api/v1/courses/:course_id/assignments/:id
  - Parameters: course_identifier, assignment_id, name, description, submission_types, due_at, unlock_at, lock_at, points_possible, grading_type, published, assignment_group_id, peer_reviews, automatic_peer_reviews, allowed_extensions
  - All update fields optional (only changed fields sent to API)
  - 9 unit tests following TDD pattern
  - Updated TODO.md (moved to Completed)
- Tool follows existing patterns from `create_assignment`

### 2026-01-21
- Fixed broken rubric API tools:
  - Disabled `create_rubric` (Canvas API returns 500 error - known bug)
  - Disabled `update_rubric` (API does full replacement, causes data loss)
  - Both tools now return informative error messages with workarounds
  - Added "Known Canvas API Limitations" section to AGENTS.md
  - Updated README.md and tools/README.md with limitations
- Pushed: `c01dc7d` fix: Disable broken rubric API tools (create_rubric, update_rubric)

### 2026-01-20
- Updated README documentation:
  - Corrected tool count from 50+ to 80+ (actual: 84 tools)
  - Updated test count from 51 to 167 tests
  - Reorganized tool sections by Canvas permissions
  - Moved module/page management tools to Educator Tools
  - Kept only read-only tools in Shared Tools section
  - Added example prompts for new educator tools
- Pushed: `85c9fef` docs: Update README with accurate tool count

### 2026-01-18
- Completed: Module tools feature branch (`feature/module-creation-tool`)
  - 7 MCP tools for Canvas module management
  - 36 unit tests
  - Full documentation in tools/README.md and AGENTS.md
- Completed: Page settings tools (`feature/page-settings-tools`)
  - `update_page_settings` - publish/unpublish, front page, editing roles
  - `bulk_update_pages` - batch operations on multiple pages
  - 15 unit tests (TDD approach)
  - Added TDD enforcement section to CLAUDE.md
  - Created GitHub issue #56 for comprehensive test coverage
- Released: v1.0.6 with 9 new tools

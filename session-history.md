# Session History

Archived session log entries from canvas-mcp CLAUDE.md.

## Session Log

### 2026-02-20
- **CI cleanup**: Removed auto-update README step from `create-release.yml` (~160 lines deleted)
  - The step created orphaned branches (e.g., `auto-update-readme-v1.0.8`) when branch protection blocked direct pushes
  - README is already updated manually during release prep — automation was redundant
  - Also removed `pull-requests: write` permission (no longer needed)
- **Branch cleanup**: Deleted orphaned remote branch `auto-update-readme-v1.0.8`

### 2026-02-16
- **Security Hardening (v1.0.8)**:
  - Implemented 4 security features via PR #74 (`feature/security-hardening`):
    - PII sanitization in logs (`LOG_REDACT_PII=true` default)
    - Token validation on startup (warns but doesn't block)
    - Structured JSON audit logging (`LOG_ACCESS_EVENTS`, `LOG_EXECUTION_EVENTS`)
    - Sandbox hardening — secure-by-default (sandbox ON, network blocked, CPU/memory limits)
  - Codex CLI review caught 3 issues: raw error payloads in audit logs, stderr in code execution audit, missing Docker env vars — all fixed
  - 235+ tests (up from 167)
- **CodeQL Alert Remediation**:
  - Resolved all 31 open alerts: 9 dismissed (archive), 4 false positives, 3 intentional patterns, 15 fixed in source/tests
  - Codex CLI handled 12 test file cleanups automatically
- **Ruff Linting Enforcement**:
  - Fixed 464 lint issues across codebase (443 auto, 21 manual)
  - Added `.git/hooks/pre-commit` running ruff on staged files
  - Updated `~/.claude/AGENTS.md` with linting setup template for all Python repos
- **Release v1.0.8**:
  - Bumped version across `pyproject.toml`, `__init__.py`, `docs/index.html`, `server.json`
  - Fixed server.json version (was stuck at 1.0.6 — caused MCP Registry "duplicate version" error)
  - Added `workflow_dispatch` to `publish-mcp.yml` for manual re-triggers
  - Made README auto-update non-blocking in `create-release.yml` with summary step
  - All workflows passing: PyPI, MCP Registry, GitHub Release, GitHub Pages
  - Added `server.json` and `__init__.py` to release checklist in CLAUDE.md
- **Cleanup**: Removed `Build AI Product Sense/` and `smithery-wrapper/` from repo
- **Tooling**: Created `/codex-review` skill for cross-checking changes with OpenAI Codex CLI
- **Decision**: Smithery publishing dropped from backlog (wrapper removed, marketplace access blocked)

### 2026-02-01
- **Smithery Publishing Attempt** (blocked):
  - Goal: Publish canvas-mcp to Smithery marketplace for additional distribution
  - **Findings**:
    - Smithery has 3 publishing options: URL (HTTP), Hosted, Local (stdio)
    - **URL option**: Requires Streamable HTTP transport (canvas-mcp uses stdio)
    - **Hosted option**: "Private Early Access" - not publicly available
    - **Local option**: CLI expects server entry to exist first; can't create new servers via CLI
    - Web UI only exposes URL option; no way to create Hosted/Local servers
  - **What we built**: TypeScript wrapper at `smithery-wrapper/` with 10 core tools
    - Native TS Canvas MCP using `@modelcontextprotocol/sdk`
    - Builds successfully with `smithery build`
    - Ready for future deployment if Smithery opens up access
  - **Decision**: Skip Smithery → focus on MCP Registry + PyPI (already published)
  - `smithery-wrapper/` removed in 2026-02-16 session (unused prototype)

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

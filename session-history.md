# Session History

Archived session log entries from canvas-mcp CLAUDE.md.

## Session Log

### 2026-03-05
- **Cloudflare Web Analytics**: Added beacon to educator, student, and bulk-grading guide pages (all 5 docs/ HTML pages now covered)
- **Cloudflare Pages auto-deploy**: Investigated connecting GitHub repo — not possible for Direct Upload projects. Manual deploy via `wrangler pages deploy` for now.

### 2026-03-04
- **Cloudflare Pages migration**: Moved site from GitHub Pages (blocked by disabled Actions) to Cloudflare Pages
  - Created Cloudflare Pages project, deployed `docs/` via `wrangler pages deploy`
  - Added `canvas-mcp.illinihunt.org` custom domain, updated DNS CNAME from `github.io` → `pages.dev` (proxied)
  - Created Workers route bypass for `canvas-mcp.*` (wildcard Worker was intercepting traffic)
  - Disabled GitHub Pages via API, deleted `docs/CNAME`
  - Auto-deploy not yet connected (manual `wrangler pages deploy` for now)
- **Learning Designer guide page**: Created `docs/learning-designer-guide.html`
  - Full guide with tools, AI skills (QC, accessibility, builder), workflows, and installation
  - Updated homepage LD card link from GitHub AGENTS.md to local guide page
  - Added "Designers" nav link to all guide pages (student, educator, bulk-grading)
- **HTTP transport & hosted deployment**: Implemented per-request credential system for multi-tenant hosting
  - New `core/credentials.py`: ContextVar-based per-request credential threading
  - Modified `core/client.py`: Per-request httpx client when ContextVar is set, falls back to global for stdio
  - Modified `server.py`: ASGI middleware extracts X-Canvas-Token/X-Canvas-URL headers, CLI args for transport/host/port
  - Deployed to VPS (76.13.122.44): systemd service, nginx reverse proxy with SSL, Cloudflare DNS + Workers route bypass
  - Live at `https://mcp.illinihunt.org/mcp` — verified MCP initialize handshake working
  - Added `tests/test_http_transport.py` (12 tests: ContextVar, middleware, client integration, CLI args)
  - Updated README (Use Without Installing section), AGENTS.md (remote auth), docs/index.html (hosted quickstart)
- **MCP token optimization**: Trimmed tool docstrings across all 91 tools (15 files) for ~35% token reduction
  - Removed Example Usage blocks (biggest savings: rubrics.py, code_execution.py, discussions.py)
  - Removed Returns/Raises sections from all MCP tool docstrings
  - Compressed Args descriptions to one-liners (e.g., `course_identifier` pattern)
  - Preserved first-line summaries and IMPORTANT behavioral notes
  - Net: -688 lines, +337 lines (351 lines removed). All 275 tests pass.
- **GitHub Pages audit**: Cross-referenced docs/index.html against codebase, found 7 disconnects
  - Updated tool count 80+ → 90+ (actual: 91) across 6 places in index.html + 3 in README
  - Added Cloudflare Web Analytics beacon (was missing per global CLAUDE.md rule)
  - Updated test count 235+ → 290+ (actual: 294) in README current text
  - Fixed server.json websiteUrl to match canonical domain (canvas-mcp.illinihunt.org)
  - Added ChatGPT to Compatibility grid (was in hero text but missing from grid)
  - Added file management mention to Educator persona card
  - Added parse_ufixit_violations to README LD tools table (synced with AGENTS.md)
- **CLAUDE.md audit**: Scored 68/100 → improved to ~85/100 (384 → 263 lines)
  - Fixed 3 bugs: AGENTS.md link, test mock path (`src.` prefix), test command
  - Updated repo tree (added skills/, tests/, tools/ dirs)
  - Removed 3 workflow sections duplicating AGENTS.md
  - Condensed Documentation Maintenance (50 → 8 lines)
  - Archived Feb 1/16/20 session logs to session-history.md

### 2026-03-03
- **skills.sh discovery debugging**: Investigated why `npx skills find canvas-mcp` returned no results
  - Root cause 1: CLI package is `skills` not `skills.sh` (`npx skills.sh` → 404)
  - Root cause 2: `find` searches the online leaderboard (populated by install telemetry), not GitHub repos
  - `npx skills add vishalsachdev/canvas-mcp` works perfectly — detects all 7 skills from repo
- **Self-installed skills globally**: `npx skills add vishalsachdev/canvas-mcp -g -y` to seed first telemetry event
  - Installed to 7 agents: Claude Code, Codex, Cursor, Windsurf, Gemini CLI, Antigravity, OpenCode
  - Removed duplicate `morning-check`/`week-plan` (non-prefixed copies from `.claude/skills/`)
- **README hero update**: Moved `npx skills add` command above the fold, added skills.sh badge, updated Publishing section
- **Version sync**: Updated server.json and docs/index.html from v1.0.8 → v1.1.0 (were missed during Feb 28 bump)
- **Learning Designer features**: Brainstormed, designed, and implemented full LD toolset
  - New MCP tool: `get_course_structure` (full module→items tree + summary stats, 5 tests)
  - 3 new skills: `canvas-course-qc`, `canvas-accessibility-auditor`, `canvas-course-builder`
  - Skills available via skills.sh (40+ agents) and Claude Code slash commands
  - Updated AGENTS.md, README.md, tools/README.md, docs/index.html (new LD persona card + 3 skill cards)
  - Codex review: clean (0 issues)
- **Live QC test on BADM 350 (Spring 2026)**: Ran canvas-course-qc workflow end-to-end
  - Fixed: GenAI Module 2 Quiz missing due date (set to Mar 13)
  - Deleted: 2 orphaned duplicate overview pages (Week 2, Week 3)
  - Renamed: 6 participation assignments for naming consistency
  - Added: 3 "Semester Project" subheaders to Weeks 5, 6, 8
  - Investigated: GenAI Fluency nav pages (orphaned, leave unpublished), Yellowdig reminders (Calendar Events don't notify — keep as-is)

### 2026-02-23
- **PR #75 Review & Merge**: Reviewed Samuel Parks' file download/listing tools PR
  - Fixed path traversal vulnerability (sanitize_filename on API-provided filenames)
  - Switched to streaming downloads (aiter_bytes) for large files
  - Added sort/order parameter validation in list_course_files
  - Replaced hardcoded `/tmp` with `tempfile.gettempdir()`
  - Added 17 new tests (50 total file tests), Codex review passed
  - Cherry-picked fix commits onto main after fork-based merge gap
- **Article**: "The Moment Your Side Project Stops Being Yours" — OSS contributor stories
  - Published drafts to Substack, LinkedIn (1,101 subscribers), and X/Twitter
  - Generated 3 cover images (LinkedIn 1200x628, Substack 1100x220, Twitter 1200x675)
- **Skill Updates**: Fixed `/publish-to-substack` and `/publish-to-linkedin` skills
  - Substack: title/subtitle changed from contenteditable divs to `<textarea>` elements
  - Substack: body editor selector changed to `.tiptap.ProseMirror`
  - LinkedIn: title also changed to `<textarea>` — native value setter pattern needed
  - Both skills: updated CSS selectors reference tables and known bugs

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

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Note**: This guide is for developers working ON the Canvas MCP codebase. If you're an AI agent USING the MCP server, see [AGENTS.md](./AGENTS.md) instead.

# Canvas MCP Development Guide

## Environment Setup
- Install uv package manager: `pip install uv`
- Install dependencies: `uv pip install -e .`
- Create `.env` file with `CANVAS_API_TOKEN` and `CANVAS_API_URL`
- Server installed as CLI command: `canvas-mcp-server`

## Commands
- **Start server**: `canvas-mcp-server` (or `./start_canvas_server.sh` for legacy setup)
- **Test server**: `canvas-mcp-server --test`
- **View config**: `canvas-mcp-server --config`
- **MCP client config**: Update your MCP client's configuration file (e.g., `~/Library/Application Support/Claude/claude_desktop_config.json` for Claude Desktop)

## Repository Structure
```
canvas-mcp/
├── src/canvas_mcp/        # Main application code
│   ├── core/             # Core utilities (client, config, validation)
│   ├── tools/            # MCP tool implementations (91 tools across 15 files)
│   ├── resources/        # MCP resources and prompts
│   └── server.py         # FastMCP server entry point
├── skills/               # Agent skills for skills.sh (8 skills)
├── tests/                # 290+ tests (pytest + pytest-asyncio)
├── docs/                 # GitHub Pages site + guides
├── tools/                # Tool documentation (README.md, TOOL_MANIFEST.json)
├── archive/              # Legacy code (git-ignored)
└── .env                  # Configuration (CANVAS_API_TOKEN, CANVAS_API_URL)
```

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

## Git Workflow - ASK FIRST

**Before starting any new feature or significant change, ASK:**
> "Should I create a feature branch for this, or work directly on main?"

| Change Type | Default Branch | Notes |
|-------------|----------------|-------|
| New tool/feature | `feature/tool-name` | PR with CI checks |
| Bug fix | `fix/issue-description` | PR recommended |
| Documentation only | `main` okay | Direct push acceptable |
| Quick fix (typo, etc.) | `main` okay | Direct push acceptable |

**Branch naming:** `feature/`, `fix/`, `docs/`, `refactor/`

This repo has branch protection on `main` (PR + status checks required), but admin can bypass. Always ask the user which workflow they prefer for the current task.

---

## Release Checklist

When bumping the version in `pyproject.toml`, also update:
- [ ] `src/canvas_mcp/__init__.py` - Update `__version__`
- [ ] `server.json` - Update both `version` fields (top-level and packages[0]) for MCP Registry
- [ ] `README.md` - Update "Latest Release" section with new version, date, and changelog
- [ ] `docs/index.html` - Update version badge, tool count, and meta descriptions (GitHub Pages site)
- [ ] Create git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`

---

## Coding Standards
- **Type hints**: Mandatory for all functions, use Union/Optional appropriately
- **MCP tools**: Use `@mcp.tool()` decorator with `@validate_params`
- **Async functions**: All API interactions must be async
- **Course identifiers**: Use `Union[str, int]` and `get_course_id()` for flexibility
- **Date handling**: Use `format_date()` for all date outputs
- **Error responses**: Return JSON strings with "error" key for failures
- **Form data**: Use `use_form_data=True` for Canvas POST/PUT endpoints
- **Privacy**: Student IDs preserved, names anonymized in `_should_anonymize_endpoint()`
- **Optional params**: Use `Optional[T]` type hints for parameters that can be `None`

## Test-Driven Development (TDD) - ENFORCED

**All new MCP tools MUST have tests before the feature is considered complete.**

### TDD Workflow
1. **Write tests first** (or alongside) for new tools
2. **Minimum 3 tests per tool**: success path, error handling, edge case
3. **Run tests** before committing: `uv run python -m pytest tests/ -v`
4. **No merging** without passing tests

### Test Structure
```
tests/
├── tools/           # Unit tests for MCP tools
│   ├── test_modules.py    # Reference implementation
│   ├── test_pages.py      # Page tools tests
│   └── ...
└── security/        # Security-focused tests
```

### Test Patterns (from test_modules.py)
```python
@pytest.fixture
def mock_canvas_request():
    with patch('canvas_mcp.tools.modules.make_canvas_request') as mock:
        yield mock

@pytest.mark.asyncio
async def test_tool_success(mock_canvas_request, mock_course_id):
    mock_canvas_request.return_value = {"id": 123, "name": "Test"}
    result = await tool_function(course_identifier="test", ...)
    assert "success" in result.lower() or "123" in result
```

### What to Test
- ✅ Successful API responses
- ✅ API error handling (404, 401, 500)
- ✅ Parameter validation (missing required params, invalid types)
- ✅ Edge cases (empty lists, None values, special characters)
- ✅ Canvas API quirks (form data requirements, pagination)

See: [Issue #56](https://github.com/vishalsachdev/canvas-mcp/issues/56) for comprehensive test coverage plan.

## Canvas API Specifics
- Base URL from `CANVAS_API_URL` environment variable
- Authentication via Bearer token in `CANVAS_API_TOKEN`
- Always use pagination for list endpoints
- Course codes preferred over IDs in user-facing output
- Handle both published and unpublished content states
- **Messaging requires form data**: Use `use_form_data=True` for `/conversations` endpoints
- **Privacy protection**: Real user IDs preserved for functionality, names anonymized for privacy

## Documentation Maintenance

**Source of truth per audience:**
- **AI agents**: `AGENTS.md` (tool tables, workflows, constraints)
- **Humans**: `tools/README.md` (full tool docs with all params)
- **Machine**: `tools/TOOL_MANIFEST.json`
- **Entry point**: `README.md` (installation, overview — update on major releases only)

**When adding a new tool**, update: `tools/README.md` → `AGENTS.md` → `TOOL_MANIFEST.json`. Do NOT update `README.md` unless it's a major feature. Do NOT duplicate tool usage docs in `CLAUDE.md` (architecture only).

## Current Focus
- [ ] Re-enable GitHub Actions (account-level billing toggle)
- [x] Create v1.1.0 GitHub Release (created manually via `gh release create`)
- [ ] Backlog triage (module templates, bulk creation, page versioning)

## Roadmap
- [x] Release v1.0.8 — all CI/CD pipelines passing (PyPI, MCP Registry, GitHub Release)
- [x] Learning Designer tools & skills — `get_course_structure` tool + 3 skills (QC, accessibility, builder)
- [x] GitHub Pages audit — 7 disconnects fixed (tool count, test count, analytics, URLs, compatibility)
- [x] MCP token optimization — trimmed tool docstrings ~35% (350 lines removed across 15 files)
- [x] HTTP transport & hosted server — per-request credentials via ContextVar, deployed to VPS at mcp.illinihunt.org
- [x] Cloudflare Pages migration — site moved from GitHub Pages (blocked by Actions) to Cloudflare Pages

## Backlog
- [ ] Module templates (pre-configured module structures)
- [ ] Bulk module creation from JSON/YAML specs
- [ ] Module duplication across courses
- [ ] Page templates
- [ ] Bulk page creation from markdown files
- [ ] Page content versioning/history tools

## Session Log
> Full history: [session-history.md](./session-history.md)

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


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
│   ├── tools/            # MCP tool implementations (88 tools across 15 files)
│   ├── resources/        # MCP resources and prompts
│   └── server.py         # FastMCP server entry point
├── skills/               # Agent skills for skills.sh (8 skills)
├── tests/                # 328 tests (pytest + pytest-asyncio)
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
- [x] Release v1.3.0 — `create_rubric` (#100), `read_course_file` (#90), event-loop fix (#99), bulk-delete safety (#96); tool count 88 → 90; CHANGELOG.md added
- [ ] Backlog triage (module templates, bulk creation, page versioning)
- [ ] Follow-up: split publish-mcp.yml into separate PyPI + MCP Registry jobs with PyPI-propagation poll (avoid race retry on next release)
- [ ] Follow-up: add `ruff` to dev deps in pyproject.toml so contributors don't trip pre-commit hook on fresh clone

## Roadmap
- [x] Release v1.0.8 — all CI/CD pipelines passing (PyPI, MCP Registry, GitHub Release)
- [x] Learning Designer tools & skills — `get_course_structure` tool + 3 skills (QC, accessibility, builder)
- [x] GitHub Pages audit — 7 disconnects fixed (tool count, test count, analytics, URLs, compatibility)
- [x] MCP token optimization — trimmed tool docstrings ~35% (350 lines removed across 15 files)
- [x] HTTP transport & hosted server — per-request credentials via ContextVar, deployed to VPS at mcp.illinihunt.org
- [x] Cloudflare Pages migration — site moved from GitHub Pages (blocked by Actions) to Cloudflare Pages
- [x] Release v1.2.0 — role-based filtering, accessibility remediation, security hardening, contributor acknowledgements
- [x] Release v1.3.0 — create_rubric, read_course_file, event-loop fix, bulk-delete safety, CHANGELOG.md

## Backlog
- [x] Impact tracker: automated weekly stats collection + website section
- [ ] Module templates (pre-configured module structures)
- [ ] Bulk module creation from JSON/YAML specs
- [ ] Module duplication across courses
- [ ] Page templates
- [ ] Bulk page creation from markdown files
- [ ] Page content versioning/history tools

## Session Log
> Full history: [docs/session-history.md](./docs/session-history.md)

### 2026-05-02
- **Released v1.3.0** (commits `cff934c` + `c2f1438`, tag `v1.3.0`): Bundled four already-merged PRs into a coherent release — `create_rubric` (#100, bracket-notation form-data finally working), `read_course_file` (#90, @DomBarker99), event-loop fix on user-scoped tools (#99, weakref-tracked client/semaphore), and bulk-delete safety (#96, default cap of 25 + dry_run). Drafted CHANGELOG.md (Keep-a-Changelog format) before bumping versions — that scope-pass caught the bulk-delete behavior change for callers passing >25 IDs and got it into the release notes. Bumped 5 release-checklist files; 382 tests pass at 1.3.0; tool count 88 → 90.
- **CI publish race surfaced**: `publish-mcp.yml` runs PyPI upload + MCP Registry publish in one sequential job. The Registry's PyPI lookup raced PyPI's CDN propagation and 404'd. `gh run rerun --failed` succeeded immediately on retry — no code change. Added a follow-up: split into two jobs with a PyPI-propagation poll between them. Also surfaced a Node 20 deprecation warning for `actions/checkout@v4` + `actions/setup-python@v5` (force-upgraded June 2026).
- **Session prep**: Pulled 3 backlog commits (#96, #99, #100), committed two carry-forward dirty files (`AGENTS.md` policy additions for memory lookup + external-action approval; `impact.json` April 27 stats refresh). Deleted two 66-day-old `.claude/plans/` files whose targets had all shipped. Cloudflare Pages deployed manually with `unset CF_API_TOKEN && wrangler pages deploy` (the documented workaround for the deprecated env var).
- **Pre-commit hook surprise**: Fresh venv didn't have `ruff` installed; hook called `uv run ruff` which spawn-failed with "No such file or directory." Installed via `uv pip install ruff`. Should be a dev dep in pyproject.toml.
- Next: Backlog triage (module templates, bulk creation, page versioning). Address the two follow-ups in Current Focus before the next release.


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
- [ ] `tools/TOOL_MANIFEST.json` - Update `version` field to match new version
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
- [x] Follow-up: split publish-mcp.yml into separate PyPI + MCP Registry jobs with PyPI-propagation poll (PR #107)
- [x] Follow-up: add `ruff`/`black`/`mypy` to dev deps in pyproject.toml; remove unused `requests`; `setup-python@v4 → @v6` (PR #105)
- [x] Retired public hosted server (`mcp.illinihunt.org`) — security teardown + cleaned all references (memory, website, README/AGENTS/CHANGELOG)
- [x] Issue #115: Gies/Azure hosted deployment — **DONE 2026-06-17.** v2 Entra platform-auth (#125) + a private custom domain (bound + managed cert; URL in gitignored `docs/ops-hosted.local.md`) **resolves the `AADSTS9010010` mcp-remote blocker — verified live, all clients work.** App renamed `gies-canvas-mcp` → `canvas-mcp` (house-consistent; old apps deleted). Branch→slot CI added (#128/#129). Remaining polish: tighten `MCP_ENTRA_ALLOWED_OIDS`; AcrPull RBAC fix (needs Adam, still on ACR admin-user creds)
- [~] PR #126: `check_enrollment` capability (core + MCP tool, data-minimizing roster membership for UniQuick) — open. Deferred: REST endpoint + teacher-token-sourcing decision; tool docs
- [ ] Backlog triage (module templates, bulk creation, page versioning)
- [ ] Issue #106: 186 mypy errors uncovered by adding mypy to dev deps — incremental cleanup, module by module

## Roadmap
- [x] Release v1.0.8 — all CI/CD pipelines passing (PyPI, MCP Registry, GitHub Release)
- [x] Learning Designer tools & skills — `get_course_structure` tool + 3 skills (QC, accessibility, builder)
- [x] GitHub Pages audit — 7 disconnects fixed (tool count, test count, analytics, URLs, compatibility)
- [x] MCP token optimization — trimmed tool docstrings ~35% (350 lines removed across 15 files)
- [x] HTTP transport & hosted server — per-request credentials via ContextVar. VPS instance (mcp.illinihunt.org) **decommissioned 2026-06-05** (workshop-only; public code-exec surface); Gies/Azure rebuild tracked in issue #115
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

## Hosted Deployment (Azure — #115)

There is a **private, Entra-gated** hosted instance for Gies course staff. It is **not shared
publicly** — keep its endpoint URL, Entra app IDs, deploy specifics, and access-key holders out
of this (public) repo. All operational detail lives in the **gitignored** `docs/ops-hosted.local.md`.

- **Architecture (no secrets):** Azure App Service (Web App for Containers) inside the UIUC
  `urbana-business-disruptionlab` subscription, fronted by App Service Easy Auth in API/bearer
  mode (Entra platform auth, RFC 9728 PRM + `401` challenge). The app reads the trusted
  `X-MS-CLIENT-PRINCIPAL-ID`; each caller passes their own `X-Canvas-Token`; the Canvas URL is
  server-pinned; `CANVAS_API_TOKEN` must never be set in HTTP mode (startup guard). Deploy is
  branch→slot GitHub Actions (`deploy-prod.yml` / `deploy-staging.yml`).
- The open-source **self-hosted (stdio)** path is the public product — see `README.md` / `AGENTS.md`.
  HTTP-transport env-var *names* live in `env.template` / `core/config.py`; the hosted *instance*
  is operator-only.

## Session Log
> Full history: [docs/session-history.md](./docs/session-history.md)

### 2026-06-17 — mcp-remote blocker RESOLVED + app→`canvas-mcp` + branch→slot CI
- **🏁 The `AADSTS9010010` blocker is gone — verified live.** DNS landed (CNAME + asuid), bound the private custom domain + GeoTrust managed cert to the app; PRM `resource` now == the registered App ID URI, and added that URI to Easy Auth `allowedAudiences` (RFC 8707 token `aud`). Ran `mcp-remote` end-to-end against the custom domain: token exchange + MCP session succeed. (Endpoint/IDs in gitignored `docs/ops-hosted.local.md`.) **All clients (Claude Desktop/Code, Cursor, Codex, VS Code) work.**
- **App renamed `gies-canvas-mcp` → `canvas-mcp`** (Azure can't rename → recreated; house-consistent bare name like mindforum/uniquick/illinihunt). ITP had typo'd the CNAME to `canvas-mcp.azurewebsites.net` (no `gies-`) — instead of asking them to fix it, adopted the cleaner name (was globally available). Old `gies-canvas-mcp` + `gies-canvas-mcp-staging` apps deleted.
- **Branch→slot CI shipped (#128, #129):** `main`→Production, `staging`→staging slot; build→push ACR→`azure/webapps-deploy`. Auth via ACR creds + publish profiles (no SP — sidesteps Owner-only RBAC). Gotcha hit + fixed: enable SCM basic-auth or deploy fails "Failed to get app runtime OS".
- **Standardization (A/A/A):** two blessed templates — Container (canvas-mcp, illinihunt) + Code (mindforum); direct branch→slot (not swap); recorded the pattern in the `illinois-azure-container-deploy`/`cli-deploy` skills. canvas-mcp ↔ illinihunt share the container backend; mindforum is the Node-code template.
- Also merged: **#126** `check_enrollment`; doc-synced it across AGENTS/README/manifest (tool count stayed 90 — was off-by-one).
- Next: tighten `MCP_ENTRA_ALLOWED_OIDS`; AcrPull grant (Adam, `docs/compliance/email-adam-acrpull-entra.txt`); wire illinihunt CI from the now-documented pattern; GRC/Cybersecurity compliance emails.

### 2026-06-14 (cont.) — Entra v2 cutover + custom-domain pivot + enrollment tool
- **Security pass → 3 PRs merged.** Deep-research evaluated UIUC/FERPA policy (Canvas records = "Sensitive"/DAT01; FO-36→IT05 needs NetID/Entra identity, not a shared key). **#123** fail-closed the HTTP gate (refuses to start ungated unless `MCP_ALLOW_UNAUTHENTICATED=true`); **#124** added the Entra-OAuth plan + `docs/SECURITY-COMPLIANCE.md` (verified vs. open findings) + trimmed VPN as a rejected non-identity control; **#125** built the **Entra platform-auth header-reader** (App Service validates the token, app reads `X-MS-CLIENT-PRINCIPAL-ID`; codex-reviewed twice — caught a P1 fail-open + a P2 PII-in-logs, both fixed). Confirmed Azure OpenAI (in-tenant) is the LLM, not consumer Claude.
- **Cut staging over to Entra (live, `az`-driven):** created 2 Entra app regs (API + pre-authorized public client; IDs in the gitignored ops doc), enabled Easy Auth API mode (`Return401` + PRM), validated 401+RFC9728 challenge on the wire, container healthy.
- **🔑 Key blocker discovered via live test:** `mcp-remote` (and Claude Desktop native) **can't complete the Entra token exchange** — `AADSTS9010010`; the MCP SDK sends the app-URL `resource` which Entra rejects (not a registered App ID URI). Known/open bug (`geelen/mcp-remote#217`, `claude-code#52871`); **VS Code native works**. Two research agents confirmed it's unfixable client-side.
- **Pivot (no proxy): verified custom domain.** Entra rejects `*.azurewebsites.net` App ID URIs but **accepts `illinois.edu` subdomains** — registered a private custom-domain App ID URI (tested live; URL in the gitignored ops doc). Confirmed via sibling repo that `disruptionlab.illinois.edu` is a live IPAM zone and UniQuick already runs on it (ITP actions DNS requests silently/fast). DNS landed 2026-06-17.
- **Also built: `check_enrollment` (PR #126, open)** — data-minimizing "is NetID enrolled in course X?" (core + MCP tool, 10 tests) for UniQuick gating; reads roster with `skip_anonymization=True` for the match, returns only a boolean. Deferred: REST endpoint + teacher-token-sourcing decision; tool docs.
- Next: (1) **send `docs/tech-services-dns-request.txt` to consult@illinois.edu**; when DNS lands → bind hostname+cert + repoint PRM scope/`allowedAudiences` to the new hostname → re-test mcp-remote (should pass) → tighten `MCP_ENTRA_ALLOWED_OIDS`. (2) Merge #126. (3) Adam AcrPull grant (`docs/compliance/email-adam-acrpull-entra.txt`). (4) Send the GRC/Cybersecurity compliance emails (recipient/title edits pending).


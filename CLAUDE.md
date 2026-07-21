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
│   ├── tools/            # MCP tool implementations (93 tools across 17 files)
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

FastMCP server; type-driven validation via `@validate_params`; dual-layer course code↔ID caching; flexible identifiers (`get_course_id()`); ISO-8601 dates. Tools use a List→Details→Content→Analytics progressive-disclosure pattern, grouped by Canvas entity, named `{action}_{entity}`. All Canvas calls route through `make_canvas_request()` with async I/O, automatic pagination, and configurable anonymization.

**Full design reference** (patterns, parameter validation, analytics engine, messaging system): [internal/architecture.md](internal/architecture.md).

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

Version-bump procedure (files to update) + publish-race gotchas: **[internal/release-checklist.md](internal/release-checklist.md)**.

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
- [x] PR #126: `check_enrollment` capability — **merged + shipped in v1.4.0.** Deferred: REST endpoint + teacher-token-sourcing decision
- [x] Claude Desktop Extension (`.mcpb`) — scaffolded, distributed via GitHub Releases (auto-attached on tag), README install section; shipped in v1.4.0
- [x] Release **v1.4.0** — GitHub + PyPI + MCP Registry + hosted server + website all live
- [x] PR #150: self-service access-approval flow for the hosted server — merged 2026-07-01
- [x] PR #155: `update_discussion_topic` (#154) — **merged 2026-07-04** (32152e8); #154 closed; auto-deployed to hosted
- [x] Release **v1.5.0** (2026-07-05) — 3 new tools (93 total), fastmcp 2.x, security hardening (#156); all channels live (GitHub/PyPI/MCP Registry/hosted/site)
- [x] Issue #159: mcp-remote proxy hangs on stale hosted session — **fixed 2026-07-09** (PR #160: `stateless_http=True`; deployed + live-verified)
- [x] Issue #164 / PR #165: FERPA anonymization bypass (safe-endpoint short-circuit) — **fixed, merged, deployed 2026-07-21**; follow-up #166 filed
- [ ] Issue #142: MCP SDK v2 migration — **blocked upstream**: fastmcp 3.4.4 pins `mcp<2.0`, so relaxing our pin can't resolve. Re-scoped via issue comment 7/21 (verify our v2-readiness, track fastmcp upstream). **Assigned to Ash (`ashcastelinocs124`), orig. deadline ~2026-07-27 — confirm plan with Ash**
- [x] Issue #145 / PR #167: fastmcp 3.4.4 migration — **DONE 2026-07-21** (CVEs PYSEC-2026-2475/2476 resolved; dep-scan green; staging-validated then prod-deployed + live-verified; #145 closed)
- [ ] Issue #157: `execute_typescript` sandbox hardening backlog (container-level egress, non-root user, prebuilt tsx image) — **self-hosted-only now**: tool is DISABLED on both hosted slots (`EXECUTE_TYPESCRIPT_ENABLED=false`, verified 2026-07-10); gate on re-enabling hosted code-exec
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
of this (public) repo. All operational detail lives in the **gitignored** `internal/ops-hosted.local.md`
(moved out of `docs/` on 2026-06-21 — that dir is the Cloudflare Pages publish root and was serving
these local-only files publicly; `docs/.assetsignore` is now a backstop).

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
> Full history: [internal/session-history.md](./internal/session-history.md)

### 2026-07-21 — fastmcp 3.4.4 shipped (#145 closed via PR #167); GRC follow-up email to Adam
- **fastmcp 2.14.7 → 3.4.4 (PR #167, merged + deployed)**: the CVE-urgent migration (PYSEC-2026-2475/2476)
  landed same-day. Only breaking change that touched us: `get_tools()` (dict) → `list_tools()` (list),
  6 test call sites; `test_fastmcp2_compat.py` → `test_fastmcp_compat.py`. Suite 610 green; dep-scan CI
  **green on main for the first time since 7/19**; codex + claude-review both clean. Validated on the Azure
  **staging slot first** (Entra 401+PRM challenge, authenticated handshake reporting 3.4.4, live tool
  dispatch), then merged (admin, no human reviewer) → auto prod deploy → re-verified live. #145 closed.
- **#142 re-scoped (comment posted for Ash)**: fastmcp 3.4.4 still pins `mcp<2.0`, so the MCP SDK v2
  bump is blocked *upstream*, not by our pin — plan should be "verify our v2-readiness + track fastmcp".
- **Deploy gotchas captured in `internal/ops-hosted.local.md`**: pushing `staging` as a *new* branch does
  NOT fire the path-filtered deploy trigger (use `gh workflow run deploy-staging.yml --ref staging`);
  staging slot host is `canvas-mcp-staging.azurewebsites.net` (workflow header comment has stale pre-rename host).
- **Vishal's Canvas API token expired 2026-07-18** — discovered during staging validation (server relays
  Canvas's 401 correctly). Hosted client + local `.env` both affected; needs regeneration (Illinois KB form).
- **Adam/GRC follow-up email sent** (in-thread reply on "Lightweight Risk Assessment for Canvas MCP",
  via thunderbird bridge-subprocess fallback after the MCP server failed tool fetch): summary of the 7/20
  GRC/privacy review meeting with Jonathan Dial + Michael Wrobel (Tier-3-only scope, de-identification
  terminology, Splunk logging rec, codebase → Windberg/Port security reviews, license check). Draft:
  `internal/compliance/2026-07-21-adam-grc-meeting-update.txt`. Vishal trimmed + sent; he owns follow-ups.
- Next: (1) **Regenerate Canvas API token** (expired 7/18 — hosted client broken since Friday). (2) Ping
  **Ash re #142** plan + ~7/27 deadline. (3) Triage #163 medium items (docs coverage #6, ruff in CI #7,
  stale test counts #9), close #162/#163 digests. (4) **#106** mypy status comment (idle 68+ days).
  (5) #166 anonymizer backlog. (6) GRC next steps when Jonathan's privacy report lands (registrar,
  license check, Windberg/Port code handoff).

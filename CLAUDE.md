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
│   ├── tools/            # MCP tool implementations (95 tools across 18 files)
│   ├── resources/        # MCP resources and prompts
│   └── server.py         # FastMCP server entry point
├── skills/               # Agent skills for skills.sh (8 skills)
├── tests/                # 550+ tests (pytest + pytest-asyncio)
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
- [x] Issue #166: anonymizer recursive identity scrub — **fixed, merged (PR #177), deployed to hosted 2026-07-29**; follow-up #179 (layer consolidation)
- [x] **#170 Tier 1 student write tools — MERGED to main 2026-07-30 (PR #185)**, deploying with
  v1.6.0. 10 codex rounds to clean; policy carrier is the course syllabus (page carrier deliberately
  removed). Hosted instance verified write-free (CANVAS_ROLE=educator + STUDENT_WRITE_TOOLS unset;
  policy recorded in internal/ops-hosted.local.md). Issue #170 stays OPEN for UMich's two answers
  (default posture; syllabus visibility) + their test results. Design record:
  `internal/issue-170-followup-draft.md`
- [x] **#171 identity tools — MERGED (PR #183)**; #171 closed. check_enrollment now returns
  INDETERMINATE instead of a confident false NO on permission-stripped rosters
- [x] **#180 rubric visibility — MERGED (PR #182)**; #180 closed. Course-bookmark association +
  never report success on an orphaned rubric
- [x] **#179 gap-closure half — MERGED (PR #184)**: anonymization tiers (full/identity/free_text);
  /conversations + /pages gated (live replay: 97 inbox records, 0 surviving emails); missed email
  keys covered; anonymization-map tool fixed. **#179 stays OPEN** for the tool-layer call
  consolidation (status comment on issue)
- [x] Release **v1.6.0** (2026-07-30) — **all five channels live + verified**: GitHub Release (+`.mcpb`),
  PyPI, MCP Registry (`isLatest=True`), site (wrangler-deployed, 1.6.0 / **96 tools**), hosted Azure.
  Behavior change in the notes: `execute_typescript` is now opt-in (#178)
- [x] #181 `associate_rubric` never attached the rubric — **fixed + live-verified on production Canvas**
  (PR #189); shared `rubric_association_id()` / `unconfirmed_write_warning()` guard now used by every
  rubric write, closing a latent hole in the #180 bookmark path
- [x] #186 ruff in CI (**first outside contribution**, @w3lld1) — `lint` is now a required check; #175 closed
- [x] #188 `claude-review` could never pass on a fork PR (GitHub withholds secrets) — **dropped from
  required checks**, so external contributions are mergeable again. Required: `test-enhancements` + `lint`
- [x] #190 `create_rubric_from_csv` — documented CSV format was **wrong** (created zero rubrics); fixed
  in #195/#196 along with `succeeded_with_errors` handling and `error_data` surfacing
- [x] #192 `/api/quiz/v1` client routing (#193) + paginated `api_root` (#197), anonymization gate intact
- [ ] **NEW zqian bugs (2026-07-30 evening)** — ⚠️ **#199 `check_enrollment` returns "no enrollment" for a
  user plainly visible in `list_enrollments`**; likely NetID/`login_id` matching (a UIUC concept — UMich
  uses "uniqname"). Also #198 (file upload creates a stray "unfiled" folder) and #200 (missing tool
  annotations, PR #201 in flight)
- [ ] **#191 quizzes BLOCKED on correctness**: New Quizzes detection is `is_quiz_assignment AND
  external_tool`, but measured live that flag marks *Classic* quizzes — the `AND` may match nothing and
  silently report zero New Quizzes. Its test fixture hard-codes the assumption. Unblocking needs zqian's
  **scoping question 4** (a New-Quizzes-enabled sandbox)
- [ ] Daily triage routine live (`trig_011HVR6j4c5hDR2fj7k3ujxC`, 7am local) — review its PRs; it opened
  #202 on its first scheduled run
- [ ] Issue #142 → **watch item, unassigned** (`blocked-upstream`): `fastmcp-slim` 3.4.5 still pins `mcp<2.0`, so relaxing our pin cannot resolve; `mcp` 2.0.0 stable has shipped. Scope collapsed since #167 removed the FastMCP→MCPServer rename — hours, not a day. Trigger: a fastmcp release lifting `mcp<2.0`
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

### 2026-07-30 (later) — Released v1.6.0; #181 fixed + live-verified; agent fleet dispatched
- **v1.6.0 SHIPPED to all five channels, verified live**: GitHub Release (w/ `.mcpb`), PyPI, MCP
  Registry (`isLatest=True`), site (`wrangler pages deploy docs/`, now 1.6.0 / **96 tools**), and
  hosted Azure. The publish race resolved itself for the first time — PR #107's propagation poll
  absorbed a ~75s CDN lag on the version-specific PyPI endpoint, no `gh run rerun` needed.
- **Six PRs merged**: #186 (ruff CI, **first outside contribution**, @w3lld1 — closed #175), #189
  (#181 fix + shared write-confirmation guard), #195 (CSV format docs), #196 (←#194, CSV semantics,
  closed #190), #193 (`/api/quiz/v1` routing, closed #192), #197 (pagination `api_root`).
  Tests **891 → 928**.
- **#181 live-verified on production Canvas** via controlled A/B in the training sandbox (one rubric,
  two assignments, old vs fixed code path): old → `rubric_association: None`, no rubric in the UI;
  fixed → association created and rendered. Bug reproduced off zqian's instance, so it was never
  instance-specific. Sandbox cleaned, verified in UI.
- **Four silent-success bugs found in one day** (#180/#181/#190/#191) — all "plausible condition
  nobody checked against a real payload". #189 extracted `rubric_association_id()` /
  `unconfirmed_write_warning()` so the guard lives in ONE place; extracting it exposed a latent hole
  (truthy association dict with no id counted as success — verified against pre-refactor code).
- **`create_rubric_from_csv` was documented wrong** — measured live: our documented format returns
  `succeeded_with_errors`, "Missing 'Rubric Name' in some rows", **zero rubrics created**. Gap 1's
  bookmark hypothesis was DISPROVEN (imports DO show in the Rubrics UI as `Draft`; the API doesn't
  list them — inverse of #180).
- **CI/ruleset**: `lint` added as a required check; **`claude-review` dropped** (#188 — GitHub
  withholds secrets from fork `pull_request` workflows, so it could never pass on an outside PR;
  every external contribution was unmergeable). Required checks now `test-enhancements` + `lint`.
- **Agent fleet dispatched**: #172/#190/#192 to `copilot-swe-agent`; Ash unassigned from everything;
  #142 → watch item (`blocked-upstream`, fastmcp-slim 3.4.5 still pins `mcp<2.0`). Key lesson:
  **agents read the issue BODY, not comments** — added scope banners to #172/#190 so a stale premise
  doesn't get built.
- **Daily triage routine LIVE** (`trig_011HVR6j4c5hDR2fj7k3ujxC`, 01:30 UTC / 7am local) — **fired on
  schedule and produced PR #202**, a high-quality brief that correctly surfaced the three new zqian
  bugs. `gh` is NOT installed in the cloud sandbox; it uses GitHub MCP tools.
- Next: (1) **THREE new zqian bugs**: **#199 check_enrollment returns "no enrollment" for a user
  visible in `list_enrollments`** — likely NetID/`login_id` matching, which is a UIUC concept
  (UMich uses "uniqname"); #198 file upload creates a stray "unfiled" folder; #200 missing tool
  annotations (PR #201 in flight). (2) **#191 BLOCKED**: New Quizzes detection is
  `is_quiz_assignment AND external_tool`, but measured live that flag marks *Classic* quizzes — the
  `AND` may match nothing; its test fixture hard-codes the assumption. Needs zqian's **scoping
  question 4** (New-Quizzes sandbox) — now blocking correctness, not just timeline. (3) Review PR
  #202 brief + #201. (4) Backlog: #173 (manifest 30/96, title says 24/93), #179 consolidation half,
  #106 mypy, stale `associate_rubric_with_assignment` at `docs/learning-designer-guide.html:173`.

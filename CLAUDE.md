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
│   ├── tools/            # MCP tool implementations (99 tools across 19 files)
│   ├── resources/        # MCP resources and prompts
│   └── server.py         # FastMCP server entry point
├── skills/               # Agent skills for skills.sh (8 skills)
├── tests/                # 900+ tests (pytest + pytest-asyncio)
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

### Closing-keyword guard — run `./scripts/install-hooks.sh` once per clone

GitHub closes an issue on any `fixes|closes|resolves #N` in a merged PR body **or
a commit message landing on `main`** — including prose that only *describes*
other work. Issue #172 was closed twice this way (PR #202's body, then commit
`98643ce` whose message documented the first accident).

`scripts/check_closing_keywords.py` is the single detector, shared by the
`commit-msg` hook (prevention) and `.github/workflows/closing-keyword-guard.yml`
(backstop). It blocks keywords **mid-sentence** and allows ones that **open a
line** — `Closes #173` is a deliberate trailer, `...bug that closed #172` is
narration. Deliberate close on a fix PR needs no ceremony; narration must be
rephrased (`closed [issue 172]`) or bypassed with `ALLOW_CLOSING_KEYWORD=1`.

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
- **Error responses**: dict-returning tools include an `"error"` key; string-returning tools return a human-readable `"Error ..."` message (match the module you're editing)
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
- [x] **All three zqian bugs CLOSED 2026-07-31.** **#199** was three defects with one root cause (a
  confident negative on an unchecked premise): `login_id` assumed to be the bare campus ID (measured
  live — UIUC stores `vishal`, email-provisioned instances store `uniqname@umich.edu`); an email-form
  identifier rejected by the input guard before any Canvas call; and `role`'s `student` default pushed
  to Canvas as `type[]`, hiding every other role. Adds an **AMBIGUOUS** answer for anything
  unverifiable (PR #203). **#198** fixed + measured A/B: omitting `parent_folder_path` isn't "root",
  Canvas creates an `unfiled` folder (PR #203). **#200** annotations (PR #201, Copilot agent)
- [x] **#204 tool-annotation contract complete + CI-gated (PR #205)** — `destructiveHint` now follows
  the MCP spec ("only additive updates") instead of "destructive == deletes"; `idempotentHint` set
  everywhere and judged on **whole effect** (grade writers append a comment; page tools re-notify;
  `delete_announcements_by_criteria` re-derives its target set). `tests/test_tool_metadata.py`
  enumerates the live registry **with every feature flag on**, so a bare `@mcp.tool()` fails CI —
  the default set had hidden `execute_typescript` shipping unannotated. Convention in
  `internal/architecture.md`
- [x] **Hosted deployment spec public (PR #206, 2026-07-31)** — `deploy/azure/` (spec + 4 placeholdered
  templates) is canonical; corrected HTML copies emailed in-thread to UMich (zqian) + UC Irvine
  (VC Choudhary); site callout live on canvas-mcp.illinihunt.org. Their feedback lands as edits to
  `deploy/azure/README.md` (`internal/hosted-spec-draft/` is scratch)
- [x] Release **v1.7.0** (2026-08-08) — all five channels live + verified. Correctness release:
  unconfirmed-write guards (#219/#220/#221), Planner-API upcoming assignments (#222), annotation
  contract (#204), `cryptography` CVE, anonymization consolidated to the client layer (#179)
- [x] Closing-keyword guard (#231) + three bypasses closed after an independent red-team (#241).
  Contributors run `./scripts/install-hooks.sh` once per clone
- [ ] **#238** `list_discussion_topics` sends unsupported `include[]=announcement` instead of
  `only_announcements`, and `tools/README.md:1733` names the parameter wrong — likely why zqian saw
  discussion topics in an announcements listing
- [ ] **#233/#234/#235** triaged, fixes pending: media inventory in `get_page_content`; stop
  claiming an unconfirmable `notify_of_update`; grade-comment docstring hardening
- [ ] **#239** page bodies returned verbatim into model context (prompt-injection surface); other
  free-text tools not yet audited
- [ ] **#236** OAuth2 developer-key flow (from discussion #229) — additive path only, blocked on
  admin access to pilot a scoped key
- [ ] Add `uv.lock` to `internal/release-checklist.md` — it carries the version and is not listed
- [ ] **#191 quizzes BLOCKED on correctness**: New Quizzes detection is `is_quiz_assignment AND
  external_tool`, but measured live that flag marks *Classic* quizzes — the `AND` may match nothing and
  silently report zero New Quizzes. Its test fixture hard-codes the assumption. Unblocking needs zqian's
  **scoping question 4** (a New-Quizzes-enabled sandbox)
- [x] Daily triage routine live (`trig_011HVR6j4c5hDR2fj7k3ujxC`, 7am local) — #202 merged. **Prompt
  patched 2026-07-31**: merging a brief closed #172, because it described another PR as `fixes #172`
  and GitHub parses closing keywords anywhere in a merged PR body. Routine now forbids them *and*
  greps its own output before opening the PR (#172 reopened)
- [ ] Issue #142 → **watch item, unassigned** (`blocked-upstream`): `fastmcp-slim` 3.4.5 still pins `mcp<2.0`, so relaxing our pin cannot resolve; `mcp` 2.0.0 stable has shipped. Scope collapsed since #167 removed the FastMCP→MCPServer rename — hours, not a day. Trigger: a fastmcp release lifting `mcp<2.0`
- [x] Issue #145 / PR #167: fastmcp 3.4.4 migration — **DONE 2026-07-21** (CVEs PYSEC-2026-2475/2476 resolved; dep-scan green; staging-validated then prod-deployed + live-verified; #145 closed)
- [ ] Issue #157: `execute_typescript` sandbox hardening backlog (container-level egress, non-root user, prebuilt tsx image) — **self-hosted-only now**: tool is DISABLED on both hosted slots (`EXECUTE_TYPESCRIPT_ENABLED=false`, verified 2026-07-10); gate on re-enabling hosted code-exec
- [ ] Backlog triage (module templates, bulk creation, page versioning — feature ideas only, no owner)
- [x] Issue #106: mypy 229 → 0 errors + mypy in CI lint job (PR #213, 2026-08-01)

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

### 2026-08-08 — v1.7.0 shipped; guard shipped, red-teamed, and fixed same day

- **Released v1.7.0** — all five channels verified live: GitHub Release (+`.mcpb`), PyPI, MCP
  Registry (`isLatest=True`), site (wrangler-deployed, both `softwareVersion` and the v-banner),
  hosted Azure. No publish race this time; the registry job passed first try. `uv.lock` also
  carries the version and is **missing from `internal/release-checklist.md`** — it only got
  bumped here because `git add -A` swept it up.
- **Closing-keyword guard (#231)** — one detector shared by a `commit-msg` hook and CI, after
  #172 was closed twice by accident (PR #202's body, then commit `98643ce` whose message
  *documented* the first accident). Acceptance replay found three closures nobody had recorded:
  a second reference inside `98643ce` (#203), `2bee9f2` (#215), `e3922b3` (#111).
- **Then an independent Codex red-team broke it (#241)** — three silent bypasses, all from my own
  design choices. Critical: `#` lines were skipped as git comments, but in a **PR body** `#` opens
  a markdown heading GitHub parses as prose, and one function scanned both surfaces. The replay
  missed it because it replayed `git log` and never scanned a PR body. Replay now extended: 100
  real PR bodies, zero false positives, two true positives (PR #202, the original incident, and
  PR #187 with an unnoticed closure of #175).
- **Merged the 7-deep triage-brief backlog** (#209–#230). The routine derives its cutoff from the
  newest brief *on main* but only opens **draft** PRs, so it re-scanned the same window for 8
  cycles — a scanner that cannot commit its own progress marker stalls silently.
- **#172 reopened and answered** — `jonespm` (first-time outside commenter) had flagged the
  closed-but-unfinished issue 3 days earlier. The triage routine could not see it: it queries
  `is:open`, which structurally cannot surface a comment on a wrongly-closed issue.
- **zqian filed four bugs in 24h** (#233/#234/#235/#238) and TSU-Carrell opened discussion #229
  (OAuth developer-key flow → tracked as #236). Triaged #233/#234/#235: **two are not server
  bugs** — `get_page_content` returns body HTML verbatim (measured live; the model summarized it
  away), and no grade path defaults a comment (the assistant supplied it). Filed **#239**: page
  bodies flow verbatim into model context, a prompt-injection surface.
- **Parallel-diagnosis beat review.** An isolated Codex diagnosis of #238 converged on my one
  finding and then found three I missed, including the likely root cause: `list_discussion_topics`
  sends an unsupported `include[]=announcement` instead of `only_announcements`, and
  `tools/README.md:1733` documents the parameter under the wrong name. My own hypothesis was
  **not** supported.
- Bugbot disabled on this repo — it writes into PR *descriptions* (regenerating on every push) and
  did so while rate-limited to zero reviews, injecting closing keywords the author never wrote.
- Next: (1) **#238 fix** — the mis-parameterized `list_discussion_topics` + wrong docs.
  (2) Fixes for #233 (media inventory), #234 (stop claiming an unconfirmable notification),
  #235 (docstring hardening + possible no-comment flag). (3) Review PRs #232 and #237.
  (4) Add `uv.lock` to the release checklist. (5) **#191 still blocked** on zqian's New-Quizzes
  sandbox. (6) Deferred: wrap-up-skill redesign for change comprehension —
  `~/.claude/skills/wrap-up-session/DESIGN-NOTES-in-progress.md`.

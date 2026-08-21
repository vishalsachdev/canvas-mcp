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
│   ├── tools/            # MCP tool implementations (up to 101 tools across 20 files)
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

### Parallel work: one PR = one worktree

This repo often has several agents/sessions working at once. The primary checkout
(`/Users/vishal/code/canvas-mcp`) stays on `main`, clean — treat it as read-only (triage,
review, reading). All branch work happens in a sibling worktree named `canvas-mcp-<slug>`
on branch `fix/NNN-slug`, created from `origin/main` (gitignored files like `.env` don't
carry over — symlink them). Never repurpose a worktree for a different issue; remove it
after its PR merges and delete the branch (local + remote). After any sibling PR merges,
rebase surviving worktree branches onto `main` and rerun tests there. Full lifecycle:
global `worktree-pr` skill.

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
- **Legacy `-> str` tools**: a few modules (notably `modules.py` and `accessibility.py`) still return JSON-stringified error objects instead of plain `"Error ..."` text; preserve the local convention when editing them
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
  policy recorded in internal/ops-hosted.local.md). **#170 CLOSED 2026-08-19** as completed for the
  delivered Tier 1 work; UMich's two pilot questions (default posture; syllabus visibility) were never
  answered and are no longer gating. Design record: `internal/issue-170-followup-draft.md`
- [x] **#171 identity tools — MERGED (PR #183)**; #171 closed. check_enrollment now returns
  INDETERMINATE instead of a confident false NO on permission-stripped rosters
- [x] **#180 rubric visibility — MERGED (PR #182)**; #180 closed. Course-bookmark association +
  never report success on an orphaned rubric
- [x] **#179 gap-closure half — MERGED (PR #184)**: anonymization tiers (full/identity/free_text);
  /conversations + /pages gated (live replay: 97 inbox records, 0 surviving emails); missed email
  keys covered; anonymization-map tool fixed. **#179 CLOSED 2026-08-01** — the tool-layer call
  consolidation shipped in PR #211 (plus a ruff TID251 ban to keep it consolidated)
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
- [x] **Security scan remediation — MERGED (PR #251, 11 commits by boundary).** 12 findings, 11
  fixed: host-filesystem boundary in the file tools (both high), a **measured** `/submissions/self`
  authorization bypass via path delimiters, CSV formula injection, Registry anonymization default,
  unauthenticated route limits, sandbox fail-closed, Canvas token at rest/in transit, AI workflow
  least privilege. Two Codex rounds (round 1 found a P1 in my own HTTPS fix; round 2 clean).
  **Three breaking changes now on main — next release needs a minor bump.**
- [ ] **#157 sandbox egress is only mitigated, not closed.** `--network=none` is passed when
  outbound is blocked *and* the allowlist is empty — but blocking auto-allowlists the Canvas host,
  so in any working config egress falls back to the in-process Node guard, which `child_process`
  and bundled utilities bypass while `CANVAS_API_TOKEN` is in the environment. Now warns honestly
  instead of implying enforcement. Real fix needs an egress proxy or network namespace
- [x] **#249 npm setup wizard retired — CLOSED (PR #257, 2026-08-10).** Deprecated the npm package
  (name retained), removed `cli/` + orphaned `docs/workshop.html`; restored the UIUC KB-150325 token
  link into both docs guides (it had lived only on the deleted workshop page)
- [x] Closing-keyword guard (#231) + three bypasses closed after an independent red-team (#241).
  Contributors run `./scripts/install-hooks.sh` once per clone
- [x] **CI never ran the test suite (PR #247)** — the *required* `test-enhancements` check looked
  for `tests/test_discussion_enhancements.py` (does not exist) and echoed a hand-written
  "✅ Basic Validation Completed / PASSED". Only **363 of 1091** tests ran on a PR (`tests/security`
  via a different workflow); **728 never ran**. Now a 3.10/3.11/3.12/3.13 matrix runs `pytest tests/`,
  with an aggregator keeping the required job *name* (a bare matrix publishes `test (3.10)`, which
  would leave the required check pending forever and block every PR). `publish-mcp.yml` no longer
  swallows failures with `|| echo "No tests found"`. **This is the likely reason so many defects
  landed green** — see the four below, each of which the suite was asserting as correct
- [x] **#238 announcements vs discussions (PR #242)** — `include[]=announcement` is a measured no-op
  (live A/B: identical 19 topics with and without it); `only_announcements` is the real filter and
  *switches* scope rather than widening, so combining costs a second call. README + manifest
  documented a **parameter that does not exist**. `list_announcements` was educator-only while
  AGENTS.md called it shared — resolved by making it **shared** (an independent Codex run framed it
  as a registration bug where I had framed it as a docs bug, and was right). The reporter's suggested
  `/announcements?context_codes[]` was measured and rejected: returns 0 (default date window)
- [x] **#233 page media (PR #246)** — `get_page_details` stripped `<img>`/`<iframe>` with a naive
  regex, destroying media with no trace, then labelled it "Content Preview". Measured on a real page:
  4 embedded videos → 0. Adds `extract_embedded_media()`; both lossy steps now announce themselves;
  naive regex → `strip_html_tags` (which also drops `<script>` *contents*)
- [x] **#234 notify_of_update (PR #245)** — measured live: Canvas's PUT returns 16 keys and none is
  `notify_of_update`, so it can never be confirmed. Now warns instead of claiming success, with a
  confident *no* for the two visible suppression cases (unpublished, <1min old)
- [x] **#235 grade comments (PR #248)** — not a server default, but **our own artifacts taught it**:
  the bulk-grading skill shipped `comment: "Graded via automated review"` and every README grading
  example paired a comment with a grade. Also fixed: the dry run never named the comment (the
  documented safety net hid the one irreversible side effect), and the simple path used membership
  while the rubric path used truthiness, so `comment: None` posted
- [x] **`/front_page` was ungated (PR #244)** — returned `last_edited_by` (display name, pronouns,
  avatar) while `/pages/{slug}` was gated at `identity`; the tier rule matched the `pages` path
  segment, which `front_page` lacks. **Two tests asserted the gap as correct.** Same class as #164/#179
- [x] **#239 prompt-injection boundary — IMPLEMENTED + MERGED (PR #258, 2026-08-10).** 11 Codex
  rounds; fencing at the tool output-formatting boundary (both forms), write-marker backstop, and
  `write_confirmation` tokens making 4 fan-out senders two-step. ReDoS + token-DoS found and fixed
  along the way; live-verified. **4 breaking changes → next release is a minor bump.** #239 stays
  OPEN for 2 low-risk deferrals (course names, own profile); durability follow-up = **#262** (CI
  guard). Full record: [[project-239-untrusted-content-boundary]]
- [ ] **#236** OAuth2 developer-key flow (from discussion #229) — additive path only, blocked on
  admin access to pilot a scoped key
- [x] Release **v1.8.0** (2026-08-09) — all five channels live + verified. Security release:
  the 11 scan fixes + 3 breaking changes (HTTPS-only, stdio-only file tools, no-overwrite
  downloads) + #255 dependency floors/workflow least-privilege. `uv.lock` now on the release
  checklist; `cli/package-lock.json` drift fixed
- [x] Release **v1.9.0** (2026-08-10) — all five channels live + verified. The #258 breaking
  changes (4 two-step fan-out senders) + provenance fencing + OSSF Scorecard/supply-chain work.
  **First release with `.mcpb` SLSA provenance** (`gh attestation verify` passes); the
  restructured two-job `create-release.yml` survived its first live run; no PyPI propagation race
- [x] **#252 diagnosed (not merged as reported)**: PR #253's form-data fix measured unnecessary —
  wire encodings equivalent; likely the pre-#220-guard permission failure on v1.6.0. Awaiting
  zqian's retest on v1.7.0+; #253 open pending that
- [ ] **PR #191 (Copilot) quizzes BLOCKED on correctness** — note this is a *PR* against issue
  **#172**, not an issue itself. New Quizzes detection is `is_quiz_assignment AND external_tool`, but
  measured live that flag marks *Classic* quizzes — the `AND` may match nothing and silently report zero
  New Quizzes. Its test fixture hard-codes the assumption. Unblocking needs zqian's **scoping question 4**
  (a New-Quizzes-enabled sandbox). Two more blockers: a 262-line non-mechanical conflict in
  `assignments.py`, and a live `Fixes` line in the PR body that would auto-close #172 on merge (#172 has
  already died this way twice). Decide this week: source a sandbox, or close the PR honestly as
  unverifiable and reopen when one exists
- [x] Daily triage routine live (`trig_011HVR6j4c5hDR2fj7k3ujxC`, 7am local) — #202 merged. **Prompt
  patched 2026-07-31**: merging a brief closed #172, because it described another PR as `fixes #172`
  and GitHub parses closing keywords anywhere in a merged PR body. Routine now forbids them *and*
  greps its own output before opening the PR (#172 reopened)
- [ ] Issue #142 → **watch item, unassigned** (`blocked-upstream`): `fastmcp-slim` 3.4.5 still pins `mcp<2.0`, so relaxing our pin cannot resolve; `mcp` 2.0.0 stable has shipped. Scope collapsed since #167 removed the FastMCP→MCPServer rename — hours, not a day. Trigger: a fastmcp release lifting `mcp<2.0`
- [x] Issue #145 / PR #167: fastmcp 3.4.4 migration — **DONE 2026-07-21** (CVEs PYSEC-2026-2475/2476 resolved; dep-scan green; staging-validated then prod-deployed + live-verified; #145 closed)
- [ ] Issue #157: `execute_typescript` sandbox hardening backlog (container-level egress, non-root user, prebuilt tsx image) — **self-hosted-only now**: tool is DISABLED on both hosted slots (`EXECUTE_TYPESCRIPT_ENABLED=false`, verified 2026-07-10); gate on re-enabling hosted code-exec
- [ ] **Agent Plugins ([agent-plugins.org](https://agent-plugins.org)) → watch item, no owner.** Spec 1.0.0
  landed 2026-08-06 (TSC: Amazon, Cursor, Microsoft, OpenAI, Vercel): root `plugin.json` +
  `skills/<name>/SKILL.md` + `mcp.json`. Our `skills/` is **already conformant**, so packaging is ~2
  files / ~30 min. **Blocked on credentials, not packaging:** the spec "defines no portable OAuth or
  credential-reference fields", `mcp.json` `env`/`headers` are literal visible package data (only
  `${PLUGIN_ROOT}` / `${PLUGIN_DATA}` expand), and the subprocess base environment is *client-selected*
  — so `CANVAS_API_TOKEN` + `CANVAS_API_URL` have no delivery path and a plugin install would fail on
  first tool call. Strictly worse than the `.mcpb` (keychain prompt) we already ship. **HTTP side does
  not apply:** hosted instance is private (URL stays out of this repo) and per-caller `X-Canvas-Token`
  can't live in portable headers. Audience skew too — Claude Code uses its own `.claude-plugin/plugin.json`,
  Anthropic isn't on the TSC, and skills.sh already covers 40+ agents. Triggers to revisit: (1) a client
  ships user-secret prompting for plugin MCP servers, or the spec adds credential refs; (2) Claude
  clients adopt/bridge the format (both layouts use `skills/<name>/SKILL.md`, so dual-shipping is cheap);
  (3) a user files an issue. If ever built: `cwd: "${PLUGIN_DATA}"` + a setup skill writing `.env` there
  is the viable pattern, but needs an explicit path in `load_dotenv()` (it resolves against the calling
  module, not CWD). Cost if adopted: a 4th version-stamp location in the release checklist
- [ ] Backlog triage (module templates, bulk creation, page versioning — feature ideas only, no owner)
- [x] Issue #106: mypy 229 → 0 errors + mypy in CI lint job (PR #213, 2026-08-01)
- [x] **#275 `get_my_peer_reviews_todo` — CLOSED 2026-08-20** on khagyard's confirmation
  ("The fix worked thank you!"). PR #288's Planner-feed discovery path is what fixed it; the
  assignment-scoped `peer_reviews` endpoints are instructor-focused, which @aesse97 called
  correctly in the thread. Two corrections to the old note here: the earlier claim that khagyard
  "confirmed still not found even with the direct lookup" is **unsupported** — their report
  predates any build containing PR #277's `assignment_identifier`, and they never answered which
  version they were on. And the **root cause of the original discovery-scan miss was never
  diagnosed, only routed around**. Their production payload is now the acceptance-replay fixture
- [x] **#309 content migration — PR #316 MERGED 2026-08-20** (`ea50c711`). Two educator-only tools:
  preview→confirm course copy + one-poll-per-call status with migration-issue review. **#309 stays
  OPEN** for zqian's answer on `selective_import` (deliberately out of v1: a second async workflow
  that cannot be measured without a sandbox) and for a real sandbox payload — the bracket-form
  encoding, Progress state vocabulary, and migration-issue field names are doc-derived, not measured

- [x] **#283 announcement→discussion silent fallback — two-layer fix complete (PR #285 +
  PR #291, merged 2026-08-14).** jonespm's retest showed the deeper mechanism: Canvas answers
  200 to a student's create_announcement, silently drops `is_announcement`, and creates a real
  discussion topic. PR #291 adds (1) a permission pre-check — `GET /courses/:id?include[]=permissions`,
  measured live: flags exist ONLY on the single-course endpoint (list ignores the include;
  `/permissions` omits them); refuses only on explicit `false`, fails open otherwise — and
  (2) cleanup: the orphaned topic is auto-deleted on downgrade detection. Two opencode rounds
  (round 1 found a None-body TypeError on the cleanup DELETE; round 2 APPROVE). Issue stays
  open for khagyard's student-token retest from main (their test course still has orphan topic 674)
- [x] **#281 search_canvas_tools never searched MCP tools — fixed (PR #286, merged 2026-08-13).**
  It searched only code_api TS files (bruchris's outside diagnosis, correct). Now also
  queries the live registry (`mcp.list_tools(run_middleware=False)`) with labeled sections;
  **breaking: response shape v2** (`schema_version: 2`, flat `tools` key gone), shape pinned
  by test. Follow-up #287 filed (pre-existing uncapped `full`-mode TS dumps). zqian confirmed
  on `main` (multiple queries) — **issue CLOSED 2026-08-14**
- [x] **#287 uncapped full-mode TS dumps — CLOSED (PR #290, merged 2026-08-14).** Second
  outside code contribution (@SHIL0018): 2,000-char cap + regression test on the discovery
  code-API full branch. Fork CI needed manual approve-runs; `claude-review` failed as always
  on forks (not required). Verified the fixture can't pass vacuously (matched file is 18.8KB)
- [x] **#270 isError + #271 double-payload — IMPLEMENTED AND MERGED 2026-08-19** (commits `2f87e13`,
  `85b1f16`, `feae3a8`; new `src/canvas_mcp/core/tool_results.py`). Both issues CLOSED. Tool failures now
  set MCP `isError: true`; string-returning tools no longer duplicate their value into
  `structuredContent.result`. **Two breaking wire-shape changes sitting UNRELEASED on `main`** — see the
  release note below
- [x] **#262 CI fencing guard — DONE 2026-08-19** (`b9c93a5`, registry-wide read-tool fencing coverage);
  #262 CLOSED. This was the durability follow-up named on #239, which is also CLOSED (2026-08-19) — its
  two low-risk deferrals (course names, own profile) are documented policy choices now, re-file narrowly
  if ever wanted
- [x] Release **v1.11.0** (2026-08-20) — all five channels live + verified: GitHub Release
  (`.mcpb` + SLSA, `gh attestation verify` exit 0), PyPI 200, MCP Registry `isLatest=True`,
  site wrangler-deployed to the custom domain, hosted Azure auto-deployed (401 challenge healthy).
  Protocol-correctness release: #303 rename (breaking), #270 `isError`, #271 double-payload,
  fastmcp 3.4.7 floor. **Registry job failed once on a NEW failure mode** — an unauthenticated
  `api.github.com` lookup rate-limited to `null`, surfacing as `not in gzip format`; a rerun
  fixed it and the step is now authenticated with a null guard (`4639847`). Not the PyPI race:
  PyPI already returned 200. Both modes and the test that distinguishes them are in the checklist

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
> Full history: `internal/session-history.md` — **local-only, untracked since 2026-08-20**
> (it carried a paraphrase of a collaborator's private email and the private hosted endpoint
> URL while being world-readable). Do not re-add it to git.

> **`internal/` is deny-by-default in `.gitignore`.** Add an un-ignore only for a file
> deliberately meant to be public. Daily triage briefs stay tracked because the routine reads
> the newest one to compute its cutoff, so they **must not** record an external collaborator's
> institutional affiliation, evaluation status, deployment timeline, or which competing
> products they are weighing. Name the person and the technical issue, nothing else.

### 2026-08-20 — v1.11.0 shipped; internal/ leak closed; content migration merged; Reynolds declined

- **Confidentiality fix (highest impact).** `internal/` defaulted to PUBLIC with six targeted
  exclusions, so `internal/session-history.md` had been world-readable for 22 days carrying a
  paraphrase of a collaborator's private email (their deployment timeline, the competing product
  they were weighing, their stated decision criterion) AND the private hosted endpoint URL this
  repo is supposed to exclude. `.gitignore` is now **deny-by-default** for `internal/` with an
  explicit un-ignore list; session-history untracked (local-only); ten triage briefs scrubbed of
  affiliation and evaluation-status framing. History deliberately NOT rewritten — 198 stars /
  67 forks. Verified live: raw URL now 404s, control file still 200. Decision: **do not tell zqian**.
- **Release v1.11.0** — all five channels verified. Protocol-correctness: #303 rename (breaking),
  #270 `isError`, #271 double-payload, fastmcp 3.4.7 floor. Website tempered from a bare "99 tools"
  to "up to 99" (default is 94) then to 101 after the migration tools. **New CI failure mode found
  and fixed** (`4639847`): the Registry job's *unauthenticated* `api.github.com` lookup rate-limited
  to `null`, surfacing three steps later as `gzip: stdin: not in gzip format`. NOT the PyPI race —
  PyPI was already 200. Both modes now in the release checklist with the test that separates them.
- **PR #316 merged** (`ea50c711`) — content migration for #309: `create_content_migration`
  (mandatory preview→confirm, token-bound, reports target occupancy, never claims content was
  copied) + `get_content_migration_status` (one poll per call, fences untrusted text, treats an
  unreadable issues list as an error not an empty list). Codex architected, I critiqued (dropped
  `openWorldHint` — zero tools use it; added target-occupancy preview; caught two missed doc files),
  Codex implemented, I re-verified independently. 24 new tests, 1398 passing. **#309 stays OPEN** —
  `selective_import` deliberately deferred and zqian asked directly whether all-content suffices.
- **Mark Reynolds DECLINED** to test or review (2026-08-17): "no need to involve our groups with it
  as there is no deployment necessary... it won't initiate a review." His reasoning is LTI-shaped —
  canvas-mcp is an API client, not an installed integration. **The Reynolds route to a campus
  blessing is closed**; Adam King's LRA remains the only Illinois review artifact. Do not re-invite.
- **Community:** #275 CLOSED (khagyard confirmed the fix). #293 CLOSED, with #315 filed first so the
  Python 3.10 EOL (2026-10-31) didn't vanish with the report. #302 answered after three triage
  cycles of silence; #283 pinged — redirected to **jonespm**, who is the real confirmer (khagyard has
  never commented there), auto-close 2026-08-27. Rebecca Simon (`rpsimon-ai`, first-time contributor)
  emailed confused that her requests "failed" — root cause: **there is no Skill Request template** and
  the three that exist are developer-gated (Tool Addition *requires* a Canvas API endpoint). She used
  the blank-issue fallback correctly. Reply sent.
- **Corrected 5 stale Current Focus lines** verified against live state: #170/#179/#239 were closed
  but recorded open; #270/#271 shipped 2026-08-19 but recorded "not implemented"; PR #191 was
  described as an issue. Six merged worktrees removed.
- **Next:** (1) **add a Skill Request issue template** — promised to Rebecca on #302 and in email;
  (2) PR #308 + dependabot #295–#298 are all behind `main` after #316 — update branches before
  merging; (3) **PR #191/#172 decision** — oldest live thread, blocked 3 weeks on a New-Quizzes
  sandbox: source one from zqian or close the PR honestly as unverifiable; (4) #309 awaits zqian on
  selective import + a sandbox payload to convert the doc-derived assumptions into measured ones;
  (5) #313 needs the reply (CANVAS_ROLE already ships, but educator=88 leaves only 40 of his 128
  budget, so it may not actually solve his cap); (6) #283 self-closes 2026-08-27.

## ⚠️ Adoption numbers: what is safe to publish (2026-08-21)

Before quoting any adoption figure for this project in a paper, report, or institutional
document:

- **Never print a PyPI download count.** It swings by more than an order of magnitude month to
  month — 521 (March), 7,426 (2026-08-10), 2,208 (2026-08-17). Whatever you quote will be wrong
  within weeks and looks cherry-picked either way.
- **Stars / forks / contributors are stable** and are the defensible numbers. Dated snapshot:
  **194 stars / 65 forks / 19 contributors (2026-08-17)**; 198 / 67 on 2026-08-20. **Re-pull from
  the GitHub API on the day the document is finalised** and state the date alongside.
- **Two claims in circulation are NOT verified** and are flagged internally as author-promotion
  statements: *"over 18,000 clones"* and *"the University of Michigan selected it as the sole
  Canvas MCP candidate for campus deployment."* Do not repeat either without a primary source.

**Institutional posture — be precise.** A private, Entra-gated hosted instance serves Gies course
staff; the **public hosted server was retired**. The only Illinois review artifact is Adam King's
LRA — Mark Reynolds declined to initiate a campus review on 2026-08-17. **Do not imply a campus
security review or blessing that does not exist.**

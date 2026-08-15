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
- [ ] **#275 `get_my_peer_reviews_todo` false negative — PR #277 merged, issue stays OPEN.**
  `assignment_identifier` param added (direct per-assignment lookup, bypasses the
  discovery scan's `peer_reviews`-flag gate) but root cause of the discovery-scan miss
  is still unconfirmed — no student-scoped token available to reproduce. Rejected a
  Copilot-authored PR (#276) whose fix didn't match how the Canvas endpoint actually
  behaves. Reporter (`khagyard`) confirmed: regular assignment, not anonymous, assigned
  before due date — still not found even with the direct lookup, per the daily triage
  routine's follow-up on the issue. **PR #288 MERGED 2026-08-13 (night)** — Planner-API
  discovery path (community-confirmed: student UI uses `/planner/items`, the
  assignment-scoped peer_reviews endpoints are instructor-focused). The merge gate
  worked exactly as designed: khagyard posted a **real production payload** ~2h after
  the ask, which falsified `plannable.user_id`/`assessor_id` (absent in reality —
  output would have said "Student None") and confirmed completed items still appear
  under `filter=incomplete_items`. Their 3-item payload is now the acceptance-replay
  fixture (JWT image URLs stripped). Verified: opencode review + Devin 3/3 PASS + CI +
  main suite green (1350). Issue stays open for khagyard's retest from main; close on
  their confirmation. Ships in next release (minor bump already owed)
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
- [ ] **#270 isError — scoped, not implemented** (design comment on issue 2026-08-13):
  central registration-time wrapper, ship together with #271; deferred to a supervised
  session (touches every tool module)

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


### 2026-08-14 — PRs #290+#291 merged; Reynolds hosted-test invite staged

- Completed: (1) **PR #290 merged, #287 CLOSED** — @SHIL0018's outside contribution (2nd ever)
  capping full-mode TS dumps; fork CI manually approved, fixture verified non-vacuous.
  (2) **PR #291 merged** — two-layer #283 fix: permission pre-check (`include[]=permissions`,
  measured live: flags exist only on the single-course endpoint) + auto-delete of the silently
  downgraded discussion topic; 2 opencode rounds (round 1 caught a None-body TypeError),
  live acceptance on a real no-permission course; #283 open awaiting khagyard's retest.
  (3) **Mark Reynolds hosted-test invite**: OID added to `MCP_ENTRA_ALLOWED_OIDS` (11 now),
  hosted `.mcpb` rebuilt as v1.0.1 (June build was missing `offline_access` → hourly re-auth),
  Thunderbird draft staged with attachment — **Vishal sends it**; drafts in
  `internal/email-reynolds-hosted-test.local.{txt,md}` (`.local.` = gitignored, private URL).
  Key framing correction: the HOSTED instance is the sole object of UIUC review; stdio is not.
- Next: (1) **release with a minor bump** (breaking: #251/#258 carryover + #286 schema v2; now
  also carries #290/#291); (2) close #275/#283 on khagyard's retest (triage watches);
  (3) supervised #270+#271 session — add the two pre-existing nits found in review
  (bare `"error" in response` in delete_announcement; `ID: None` interpolation);
  (4) send the Reynolds draft (sits in Thunderbird Drafts); (5) Codex credits still out —
  opencode (deep) + devin (quick) until refilled.

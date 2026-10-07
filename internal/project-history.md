# Project history (moved out of CLAUDE.md, 2026-09-30)

The Current Focus, Roadmap and Backlog sections exactly as they stood in CLAUDE.md on
2026-09-30, completed items included. CLAUDE.md now lists only the open items. Statuses
here are as written at the time and are not maintained; check the issue tracker and
CHANGELOG.md for current state. Session-by-session history is in the local-only
`internal/session-history.md`.

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
│   ├── tools/            # MCP tool implementations (up to 111 tools across 21 files)
│   ├── resources/        # MCP resources and prompts
│   └── server.py         # FastMCP server entry point
├── skills/               # Agent skills for skills.sh (8 skills)
├── tests/                # 900+ tests (pytest + pytest-asyncio)
├── docs/                 # GitHub Pages site + guides
├── tools/                # Tool documentation (README.md, TOOL_MANIFEST.json)
├── archive/              # Legacy code (git-ignored)
└── .env                  # Configuration (CANVAS_API_TOKEN, CANVAS_API_URL)
```

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
- [x] **#318 delete confirmation — SHIPPED (PR #330, 2026-08-29)**; **#325 `ACCESSIBILITY_CHECKERS` — SHIPPED (PR #329)**; **#315 drop 3.10 — SHIPPED (PR #331), closed**. All in **v1.12.0, staged on main, unreleased** (breaking; see CHANGELOG Breaking block)
- [x] **PR #317** non-root sandbox — **MERGED `b4f21b4` 2026-08-30** (stdin delivery + import-regression fix pushed to the fork; CodeQL 145/146 dismissed; #157 stays open); **#336 `--read-only` shipped same day (PR #339, `5bed8d5`)**; follow-up **#338** (configurable sandbox uid)
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
  already died this way twice). **PR #191 CLOSED 2026-08-26** as unverifiable; #172 stays open; reopen when a sandbox exists
- [x] Daily triage routine live (`trig_011HVR6j4c5hDR2fj7k3ujxC`, 7am local) — #202 merged. **Prompt
  patched 2026-07-31**: merging a brief closed #172, because it described another PR as `fixes #172`
  and GitHub parses closing keywords anywhere in a merged PR body. Routine now forbids them *and*
  greps its own output before opening the PR (#172 reopened)
- [x] Issue #142 → FastMCP 4 / MCP SDK 2 migration complete: dependency
  constraints and lockfile upgraded, protocol-model reads use native snake_case,
  and CI runs with the temporary camelCase compatibility bridge disabled
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
  open for khagyard's student-token retest from main (their test course still has orphan topic 674). **#283 CLOSED 2026-08-26** on khagyard's confirmation
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
- [x] Release **v1.13.0** (2026-09-27): GHSA-hmr8 fix (`ALLOWED_WRITE_TOOLS`, two-step `send_conversation`, read-only `get_conversation_details`, syllabus token fixes), production deploys only on release tags (#417). All five channels verified. Advisory still to publish

## Roadmap
- [ ] Grok/xAI integration research and pilot — verify the current official path for third-party
  tools, connectors, bots, or MCP servers; document registration, hosting, authentication, review,
  and cost requirements; then test the nearest supported integration path. If Grok still has no
  public plugin or MCP registry, record that boundary and revisit when xAI publishes one.
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
- [ ] **2026-09-06 security review follow-ups** (Codex xhigh): the branch merged as PR #360 on 2026-09-12 (shared-server exports refused over HTTP, logged URL credentials redacted). Check `docs/superpowers/plans/2026-09-06-security-review-followups.md` for items #360 did not cover before closing this.

# Session History

Archived session log entries from canvas-mcp CLAUDE.md.

## Session Log

### 2026-06-21 — public-site doc leak fixed + hosted access locked down + cohort onboarded
- **🔒 Fixed a live exposure:** gitignored local-only ops/compliance docs inside `docs/` were being
  served publicly by Cloudflare Pages (`wrangler pages deploy docs/` ignores `.gitignore`). Moved
  `ops-*.local.md` + `compliance/` → `internal/` (outside the publish dir), added `docs/.assetsignore`
  backstop, gitignored `internal/*.local.md` + `internal/compliance/` (commit `796d352`). **Stale CDN
  copies persist on the custom domain until the Pages-layer cache TTL (≤7d) — zone purge can't evict
  it; not fixable from this repo.** Plan: `.claude/plans/post-exposure-remediation.md`.
- **Access control:** `MCP_ENTRA_ALLOWED_OIDS` was empty (= any UIUC tenant user). Locked to an
  explicit **7-OID allowlist on both slots** (operator + Lalitha/Challen/AdamKing/Ashish/Cheng/Jim).
  Rationale captured in the plan: it's **not** a confidentiality control (BYO-token = caller only sees
  own data) — it's a FERPA-scope/abuse control **while the security/privacy review is pending**; open
  it up after. CAE gotcha resolving emails→OIDs: needed `az logout && az account clear && az login`.
- **Dogfooding:** swapped user-scope Canvas MCP from local stdio → hosted `canvas` (mcp-remote/Entra)
  to mirror faculty. Verified login end-to-end (operator not locked out; reached Summer AI Studio 69366).
  **Hosted exposes 85 tools vs local 92** — code-exec (2) gated in HTTP mode + student `get_my_*` (5)
  filtered by educator role. Memory: `project_hosted_canvas_mcp_as_default_client.md`.
- **Onboarding doc + cohort email** (`internal/ops-faculty-onboarding.local.md`, `internal/compliance/`):
  added the allowlist requirement + *why*, the Canvas-token request link
  (answers.uillinois.edu/illinois/internal/150325), and the 85-vs-92 toolset note. Emailed the 6 (BCC)
  via Outlook compose (reviewable, not auto-sent).
- **Easier install — hosted `.mcpb` BUILT:** `internal/mcpb-hosted/` (GITIGNORED — has the private
  endpoint) holds a 2nd Desktop Extension that wraps `mcp-remote` via a tiny `index.cjs` launcher +
  a `canvas_token` user_config field. Built `canvas-mcp-hosted.mcpb` (gitignored), shim smoke-tested.
  Distinct from the repo-root `manifest.json` (the LOCAL/stdio python extension). Distribute PRIVATELY.

### 2026-06-17 — mcp-remote blocker RESOLVED + app→`canvas-mcp` + branch→slot CI
- **🏁 The `AADSTS9010010` blocker is gone — verified live.** DNS landed (CNAME + asuid), bound the private custom domain + GeoTrust managed cert to the app; PRM `resource` now == the registered App ID URI, and added that URI to Easy Auth `allowedAudiences` (RFC 8707 token `aud`). Ran `mcp-remote` end-to-end against the custom domain: token exchange + MCP session succeed. (Endpoint/IDs in gitignored `internal/ops-hosted.local.md`.) **All clients (Claude Desktop/Code, Cursor, Codex, VS Code) work.**
- **App renamed `gies-canvas-mcp` → `canvas-mcp`** (Azure can't rename → recreated; house-consistent bare name like mindforum/uniquick/illinihunt). ITP had typo'd the CNAME to `canvas-mcp.azurewebsites.net` (no `gies-`) — instead of asking them to fix it, adopted the cleaner name (was globally available). Old `gies-canvas-mcp` + `gies-canvas-mcp-staging` apps deleted.
- **Branch→slot CI shipped (#128, #129):** `main`→Production, `staging`→staging slot; build→push ACR→`azure/webapps-deploy`. Auth via ACR creds + publish profiles (no SP — sidesteps Owner-only RBAC). Gotcha hit + fixed: enable SCM basic-auth or deploy fails "Failed to get app runtime OS".
- **Standardization (A/A/A):** two blessed templates — Container (canvas-mcp, illinihunt) + Code (mindforum); direct branch→slot (not swap); recorded the pattern in the `illinois-azure-container-deploy`/`cli-deploy` skills. canvas-mcp ↔ illinihunt share the container backend; mindforum is the Node-code template.
- Also merged: **#126** `check_enrollment`; doc-synced it across AGENTS/README/manifest (tool count stayed 90 — was off-by-one).
- **Claude Desktop Extension (`.mcpb`)** scaffolded (uv runtime; `manifest.json` + `.mcpbignore` allowlist + `scripts/build-mcpb.sh`) and **distributed via GitHub Releases** (`create-release.yml` stamps the tag version + attaches the bundle). Install tested in Claude Desktop. README "Install as a Desktop Extension" section added.
- **Released v1.4.0** — GitHub Release + `.mcpb` + PyPI + MCP Registry + hosted server + Cloudflare website all live. (Publish-race recurred; rerun needed *after* PyPI returns 200 — memory updated.)
- **Sanitized the public repo:** moved hosted-deployment ops (URL, Entra IDs, key-holder names) → gitignored `docs/ops-hosted.local.md`; untracked `docs/compliance/` email drafts (kept local); deleted DNS correspondence files. Repo is PUBLIC — keep the hosted endpoint out of tracked files.
- **Outreach:** faculty onboarding doc (`docs/ops-faculty-onboarding.local.md`, hosted-only, human+agent readable). Challen reply **sent** (him only; offered demo + linked the Extension + attached setup). Mark Reynolds email **staged in Outlook** (Canvas service owner; security architecture + review ask) — needs his address before send.
- Next: (1) **send Mark Reynolds email** (confirm address). (2) **AcrPull grant** (Adam, `internal/compliance/email-adam-acrpull-entra.txt`) → re-enable MI pull. (3) Test `.mcpb` on **Windows** (pydantic compiled-wheel risk). (4) Wire **illinihunt CI** from the documented container pattern. (5) GRC/Cybersecurity compliance emails.

### 2026-06-14 (cont.) — Entra v2 cutover + custom-domain pivot + enrollment tool
- **Security pass → 3 PRs merged.** Deep-research evaluated UIUC/FERPA policy (Canvas records = "Sensitive"/DAT01; FO-36→IT05 needs NetID/Entra identity, not a shared key). **#123** fail-closed the HTTP gate (refuses to start ungated unless `MCP_ALLOW_UNAUTHENTICATED=true`); **#124** added the Entra-OAuth plan + `docs/SECURITY-COMPLIANCE.md` (verified vs. open findings) + trimmed VPN as a rejected non-identity control; **#125** built the **Entra platform-auth header-reader** (App Service validates the token, app reads `X-MS-CLIENT-PRINCIPAL-ID`; codex-reviewed twice — caught a P1 fail-open + a P2 PII-in-logs, both fixed). Confirmed Azure OpenAI (in-tenant) is the LLM, not consumer Claude.
- **Cut staging over to Entra (live, `az`-driven):** created 2 Entra app regs (API + pre-authorized public client; IDs in the gitignored ops doc), enabled Easy Auth API mode (`Return401` + PRM), validated 401+RFC9728 challenge on the wire, container healthy.
- **🔑 Key blocker discovered via live test:** `mcp-remote` (and Claude Desktop native) **can't complete the Entra token exchange** — `AADSTS9010010`; the MCP SDK sends the app-URL `resource` which Entra rejects (not a registered App ID URI). Known/open bug (`geelen/mcp-remote#217`, `claude-code#52871`); **VS Code native works**. Two research agents confirmed it's unfixable client-side.
- **Pivot (no proxy): verified custom domain.** Entra rejects `*.azurewebsites.net` App ID URIs but **accepts `illinois.edu` subdomains** — registered a private custom-domain App ID URI (tested live; URL in the gitignored ops doc). Confirmed via sibling repo that `disruptionlab.illinois.edu` is a live IPAM zone and UniQuick already runs on it (ITP actions DNS requests silently/fast). DNS landed 2026-06-17.
- **Also built: `check_enrollment` (PR #126, open)** — data-minimizing "is NetID enrolled in course X?" (core + MCP tool, 10 tests) for UniQuick gating; reads roster with `skip_anonymization=True` for the match, returns only a boolean. Deferred: REST endpoint + teacher-token-sourcing decision; tool docs.
- Next: (1) **send `docs/tech-services-dns-request.txt` to consult@illinois.edu**; when DNS lands → bind hostname+cert + repoint PRM scope/`allowedAudiences` to the new hostname → re-test mcp-remote (should pass) → tighten `MCP_ENTRA_ALLOWED_OIDS`. (2) Merge #126. (3) Adam AcrPull grant (`docs/compliance/email-adam-acrpull-entra.txt`). (4) Send the GRC/Cybersecurity compliance emails (recipient/title edits pending).

### 2026-06-13 → 06-14
- **Shipped #115 v1 (token-only fail-closed HTTP auth + key gate) and deployed it to Azure staging.** Three Codex passes drove it: Architect GO on the "token-only + server-pinned URL" model, an xhigh end-to-end plan, and a diff-level review that caught a secure-by-default Dockerfile gap (code-exec defaulted on for the network-facing image → fixed). Core problem solved: the old HTTP credential path was all-or-nothing — a missing/rejected per-request header silently fell back to the *server's* token, mis-attributing actions to the operator (FERPA/audit failure); #118's `*.instructure.com` SSRF regex made it worse by rejecting the `canvas.illinois.edu` vanity domain.
- **Code (PR #121, admin-merged, CI green + twice codex-reviewed clean):** new `is_http_request_active()` marker so the env-fallback only fires in stdio; all Canvas-touching paths route through one `canvas_authenticated_client()` resolver (caught a 6th leak path — `files.py` downloads used the server-token global client); middleware is token-only (X-Canvas-URL ignored, 401 on missing token), startup guard forbids `CANVAS_API_TOKEN` in HTTP mode; `MCP_ACCESS_KEYS` constant-time gate; Dockerfile launches streamable-http on the injected port with code-exec off by default. 405 tests pass.
- **Deploy:** built from main, live at `gies-canvas-mcp-staging`. Verified both gates over HTTPS (no-key → 401, key-but-no-token → 401). Discovered the app had never actually served (prior Jun 9/10 images crash-looped on `ACRTokenRetrievalFailure`); root cause = MI lacks `AcrPull`; worked around with ACR admin-user creds + enabled `httpsOnly`.
- **Validated + onboarded (6/14):** TA **Lalitha** connected via Claude Desktop + `mcp-remote` and confirmed it works — first real positive end-to-end test. Per-user keys minted for **Lalitha, Ash, Cheng (L&D)**; per-person onboarding `.txt` files on `~/Desktop`. Corrected the AcrPull authority: it needs a **subscription Owner = Adam King** (verified via RBAC the whole app team is Contributor-only).

### 2026-06-05
- **Retired the public hosted MCP server end-to-end + specced the Gies/Azure replacement.** Brainstormed the "move repo to gies-ai-experiments / transition to Azure" ask and decomposed it into three separable concerns — code ownership (stays personal; a GitHub transfer would break PyPI Trusted Publishing + the `io.github.vishalsachdev` MCP Registry namespace for zero benefit → **no transfer, no fork**), institutional *operation* (the Azure project), and inference (Azure OpenAI credits). Goal landed on: a Gies-operated, Azure-hosted, SSO-gated deployment for staff using downloaded MCP clients (Codex/Claude Desktop/VS Code/Cursor).
- **Security teardown of `mcp.illinihunt.org`** (was a workshop-only instance): review found it live with **no auth gate**, `execute_typescript` (code-exec) exposed publicly 🔴, unvalidated `X-Canvas-URL` (SSRF) 🟠, on a `0.0.0.0:8819` systemd listener. Decommissioned reversibly: `systemctl stop/disable canvas-mcp.service` (port closed), nginx vhost symlink removed, Cloudflare `A mcp` record deleted (NXDOMAIN; `proof-mcp`/`canvas-mcp` siblings untouched).
- **Filed issue #115** — dev-team-ready v1 spec: Azure Container Apps, lightweight per-user **key gate** (proof-vps pattern, not full OAuth), BYO `X-Canvas-Token` header, hardening as acceptance criteria (disable code-exec, pin `CANVAS_API_URL=canvas.illinois.edu`, ingress-only), phased toward v2 OAuth/Entra/ChatGPT-Edu-web-connector. Confirmed ChatGPT Edu *web* connectors are OAuth-only (→ v2); downloaded clients support custom headers (→ key gate fine for v1).
- **Cleaned every surface that referenced the dead server**: auto-memory (`reference_vps_deploy.md` + MEMORY.md index → DECOMMISSIONED), website (removed "Hosted Server (Recommended)" from `docs/index.html` + learning-designer guide; local install now primary; redeployed to Cloudflare), and README/AGENTS/CHANGELOG (accurate "retired" notes + dated `### Security` disclosure — feature *not* disabled, it was a deployment-posture issue, package unaffected).
- **impact.json refresh** committed + deployed (stars 128→141, forks 34→38, data through 2026-06-01) + cron heartbeat sentinel.
- Next: Backlog triage (module templates, bulk creation, page versioning) and Issue #106 (mypy cleanup) remain the standing queue. **#115 (Gies/Azure hosted deployment)** is now a live thread — picked up if/when the Gies dev team or demand materializes.

### 2026-05-14
- **Cleared both v1.3.0 follow-ups from the carryover queue** by working through the auto-bot maintenance reports (#95/#101/#102). Started with a Codex plan-review pass on the proposed batches — that surfaced two real corrections before any code: the bot was recommending `setup-python@v4 → @v5` but current is `@v6` (Node 24 vs 20), and Batch 1 needed to be a PR, not a direct-to-main push, because of the lockfile regeneration. Final plan: two PRs, both admin-merged after green CI + Codex code-review.
- **PR #105 (`chore: housekeeping`)**: Added `ruff>=0.9.0`, `black>=25.0.0`, `mypy>=1.15.0` to `[dependency-groups] dev` — all three were already configured in `[tool.*]` sections but never installable; fresh contributors tripped the pre-commit hook. Removed unused `requests>=2.33.1` from runtime deps (verified zero `import requests` across `src/`/`tests/`/`scripts/`/`tools/`/`.github/`). Bumped `actions/setup-python` from `@v4`/`@v5` to `@v6` across all 5 workflow files. Applied `ruff --fix` to clear 7 pre-existing unused-import warnings. 382 tests + ruff clean post-change.
- **PR #107 (`ci: split publish-mcp`)**: Split the single `publish` job into `publish-pypi` (build/test/upload, exposes resolved version as a job output with leading-`v` stripped) and `publish-registry` (`needs:` PyPI job; polls `https://pypi.org/pypi/canvas-mcp/<version>/json` up to 12× × 30s = 6 min ceiling before calling `mcp-publisher publish`). Eliminates the rerun-after-each-release operational burden caused by the CDN-propagation race that hit v1.3.0. Codex code-review returned zero findings.
- **Issue #106 filed**: Adding mypy as a real dev dep exposed 186 pre-existing type errors across 19 files (mypy was configured in `[tool.mypy]` but never installable, so no one ever ran it). Tracked for incremental module-by-module cleanup; out of scope for the housekeeping PR.
- **impact.json refresh**: A 2026-05-11 auto-refresh from the impact-stats skill was waiting at session start (stars 120→128, new referrers from search.brave.com and mcpservers.org). Committed direct to main and deployed to Cloudflare Pages.
- Next: Backlog triage (module templates, bulk creation, page versioning) — same as last two sessions. After that, Issue #106 (mypy cleanup) and the two test-coverage gaps from the maintenance reports (`discovery.py`, `message_templates.py`).

### 2026-05-07
- **Instructure/Canvas breach advisory** (no code changes): ShinyHunters claimed exfiltration of ~275–280M records / 3.65 TB from Instructure across ~8,800 institutions; ransom deadline was today. Exposed: names, emails, student IDs, **private Canvas Inbox messages**. Not exposed (per Instructure): passwords, DOB, gov IDs, financial. Second Instructure breach in 8 months (Sept 2025 was Salesforce social-engineering). **Project impact: none** — canvas-mcp is a client of the Canvas API, not affected by the data exfil. `CANVAS_API_TOKEN` is user-issued via Canvas UI and almost certainly not in the exfil path; rotation is hygiene, not required. No advisory needed in repo docs.
- **Stats refresh deployed**: Committed pre-session `docs/data/impact.json` refresh and pushed to Cloudflare Pages.
- Next: Backlog triage (module templates, bulk creation, page versioning) — unchanged from last session. Two v1.3.0 follow-ups still open: split `publish-mcp.yml` (PyPI + MCP Registry jobs with propagation poll), add `ruff` to dev deps in `pyproject.toml`.

### 2026-05-02
- **Released v1.3.0** (commits `cff934c` + `c2f1438`, tag `v1.3.0`): Bundled four already-merged PRs into a coherent release — `create_rubric` (#100, bracket-notation form-data finally working), `read_course_file` (#90, @DomBarker99), event-loop fix on user-scoped tools (#99, weakref-tracked client/semaphore), and bulk-delete safety (#96, default cap of 25 + dry_run). Drafted CHANGELOG.md (Keep-a-Changelog format) before bumping versions — that scope-pass caught the bulk-delete behavior change for callers passing >25 IDs and got it into the release notes. Bumped 5 release-checklist files; 382 tests pass at 1.3.0; tool count 88 → 90.
- **CI publish race surfaced**: `publish-mcp.yml` runs PyPI upload + MCP Registry publish in one sequential job. The Registry's PyPI lookup raced PyPI's CDN propagation and 404'd. `gh run rerun --failed` succeeded immediately on retry — no code change. Added a follow-up: split into two jobs with a PyPI-propagation poll between them. Also surfaced a Node 20 deprecation warning for `actions/checkout@v4` + `actions/setup-python@v5` (force-upgraded June 2026).
- **Session prep**: Pulled 3 backlog commits (#96, #99, #100), committed two carry-forward dirty files (`AGENTS.md` policy additions for memory lookup + external-action approval; `impact.json` April 27 stats refresh). Deleted two 66-day-old `.claude/plans/` files whose targets had all shipped. Cloudflare Pages deployed manually with `unset CF_API_TOKEN && wrangler pages deploy` (the documented workaround for the deprecated env var).
- **Pre-commit hook surprise**: Fresh venv didn't have `ruff` installed; hook called `uv run ruff` which spawn-failed with "No such file or directory." Installed via `uv pip install ruff`. Should be a dev dep in pyproject.toml.
- Next: Backlog triage (module templates, bulk creation, page versioning). Address the two follow-ups in Current Focus before the next release.

### 2026-04-21
- **Merged PR #93** (`chore/drop-unused-fastmcp-dep`, commit `eebac6a`): Weekly maintenance report #91 flagged fastmcp 2.14 → 3.x as a 🔴 high-priority upgrade. Investigation showed the repo imports `from mcp.server.fastmcp import FastMCP` (bundled FastMCP 1.0 inside the official `mcp` SDK v1.26.0) — zero files import the standalone `fastmcp` package. The `fastmcp>=2.14.0` pin was phantom. Replaced with explicit `mcp>=1.26.0,<2` (upper bound per Codex plan review), regenerated uv.lock. Net −794 lines, pruned ~30 unused transitive deps (authlib, cyclopts, pydocket, py-key-value-aio, rich, typer, websockets, etc). All 363 tests pass, stdio + streamable-http transports verified, CI 8/8 green. Admin-merged through branch protection.
- **Codex integration**: Used `codex:codex-rescue` subagent for plan review (caught need for upper bound + "intentional, not to-be-re-flagged" framing) and `/codex:rescue` for post-push diff review (APPROVE with evidence from uv.lock and upstream mcp docs).
- **Key learning**: When a maintenance bot flags a dep upgrade, first verify the dep is actually imported. Weekly-report "🔴 High" can be a false positive on a phantom pin.
- Next: Tag v1.3.0 release for `read_course_file` (still pending from prior session). Backlog triage. Note: `docs/data/impact.json` still dirty from prior session. Deleted the `canvas-mcp-meets-skills-sh` article draft as not relevant.

### 2026-04-18
- **Merged PR #90** (`read_course_file`, external contributor @DomBarker99): Returns Canvas file content as base64 in MCP response — complements `download_course_file` which writes to the server filesystem (useless for remote MCP topologies). Dual size-cap enforcement (reported + mid-stream), server-side `READ_FILE_MAX_SIZE_MB` clamp. 363 tests pass. Added @DomBarker99 to contributors list. Tool count 87 → 88; educator role 86 → 87.
- **Repo hygiene audit (-9,260 lines across 5 priorities)**: P0 archived legacy code + rubric plans -3,937. P1 orphan docs (SECURITY_*, course_doc_template, impact-metrics-2026-03-20) -2,421. P2 UIUC security cluster (self-referencing island, no user-facing in-links) -914. P3 duplicate student/educator guides (kept HTML on canvas-mcp.illinihunt.org, rewrote 10 links) -842. Untracked `.claude/` (Claude Code per-project working dir) -1,021.
- **Misc cleanup**: Moved `session-history.md` → `docs/`. Added defensive `.gitignore` entries for `.DS_Store`, `Thumbs.db`, editor swap files. Cloudflare Pages redeployed with tool count 88.
- **CLI DRY refactor** (`cli/lib/config-writer.js`, commit `6f24719`): Collapsed `configureJsonClient` + `configureCodexClient` into a single `updateConfigFile` helper taking a `mutate` callback; format-branching (JSON vs TOML) now happens once. −8 net LOC, public API unchanged, 7 tests pass. Triggered by a PR-review tool flagging duplication; dismissed the tool's CRITICAL "hardcoded secrets/injection" finding as a false positive (no secrets, all writes go through `JSON.stringify`/`TOML.stringify`).
- Next: Tag v1.3.0 release for `read_course_file`. Publish decision on `articles/2026-03-01-canvas-mcp-meets-skills-sh` (staged locally, untracked). Backlog triage.

### 2026-04-10
- **Rubric tool rationalization** (PR #86): Reduced rubric tools 11 → 6 (total 92 → 87). Deleted 3 broken/unused tools, merged 3 overlapping reads into `get_rubric`, renamed 3 for clarity, moved `bulk_grade_submissions` to assignments.py. Net -540 lines from rubrics.py.
- **Stale markdown cleanup** (PR #87): Deleted 11 fully-implemented plans, satisfied specs, and dead artifacts. -4,766 lines.
- **Codebase health audit**: Analyzed all 92 tools against session history — ~50 had no evidence of use. Rubric tools were worst case (2 disabled, 3 undocumented, 3 overlapping).
- Next: Consider rationalizing peer review tools (9 tools, similar pattern). Deploy docs to Cloudflare Pages (tool count 87). Backlog triage.

### 2026-04-09 (late session)
- **PR #84 merged**: Role-based tool filtering from external contributor (Promithius-DR). Code reviewed, found 2 bugs (validate_config not resetting invalid role, --config showing wrong role), fixed and merged with --admin.
- **PR #85 merged**: Windows tsx fix (issue #83). Reviewed Claude + Codex feedback, addressed P1 (npx fallback re-introduces bug) and P2 (global before local resolution order), merged.
- **CI consolidation**: Merged auto-update-docs into claude-code-review (1 Claude call instead of 2), removed security-summary job. 11 → 8 checks per PR.
- **GitHub Actions re-enabled**: Fixed fork-aware checkout in workflows, added OAuth token check.
- **Cleaned up**: Deleted stale github-pages deployment environment.

### 2026-04-09 (earlier session)
- **Accessibility scanner expanded (4 → 20 checks)**: Upgraded `_check_content_accessibility()` based on DesignPLUS/Pope Tech/WAVE checklist. 20 checks run on every scan.
- **BADM 350 remediation**: Applied fixes to course 68238 — `scope="col"` to 118 `<th>` elements, contrast fixes, `kl_` → `dp-` class migration.

### 2026-04-06
- **Security: PR #81 review & merge**: CWE-22 path traversal fix + codebase-wide file I/O hardening (4 additional sites).
- **Housekeeping**: Archived 6 stale session log entries, deleted 2 completed plans.

### 2026-03-20
- **InstructureCon 2026 proposal**: Drafted CFP for InstructureCon26 (Louisville, July 21-23).
- **Impact tracker implemented**: `scripts/collect-impact-stats.sh`, live website section, launchd plist.

### 2026-03-13
- **Event loop bug fix**: Fixed "Event loop is closed" on first MCP tool call.
- **Concurrency limiter**: `asyncio.Semaphore` in `make_canvas_request()` (default 10).

### 2026-03-12
- **CLI npm package**: Published `canvas-mcp` v1.1.0 to npm — `npx canvas-mcp setup` wizard.
- **Workshop page**: Created `canvas-mcp.illinihunt.org/workshop`.

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

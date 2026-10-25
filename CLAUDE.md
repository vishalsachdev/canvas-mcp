# CLAUDE.md

Guidance for developing the Canvas MCP server. Agents *using* the server: see [AGENTS.md](./AGENTS.md).
Design: [internal/architecture.md](internal/architecture.md). Long-form rules and the reasons behind them: [internal/dev-reference.md](internal/dev-reference.md). Completed work: [internal/project-history.md](internal/project-history.md), `CHANGELOG.md`.
Codex reads `AGENTS.md`, not this file; its "Developing this server" section points here, so keep development rules in this file only. Paths, flags, symbols and issue states below were checked on 2026-09-30.

## Commands
- Install `uv pip install -e .`; run `canvas-mcp-server` (`--test`, `--config`); `.env` holds `CANVAS_API_TOKEN` and `CANVAS_API_URL`.
- Before committing: `uv run python -m pytest tests/ -v -rf`. TypeScript changes: `npm test` and `npm run build`.

## Git Workflow - ASK FIRST
- Before a feature or significant change, ask: feature branch or `main`? Defaults: new tool `feature/`, bug `fix/`, docs or typo may go straight to `main`. Prefixes: `feature/`, `fix/`, `docs/`, `refactor/`.
- The primary checkout stays on `main`, clean and read-only. One PR = one sibling worktree `canvas-mcp-<slug>` from `origin/main`; never reuse it for another issue; remove it and the branch (local and remote) after merge.
- After a sibling PR merges, rebase surviving worktree branches and rerun tests. Before tagging, run the suite in the primary checkout on the merged commit (its `.env` sets a token that worktrees and CI lack).
- `main` requires a PR plus `test-enhancements` and `lint`; the admin can bypass the review requirement.
- Run `./scripts/install-hooks.sh` once per clone. `fixes|closes|resolves #N` mid-sentence in a commit or PR body closes the issue on merge: rephrase (`closed [issue 172]`) or set `ALLOW_CLOSING_KEYWORD=1`. A trailer that opens a line (`Closes #173`) is allowed.
- Release steps and publish-race fixes: [internal/release-checklist.md](internal/release-checklist.md). Breaking changes need a minor bump.

## Coding Standards
- Type hints on every function; PEP 604 unions (`X | Y`), enforced by ruff UP.
- Tools use `@mcp.tool()` with `@validate_params`, and every tool carries annotations (`tests/test_tool_metadata.py` fails a bare decorator).
- All Canvas calls are async and go through `make_canvas_request()`; paginate every list endpoint.
- Course identifiers are `str | int` resolved with `get_course_id()`; dates go out through `format_date()`.
  Code that needs a numeric course ID (paths, context codes, comparisons) uses `resolve_numeric_course_id()`, which returns `(id, error)` and never yields an unvalidated string. `get_course_id()` matches the same way but keeps its pass-through fallback on a miss.
- Canvas POST/PUT needs `use_form_data=True`, `/conversations` included.
- Errors: dict tools return an `"error"` key; string tools return `"Error ..."`. `modules.py` and `accessibility.py` return JSON-stringified errors; keep the local convention.
- Privacy: student IDs preserved, names anonymized at the client layer (`_should_anonymize_endpoint()`); a new endpoint must be checked against the tier rules.
- Show course codes, not IDs, in user-facing output; handle published and unpublished states.

## Testing and behavioral evidence
- New tools need meaningful automated coverage: success, failure, boundary and safety behavior.
- A reproducible bug gets a failing regression first; watch it fail for the intended reason.
- Assert outgoing request contracts and forbidden side effects, from an independent requirement, not from the implementation's own output.
- Use a real client with controlled HTTP transport when the risk is serialization, retries, pagination or error classification.
- Never send live Canvas writes to verify a patch. Never weaken an assertion to get a green run.
- Lean/TLA+ (`verify/`) only for consequential state, ownership or termination invariants; pair with implementation regressions.
- Report what was verified, what failed and what was skipped.

## Documentation Maintenance
- Source of truth: agents `AGENTS.md`; humans `tools/README.md`; machine `tools/TOOL_MANIFEST.json`; `README.md` is the entry point.
- New tool: update `tools/README.md`, then `AGENTS.md`, then `TOOL_MANIFEST.json`. Touch `README.md` only for a major feature. No tool usage docs in this file.
- `docs/` is the public Cloudflare Pages root and deploys manually (`wrangler pages deploy docs/`); nothing internal goes there.
- The site's version, tool and skill counts and GitHub stats come from `scripts/sync_site_facts.py` (CI runs `--check`): change the source, then run it; never hand-edit those numbers.
- `internal/` is deny-by-default in `.gitignore`; un-ignore only a file meant to be public. `internal/session-history.md` stays untracked.
- Triage briefs are tracked: never record a collaborator's affiliation, evaluation status, timeline or competing products. Name the person and the technical issue only.

## Hosted Deployment
- A private, Entra-gated Azure instance serves Gies course staff. Its URL, app IDs, deploy details and key holders stay out of this repo; they live in the gitignored `internal/ops-hosted.local.md`.
- HTTP mode: each caller sends `X-Canvas-Token`; `CANVAS_API_TOKEN` must never be set (startup guard); read-only unless `ALLOWED_WRITE_TOOLS` is set.
- Merging to `main` does not deploy production. It deploys on a `v*` tag or `gh workflow run deploy-prod.yml --ref main`; `staging` deploys on push.

## Adoption numbers
- Never print a PyPI download count. Quote stars, forks and contributors, re-pulled from the GitHub API that day, with the date.
- Do not repeat "over 18,000 clones" or "UMich selected it as sole candidate" without a primary source.
- Do not imply a campus security review: the only Illinois artifact is Adam King's LRA, and the public hosted server is retired.

## Current Focus
- [ ] **#157** sandbox egress is mitigated, not closed (self-hosted only; `execute_typescript` is disabled on hosted). Needs an egress proxy or network namespace.
- [ ] **#236** OAuth2 developer-key flow: additive only, blocked on admin access to pilot a scoped key.
- [ ] **#172** Canvas Quizzes tools: blocked on a New-Quizzes-enabled sandbox (PR #191 was closed as unverifiable).
- [x] **#418 to #421** shipped (#438, #437, #436, #435; #421 part 2 via #442 and the anonymous-update refusal via #446; issue closed by 2026-10-07).
- [x] **v1.16.0** released 2026-10-24 (PR #530, tag on `b3f06c7`; Release + `.mcpb` with attestation, PyPI wheel + sdist with provenance, Registry latest, prod `azure-gies-b3f06c7` per the Kudu docker log, site from the tag plus current stats): security release; GHSA-hmr8, GHSA-7pp5, GHSA-7mj9 and GHSA-qf6c published 2026-10-25 04:11 UTC, CVEs requested (IDs pending). Breaking: the local sandbox needs Node.js 22.18+.
- [ ] **fastmcp** 4.0.3 has GHSA-7xgj-8392-5q4r and GHSA-vqqp-x5qm-5qp4 (medium, fixed in 4.1.2); the dependency scan fails on `main` since 10-24. Handed to control for a 1.16.1 lock bump. Dependabot opened #531 (fastmcp) and #532 (fastmcp-slim) on 10-24, both mergeable with checks green; each rewrites `uv.lock` from revision 3 to 5, the same as `uv lock --upgrade-package fastmcp`.
- [ ] **OSS Verify** theorem-labs/oss-verify#8: Theorem's P3 change done (`326cb40`, compares the kept text; `--twice` passed), reply posted 10-24. Waiting on a person at Theorem (criticality 0.59 is below their 0.7 rubric line). Theorem statements first; proofs wait on their verified Python runtime. Findings go privately to vishal@illinois.edu.
- [ ] **OSS Scanner** anthropics/oss-scanner#1115: enrolled 2026-10-24 (terms and CLA signed at Vishal's direction, all checks green); waiting on Anthropic's human review.
- [ ] Hosted ops: remove `llkarri2` from the allowlist; usage telemetry is not retained (see Session Log).
- [ ] Watch, no owner: Agent Plugins packaging (blocked on credential delivery; triggers in project-history).

## Roadmap
- [ ] Grok/xAI integration research and pilot.

## Backlog
- [ ] Module templates; bulk module creation from JSON/YAML; module duplication across courses.
- [ ] Page templates; bulk page creation from markdown; page versioning tools.
- [ ] 2026-09-06 security review follow-ups: check `docs/superpowers/plans/2026-09-06-security-review-followups.md` for items PR #360 did not cover.

## Session Log
> Full history: `internal/session-history.md`, local-only and untracked since 2026-08-20. Do not re-add it to git.

### 2026-10-24 15:00 → 23:15 CDT — v1.16.0 security release; four advisories published; OSS Verify P3; OSS Scanner enrolled
- **OSS Verify #8:** Theorem's review agent (`sjawhar-agent[bot]`; every PR comment so far is from a bot) and Codex asked P3 to compare text, not length. Fixed in `326cb40`: the new mutant passes the old P3 on all 20 seeds and fails the new one on 10. `--twice` passed on m2max (canvas-mcp `de61842`); pushed; reply posted. Theorem's #16 (merged) cites our enrollment on binary size: our plain `.text` is 3.77 MB against their 1 MB fast lane.
- **OSS Scanner #1115** opened (terms and CLA at Vishal's direction); all checks green. Vishal submitted the **Claude for Open Source** application (criticality path).
- **Advisories:** GHSA-7pp5 (local sandbox runs Node under `--permission`; Codex stopped on OpenAI's cyber filter, so Claude implemented it; three Codex review rounds to APPROVE), GHSA-7mj9 (Canvas token limited to the Canvas origin), GHSA-qf6c (Windows warning; documented limitation, Vishal's call), GHSA-hmr8 (`read_course_file` contents fenced; text rewritten). Triage reports accepted, CVEs requested, all published 04:11 UTC. Record: `internal/security/2026-10-24-advisory-fixes.md`.
- **v1.16.0** (PR #530 → `b3f06c7`, tag 23:06 CDT). The combined branch needed `59b20ae` (tests patched a renamed client) and `63fba73` (Windows: SYSTEMROOT and WINDIR in the sandbox environment; Node cannot start without them). Checked each artifact: Release and `.mcpb` 1.16.0 with attestation; PyPI wheel + sdist with provenance; Registry 1.16.0 latest; prod Kudu log "Site is running with deployment version: b3f06c7…"; site live (v1.16.0, 128 tools, current stats).
- **Impact stats** refreshed (2026-10-24: 308 stars, 99 forks, 27 contributors) and deployed; `docs/data/impact.json` (10-19 and 10-24 history) committed at wrap-up.
- **Michigan:** Zhen Qian asked for citation text for the 10-30 Michigan Canvas User Conference talk; Vishal sent the reply 22:06 CDT (Sent Items). U-M's public M-Connector page does not name canvas-mcp, so do not advertise the adoption yet.
- **Next:** control: fastmcp 1.16.1 (Dependabot #531 and #532 are ready); CVE IDs (GitHub, up to 72 h); Theorem's review of #8; Anthropic's review of #1115; KKazuhaK's new PRs #533 and #534 (10-25); m2max keeps `~/code/oss-scanner` and image `oss-scanner-check/built:canvas-mcp` (2.83 GB) until #1115 merges (Vishal). Carry from 10-23: F6 token revoke (most urgent), F1/F7/F9 patch scan, Codex 10-23 follow-ups, #510 re-review, remove `llkarri2`, #489.

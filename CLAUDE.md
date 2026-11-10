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
  Code that needs a numeric course ID (paths, context codes, comparisons) uses `resolve_numeric_course_id()`, which returns `(id, error)` and never yields an unvalidated string. `get_course_id()` matches the same way and refuses unknown aliases; explicit `sis_course_id:` forms keep their validated pass-through behavior.
- Canvas POST/PUT needs `use_form_data=True`, `/conversations` included.
- Errors: dict tools return an `"error"` key; string tools return `"Error ..."`. `accessibility.py` and the read/structure tools in `modules.py` (`get_course_structure`) return JSON-stringified errors; the `modules.py` write tools return plain text; keep each function's local convention.
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
- `docs/` is the public Cloudflare Pages root and deploys manually with `scripts/deploy_site.sh` (a bare `wrangler pages deploy docs/` ignores `.assetsignore` and publishes `triage/`, `audits/`, `superpowers/`); nothing internal goes there.
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
- [x] **v1.16.0** released 2026-10-24 (PR #530, tag on `b3f06c7`; Release + `.mcpb` with attestation, PyPI wheel + sdist with provenance, Registry latest, prod `azure-gies-b3f06c7` per the Kudu docker log, site from the tag plus current stats): security release; GHSA-hmr8, GHSA-7pp5, GHSA-7mj9 and GHSA-qf6c published 2026-10-25 04:11 UTC. Breaking: the local sandbox needs Node.js 22.18+.
- [ ] **v1.16.0 advisory CVEs** — follow up on the four requested IDs in the [repository advisories](https://github.com/vishalsachdev/canvas-mcp/security/advisories).
- [x] **v1.16.1** [published](https://github.com/vishalsachdev/canvas-mcp/releases/tag/v1.16.1) 2026-11-05 UTC on GitHub and [PyPI](https://pypi.org/project/canvas-mcp/1.16.1/). The release locks FastMCP 4.1.2 (#531), requires `fastmcp>=4.1.2,<5` for fresh installs (#548), and includes #535, #541 and #542.
- [x] **v1.17.0** [published](https://github.com/vishalsachdev/canvas-mcp/releases/tag/v1.17.0) 2026-11-09 on GitHub and [PyPI](https://pypi.org/project/canvas-mcp/1.17.0/), tag on `fc2fad2`. Breaking: strict course identifiers (#567), `create_rubric` refuses an assignment that already has a rubric, and an empty Entra allowlist needs an explicit setting (#563).
- [ ] **OSS Verify** — enrollment merged in [theorem-labs/oss-verify#8](https://github.com/theorem-labs/oss-verify/pull/8). The HTML harness follow-up [#42](https://github.com/theorem-labs/oss-verify/pull/42) merged with independent parser checks and mutation cases still outstanding. Python proof work remains paused. Describe the project as enrolled and route findings privately to vishal@illinois.edu.
- [ ] **OSS Scanner** — [Anthropic's enrollment PR #1115](https://github.com/anthropics/oss-scanner/pull/1115) remains open pending human review.
- [ ] Hosted ops — revoke the F6 token and remove `llkarri2` from the allowlist ([#572](https://github.com/vishalsachdev/canvas-mcp/issues/572)). Usage telemetry is not retained.
- [ ] [#489](https://github.com/vishalsachdev/canvas-mcp/issues/489) — finish the caller-boundary audit for HTTP course-policy and discussion caches.
- [ ] Watch, no owner: Agent Plugins packaging (blocked on credential delivery; triggers in project-history).

## Roadmap
- [ ] Grok/xAI integration research and pilot.

## Backlog
- [ ] Module templates; bulk module creation from JSON/YAML; module duplication across courses.
- [ ] Page templates; bulk page creation from markdown; page versioning tools.
- [ ] 2026-09-06 security review follow-ups: check `docs/superpowers/plans/2026-09-06-security-review-followups.md` for items PR #360 did not cover.

## Session Log
> Full history: `internal/session-history.md`, local-only and untracked since 2026-08-20. Do not re-add it to git.

### 2026-11-09 to 11-10: PR queue cleared; 1.17.0 released; remote branches pruned
- 11-09: merged #576, #559, #552 (merge commit `087e04d`; #533 marked merged with it), #575, #545, #577, #578 and #579. PR 556 was shut without a merge: Python 3.15 is outside the test matrix, and Dependabot now skips that minor version.
- 11-09: released 1.17.0 on `fc2fad2`. Verified the Release and `.mcpb` attestation, PyPI with provenance, Registry latest, prod `azure-gies-fc2fad2` in the Kudu log, and the site. Both high-priority inbox items are in `_agent-inbox/done/`.
- 11-10: declined PR 580 (a README block that pointed to a third-party installer; the README documents each client's own configuration format only). Deleted 25 merged remote branches. The remote keeps `main`, `staging` and `copilot/feature-add-tools-for-canvas-quizzes` (the only draft for #172).
- **Next:** #510 waits on its contributor (six P2 findings, comment posted 11-09). Follow-up for three low-severity `get_my_submission_status` edge cases from the #545 review (`not_graded`, excused plus missing, null `submission_types`). Four normal and low inbox items are pending. The `canvas-mcp-unused-code` worktree is parked. A squash-merged branch never shows as merged in `git branch --merged`: compare the branch tip to the PR head before deleting it.

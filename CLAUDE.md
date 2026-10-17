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
- [x] **v1.14.0** released 2026-10-07 (PR #478, tag on `4696c16`; GitHub Release, PyPI, Registry, prod `azure-gies-4696c16` and site all verified): student tools from @KKazuhaK, guarded edits, group and anonymous discussion reads; contributors credited in CHANGELOG + README; site deployed.
- [ ] Hosted ops: remove `llkarri2` from the allowlist; usage telemetry is not retained (see Session Log).
- [ ] GHSA-hmr8: publish and request a CVE. GHSA-7pp5: decide (in triage since 07-04).
- [ ] Watch, no owner: Agent Plugins packaging (blocked on credential delivery; triggers in project-history).

## Roadmap
- [ ] Grok/xAI integration research and pilot.

## Backlog
- [ ] Module templates; bulk module creation from JSON/YAML; module duplication across courses.
- [ ] Page templates; bulk page creation from markdown; page versioning tools.
- [ ] 2026-09-06 security review follow-ups: check `docs/superpowers/plans/2026-09-06-security-review-followups.md` for items PR #360 did not cover.

## Session Log
> Full history: `internal/session-history.md`, local-only and untracked since 2026-08-20. Do not re-add it to git.

### 2026-10-16 16:31 → 20:40 CDT — hosted stays read-only; Cheng and Tomkin routed to local installs
- **Decision (Vishal, reaffirmed):** hosted stays read-only (`ALLOWED_WRITE_TOOLS=none`) until reviewers answer agent-infra#1; users who need edits run the local `.mcpb`/stdio server. Recorded in `internal/ops-hosted.local.md:30`; control told.
- **Usage evidence:** Graph beta `auditLogs/signIns` (interactive + non-interactive, appId = desktop client) for 09-16 → 10-16: 7 of 14 allowlisted users signed in (vishal, chengli8, tomkin, lhoussei, maryflah, ashleyn4, llkarri2). Cheng 13 interactive sign-ins (frequent re-auth); Tomkin 7× AADSTS50011 (non-`mcp-remote` client). The server itself still keeps no usage record.
- **Learned:** the ChatGPT desktop app runs local STDIO MCP servers (Settings → MCP servers; shares `~/.codex/config.toml`, see README Codex section). Only ChatGPT web / connectors cannot reach the hosted server (chatgpt.com redirect URI not registered, no per-user `X-Canvas-Token` header). A first draft wrongly said otherwise and was not sent. Untested: because ChatGPT desktop runs stdio, the hosted `mcp-remote` config may work there too; the Tomkin email says hosted "is not set up for ChatGPT", so test before repeating it.
- **Mail (Sent Items 20:36 CDT):** Cheng "Canvas MCP: making edits in Canvas" (install local `.mcpb`, drop hosted, ChatGPT steps on request); Tomkin reply in the 10-07 setup thread (which app?).
- **Next:** ease-of-use pieces designed, not built: (1) server `instructions` line naming the read-only policy (`feature/http-policy-notice`, sibling worktree); (2) hosted `.mcpb` with a keychain token prompt; (3) launcher clears stale `mcp-remote` lock. Save the sign-in query as a script. Write ChatGPT-desktop local steps if Cheng or Tomkin asks. Carry: remove `llkarri2`; GHSA-hmr8 + CVE; GHSA-7pp5; PR #441 CI approval; #489 closable after #490/#491/#494?

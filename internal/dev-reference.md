# Developer reference (moved out of CLAUDE.md, 2026-09-30)

Long-form guidance that used to load in every session. CLAUDE.md keeps the one-line
rule for each section; this file keeps the reasoning, examples and incident detail.
Sections are verbatim as of the move.

Verified 2026-09-30: every file path, script, workflow, test name, symbol and commit hash named below
exists; `main` requires a PR with one approval plus `test-enhancements` and `lint` (ruleset "Main Branch
Protection"); `deploy-prod.yml` triggers on `v*` tags and manual runs only. The adoption figures are
dated snapshots and were not re-pulled.

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

## Testing and behavioral evidence

Choose verification by the behavior at risk, not a per-tool test quota. New tools
must have meaningful automated coverage before they are complete. Cover relevant
success, failure, boundary, and safety behavior; several scenarios may fit one
parameterized test, while a consequential invariant may need several kinds of
evidence. Preserve existing regression coverage and required CI checks.

### TDD and refactoring

- For a reproducible bug or a clear behavior change, write a focused failing
  regression first. Observe it fail for the intended reason, then repair the
  implementation and verify it passes.
- Before refactoring, characterize behavior where the existing tests leave a
  meaningful uncertainty. Preserve the public contract and separate intentional
  behavior changes from structural cleanup.
- When expected behavior is still being discovered, exploration is appropriate.
  Establish the intended contract and meaningful verification before claiming
  completion; do not turn exploratory output into its own test oracle.

### Choose the test boundary

Use unit tests for local rules, integration tests for collaboration and transport
contracts, and end-to-end tests for complete user workflows when that is the
uncertainty. There is no universal ratio or preferred layer simply because an AI
agent writes the code. Keep the real components involved in the risk, replacing
external services with controlled responses where useful. End-to-end coverage
can expose integration failures; focused tests make edge cases and failures
cheaper to reproduce. Do not send live Canvas writes merely to verify a patch.

Derive assertions from an independent requirement or hand-checked example.
Assert observable outputs, outgoing request contracts, and forbidden side effects.
Scrutinize mocks that remove the interaction being tested or return only the
shape the implementation happens to expect. A passing success substring or a
mock assertion alone rarely establishes the whole behavior.

For example, this is adapted from `TestMarkConversationsRead.test_sends_form_data`
in `tests/tools/test_messaging.py`, the form-encoding regression for #208. It checks
the actual tool's outgoing contract:

```python
# get_tool_function is the registration helper in that test module.
@pytest.mark.asyncio
async def test_marks_conversations_read_with_canvas_form_fields():
    with patch(
        "canvas_mcp.tools.messaging.make_canvas_request", new_callable=AsyncMock
    ) as request:
        request.return_value = [{"id": 319, "workflow_state": "read"}]
        tool = get_tool_function("mark_conversations_read")
        result = await tool(conversation_ids=["319"])

    assert result["success"] is True
    assert request.call_count == 1
    assert request.call_args.kwargs["use_form_data"] is True
    assert request.call_args.kwargs["data"] == {
        "conversation_ids[]": ["319"], "event": "mark_as_read"
    }
```

This checks the tool-to-client boundary. Use a real client with controlled HTTP
transport when the uncertainty is serialization, retries, pagination, or error
classification; this mocked example does not establish those properties.

### Formal methods and completion gates

Use Lean/TLA+ selectively for consequential state, ownership, concurrency, or
termination invariants. Keep the source-to-model mapping and assumptions explicit,
and pair model proofs with implementation regressions. A proved model does not
prove the HTTP service, compiler, or every caller follows it. See `verify/` for
scoped examples and pinned toolchain instructions.

Run focused checks during iteration and the full Python suite before committing:
`uv run python -m pytest tests/ -v -rf`. Run `npm test` and `npm run build` for
TypeScript changes, and relevant formal checks when their implementation mapping
changes. Keep required lint, type-checking, and CI gates; do not merge with failing
required checks. Report what was verified and any failures, skipped coverage, or
environment limitations. Do not weaken assertions to obtain a green run.

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
  GitHub Actions: `deploy-staging.yml` on push to `staging`; `deploy-prod.yml` only on a `v*`
  release tag or a manual run from `main`. **Merging to `main` does not deploy production**
  (since 2026-09-27); ship unreleased `main` with `gh workflow run deploy-prod.yml --ref main`.
- The open-source **self-hosted (stdio)** path is the public product — see `README.md` / `AGENTS.md`.
  HTTP-transport env-var *names* live in `env.template` / `core/config.py`; the hosted *instance*
  is operator-only.

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

## Session Log notes (why `internal/` is deny-by-default)

> Full history: `internal/session-history.md` — **local-only, untracked since 2026-08-20**
> (it carried a paraphrase of a collaborator's private email and the private hosted endpoint
> URL while being world-readable). Do not re-add it to git.

> **`internal/` is deny-by-default in `.gitignore`.** Add an un-ignore only for a file
> deliberately meant to be public. Daily triage briefs stay tracked because the routine reads
> the newest one to compute its cutoff, so they **must not** record an external collaborator's
> institutional affiliation, evaluation status, deployment timeline, or which competing
> products they are weighing. Name the person and the technical issue, nothing else.

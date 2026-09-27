# Security review follow-ups (from the 2026-09-06 Codex xhigh review)

Status: PLAN, not started. Written by control 2026-09-06 evening.
Source: branch `codex/review-2026-09-06` (worktree `/Users/vishal/code/canvas-mcp-review`, 5 commits on top of `43497f9`), report `REVIEW-2026-09-06.md` at that branch's root. Suite on the branch: 1,464 passed / 21 skipped (control re-ran it). pip-audit, npm audit, bandit clean.

## 1. Land the branch (decision needed)

The branch is NOT merged because one fix changes public behaviour for HTTP deployments:

- `735ca36` **High S1**: over HTTP, `generate_peer_review_report(save_to_file=True)`, `extract_peer_review_dataset(save_locally=True)` and `create_student_anonymization_map` now refuse before any Canvas call instead of writing student records to the server's disk. stdio behaviour unchanged. The two optional-save tools are no longer annotated `readOnlyHint`, so cautious clients may prompt for confirmation.
- `afb4cc0` Medium S3: URL sanitizer strips user-info, query and fragment before logging (presigned upload credentials were reaching stderr).
- `63d2037` perf O1: peer-review completion analytics fetches the roster once, not twice.
- `b72c430` test: fencing registry test corrected for hybrid read/write tools.

Path: open a PR from the branch, note the S1 behaviour change in CHANGELOG under a minor bump, and ask Codex (not the branch author) to review the PR per the fleet rule. Hosted slots: confirm the three tools are not used with save flags by any hosted instructor before release.

## 2. Remaining findings, in priority order

| # | Sev | Finding | Where | Fix shape | Size |
|---|---|---|---|---|---|
| S2 | Med | Code-execution tool captures unbounded stdout/stderr with `communicate()`; a caller can exhaust host memory | `src/canvas_mcp/tools/code_execution.py:680-731` | Drain both pipes incrementally, keep a configured cap, kill the child on overflow, return an explicit truncation result. Needs deadlock-free draining tests. Tool is disabled on hosted slots (see CLAUDE.md #157), so self-hosted only | M |
| S4 | Med | Authenticated MCP HTTP requests have no body size limit; the bounded reader only guards the approval form | `src/canvas_mcp/server.py:85-119` vs `329-410` | Configurable ASGI receive limit for all MCP HTTP requests, enforce Content-Length and streamed bytes, 413 before JSON parsing. Integration test with a chunked oversize body | M |
| S5 | Med | Caller-supplied regex applied to Canvas titles with no time bound (announcement filters) | `src/canvas_mcp/tools/discussions.py:1416-1462` | Either a timeout-capable regex engine with a short limit, or retire regex for bounded literal/glob matching. Public filter contract changes; add compatibility tests | S-M |
| S6 | Low | Access-key comparison short-circuits via `any()`, contradicting the comment that every key is compared | `src/canvas_mcp/server.py:123-129` | OR integer results across all keys without short-circuit | S |
| S7 | Low | Anonymization mapping cache is global and unbounded | `src/canvas_mcp/core/anonymization.py:13-14,188-213` | Pseudonym is deterministic: drop the value cache, or bound it per request/tenant; status statistics need a design call first | S-M |

## 3. Optimizations recommended, not implemented

- O4 (top): HTTP mode builds a new `httpx.AsyncClient` per Canvas call (`core/client.py:458-470,603-607`); hold one authenticated client per MCP request in context and close in middleware. Needs concurrency and credential-isolation tests.
- O3: `list_groups` and `get_course_content_overview` serialize independent fetches; `asyncio.gather` with order preserved.
- O2: `generate_report` re-scans assignments already fetched by `get_completion_analytics`; a private collector returning both.
- O5: uploads read the whole file synchronously on the event loop; stream or bounded worker thread.

## 4. Order of work

1. PR and review of the branch (section 1).
2. S6 and S5 as small TDD commits.
3. S4, then O4, both need HTTP integration tests; do them together since both touch the HTTP path.
4. S2 only if hosted code-exec is ever re-enabled.

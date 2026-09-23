# TypeScript grading verification implementation plan

> Execute inline with tests before fixes, then one independent whole-branch review.

Goal: verify the real retry/bulk scheduler in client.ts and bulkGrade.ts, replay
counterexamples on TypeScript, and land minimal repairs. This is stage 3 of the
maintainer's ordered verification request; no wrapper-by-wrapper expansion.

Baseline: 65427f6. Existing npm suite: 10 passing; TypeScript build passes.

## Constraints and decisions

- Lean 4.19.0 under verify/lean; lake build without sorry. Pinned TLC under
  verify/tla; original negative controls must exhibit named failures.
- One bulk invocation is the deduplication/concurrency boundary. Intentional
  later regrading is supported (already tested); there is no global exactly-once
  service or durable job identity. Separate invocations can overlap.
- Treat an ambiguous write failure as potentially committed. Do not retry it;
  tell the caller to inspect Canvas before retrying. GET retains bounded retries.
- Reject duplicate submission targets before callbacks or writes, rather than
  silently choosing between potentially inconsistent submission records.
- Validate maxConcurrent as positive safe integer and rateLimitDelay as integer
  milliseconds in [0, 2147483647]. Explicit zero delay must remain zero.
- Preserve the per-run batch barrier and rubric metadata precheck.
- Proofs model API-side effects per dispatched request; they cannot prove remote
  exactly-once execution or constrain grading callbacks that perform own writes.

## Tasks

1. Add tests/code_api/grading-control-plane.test.ts. Drive actual exported
   functions with scheduled fetch responses and a local HTTP server that commits
   then returns 503, disconnects, or returns invalid JSON. Assert one write and
   an uncertainty error; duplicates reject without callbacks; invalid controls
   reject before fetch; zero delay does not schedule a sleep. Keep cap/backoff,
   dry-run, skipped/failed statistics and multi-run controls. Run npm test before
   production changes; save failures in verify/evidence/typescript-before.txt.
2. Repair client.ts with a method-aware write retry policy. Repair bulkGrade.ts
   with nullish defaults, input validation and full-target uniqueness preflight.
   Keep batching and reuse the existing grader. Run npm test and npm run build.
3. Add Grading Lean scheduler/retry machines and TLA+ commit-response retry,
   duplicate queue, and batch-barrier interleavings. Extend verify/run.py with
   positive/negative controls. Build and model-check; replay every failed
   invariant against the TypeScript tests. Document mappings and proof limits
   in verify/TYPESCRIPT.md, including no claim of cross-run exactly-once grading.
4. Independent review, full tests/formal checks, PR/CI and merge per existing
   maintainer authorization. Do not change deployed Canvas grades for testing.

## Review focus

Ambiguous response after commit; duplicate user IDs across fetched pages;
fractional/nonfinite/zero limits; explicit zero timer delay; async callback
failures and in-flight writes spanning batch boundaries. Each has a regression
or passing control in the new suite. Server snapshot/pagination completeness
is separate from the requested TS retry/scheduling proof.

## Execution ledger

- Source read: every request method currently retries network, JSON and 5xx
  failures. Bulk uses `||` defaults, unvalidated slice strides and no uniqueness
  check. Confirmed existing repeated-run test permits intentional regrading.

- Additional replay: mutable callback user_id redirected distinct jobs to one target.
  Capture each validated target before callback; add the matching TLA mode.
- Native npm baseline replay: 25 failures, 3 passing controls; repaired npm suite
  38 passing. Lean build succeeded; final combined TLC check in progress.

- Transport boundary followup: default fetch follows write-preserving redirects.
  A local307 commit replay failed (2 effects); redirect:error for writes fixes
  it. Added GradingRedirect negative/fixed controls and the regression.

- Final review: no safety blocker. Reproduced reviewer's callback null/undefined
  diagnostic loss; one-character null-safe access now preserves failed targets.
  Two added regressions fail before and pass after. This small repair follows
  the user's request to reproduce findings and land fixes.

- Final checks: all Lean/TLC cases passed, npm41/41, Python1601 passed/21
  skipped, TypeScript build passed. Baseline final replay28 failed/3 passed.

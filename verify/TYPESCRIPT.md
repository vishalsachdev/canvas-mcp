# TypeScript grading control-plane verification

Baseline: `65427f6939458ce5930006f6df3d4c2e5fa53351` (after Python client repair).
Scope: `code_api/client.ts` retry policy and `canvas/grading/bulkGrade.ts`
scheduling. Models come from these implementations, not the tool catalog.

## Findings, real-code traces and minimal fixes

| Finding | Replayed trace | Repair |
|---|---|---|
| Ambiguous failure replays a committed grade/comment | Local HTTP server accepts a grade, records its effect, then returns 503, disconnects, or returns invalid JSON. Original client sends the same write again; server records two effects. | Only GET retries. A write failure reports that it may have applied and requires checking Canvas before retrying. |
| Automatic redirect replays a committed write | Local HTTP server records the PUT then returns 307; default fetch resends it, recording a second effect even with explicit retries disabled. | Non-GET fetch uses redirect:error; reads retain follow behavior. |
| Duplicate records grade the same target twice | Submission list contains user 7 twice; two callbacks and PUTs run. | Reject the entire duplicate list before callbacks or writes. No silent winner selection. |
| Callback edits redirect a validated target | Distinct users 1 and 2 pass validation; each callback changes its input user_id to 7; both PUTs target 7. | Capture each validated user ID before invoking its callback. |
| Fractional concurrency breaks the cap | maxConcurrent=1.5; JS slice truncates bounds. First batch has one item; second batch has two, exceeding 1.5. Negative strides also need rejection to avoid backwards traversal. | Require a positive safe integer before fetching. Reject zero, negative, fractional and nonfinite controls. |
| Explicit zero delay is ignored | Two one-item batches with rateLimitDelay=0 schedule a 1000ms sleep because of `||`. | Nullish default; no sleep for zero. |
| Invalid delays are accepted | Negative, fractional, nonfinite and overflowing delays reach batch setup instead of being rejected; oversized Node timers would be clamped. | Require integer milliseconds from 0 through 2147483647 before fetching. |

Missing, nonpositive, fractional or nonnumeric response user IDs are rejected
before callbacks too: runtime JSON is not guaranteed by a TypeScript interface.
Independent review also reproduced a pre-existing callback error edge: throwing
null/undefined incremented failed but lost the target from failedResults. A
null-safe error access preserves the target and diagnostic; both cases have
failing-before/passing-after tests. The simplification pass removes the unused `allSettled` result binding. The
existing batch barrier and per-run rubric metadata precheck are retained.

The local HTTP server is a controlled substitute for Canvas, not a test against
production students. It proves that the actual TypeScript transport replays a
request after an ambiguous commit; it does not claim to have observed Canvas
itself return those failures. Other regressions replace only fetch/timers and
exercise real exported client/grading functions. No live grades were changed.

## Requested properties: exact verdicts

| Property | Verdict |
|---|---|
| No double-grade of the same submission | False originally within one run. Repaired preflight + immutable per-job target + no write retry establish at most one client-dispatched grading write per target per invocation, assuming callbacks do not perform their own writes. Separate invocations may intentionally regrade, as the existing tests require. |
| In-flight work respects maxConcurrent | True for positive integer limits on the original batching path; false for accepted fractional inputs. Repaired input validation makes the integer model applicable. A slot covers callback, rubric lookup and grading write through settlement. Cap is per invocation, not shared across concurrent runs/processes. |
| 5xx retry does not apply a grade twice | False originally. Repaired writes are never automatically retried, including 5xx, network, timeout and response-JSON failures. Write-preserving redirects are also blocked. GET retains at most four attempts with 1s/2s/4s backoff. At-most-one dispatch is not proof that a remote server cannot internally duplicate a request's effect. |
| rateLimitDelay | Sleep is admitted only after the batch settles and before another batch. Zero skips it. Positive validated values are passed to the timer; exact elapsed time is an event-loop/runtime assumption, not a wall-clock theorem. |

Bulk `failed` means the operation was not confirmed successful; after an
ambiguous write failure it **does not mean no grade was saved**. The propagated
error explicitly says to check Canvas before retrying. Existing 4xx behavior
is retained without retries. No new automatic reconciliation or idempotency
service is invented.

## Lean and TLA+ mapping

`lean/Grading/Retry.lean` models dispatch, possible commit and read retry.
The source loop still has four slots; write safety is proved from the absence
of a transition that re-enables a write after dispatch, not a one-attempt loop
assumed into the model. `reachable_invariant`, `no_write_replay`,
`at_most_one_write`, `reads_at_most_four_attempts`, and
`dispatch_decreases_budget` are checked without `sorry`.

`lean/Grading/Scheduler.lean` models a queue of preflight-validated user IDs,
issued jobs, active count and completed count. `admitted_unique` proves the
preflight gate; induction `reachable_safe` yields `no_duplicate_dispatch`,
`in_flight_cap`, and `accounted`. `slice_partition` and `batch_size_bound`
connect integer slicing to the queue abstraction. The scheduler conservatively
allows refilling a freed slot immediately; real `allSettled` waits for the
whole batch, so it admits fewer interleavings. `sleep_requires_settlement` and
`zero_delay_no_sleep` state the sleep gate.

TLA+ models:

- `GradingRedirect`: one fetch, remote commit, write-preserving redirect. The
  original two-request prefix violates `OneWrite`; repaired mode terminates
  after the first response. Redirect handling is below the explicit retry loop.
- `GradingRetry`: dispatch → remote effect → response → terminal/backoff. A
  remote commit and its response are separate events. Original mode violates
  `OneWrite`; repaired write/read configurations check bounds and termination.
- `GradingBatch`: individual callback/request/remote/settled states, batch
  admission and delay barrier. Duplicate-input and callback-mutation original
  modes violate `NoDoubleGrade`; fixed mode rejects duplicates or retains the
  captured target. Zero-delay original mode violates `ZeroDelay`.
- `GradingStride`: exact half-unit encoding of the 1.5 stride and truncated
  slice bounds; original mode violates `CapRespected`, fixed mode rejects it.

Every negative configuration has a TypeScript replay in the new tests.
Finite TLC exploration includes four jobs with cap two and arbitrary completion
orders; Lean induction covers arbitrary finite unique job lists and natural
caps. TLC liveness assumes enabled operations eventually finish (weak fairness).
Callbacks, network I/O and timers that never settle can prevent real completion.

These are manual, reviewed abstractions with executable regression evidence,
not a machine-checked compilation/refinement of JavaScript, fetch or Canvas.
Numbers map to natural counts only after runtime validation. Per-run input
configuration is assumed stable during the run; arbitrary external mutation of
private state, hostile callback network calls, and process restarts are outside
the proof. A callback may edit its own submission object without redirecting
the bulk writer, which is covered explicitly.

Pagination follow-up: [TYPESCRIPT_PAGINATION.md](TYPESCRIPT_PAGINATION.md) records
the subsequent repair and verification. The historical scope below describes
the grading-only baseline of this report.

## Remaining scope and operational limits

- No global/durable exactly-once guarantee across calls, users, processes or
  manual retries. Deliberate regrading must remain possible.
- The submission-list pagination algorithm in the TypeScript client is still
  the existing length-based numeric loop. This stage proves retry/scheduling
  after list retrieval, not complete or terminating enumeration. The Python
  pagination proof does not transfer to TypeScript. Broader workflow attachment
  is not declared clean by this report.
- Student matching, correct grade calculation and rubric semantics beyond the
  existing precheck/response checks are not newly verified.
- The write-retry restriction also protects the existing POST/PUT/DELETE
  exports. They now surface ambiguous failures instead of resending. Read
  retries and the public function signatures are unchanged.

## Run and reproduce

```sh
npm ci
npm run build
npm test
lake -d verify/lean build
TLA_JAR=/absolute/path/to/tla2tools.jar python verify/run.py
```

Use the toolchain and checksums in `README.md`. The runner checks both original
counterexamples and repaired invariants; parser/tool failures do not count as
counterexamples. Evidence is in `evidence/typescript-{before,after,formal}.txt`.
To replay the current regressions on the baseline, create a detached worktree at
65427f6, copy `tests/code_api/grading-*.test.ts` into it, run `npm ci`, then:

```sh
node --import tsx --test tests/code_api/grading-*.test.ts
```

The baseline replay has **28 failures and 3 passing controls**. Repaired complete
TypeScript suite: **41 passing tests**, including the existing 10 rubric tests.

Validation: npm build passed; 41 TypeScript tests passed. Full Python suite
passed (1,601 passed, 21 skipped); no Python production behavior changed.
Independent review found no blocking defects.

Runtime references: [Node timer bounds](https://nodejs.org/api/timers.html) and
[Fetch redirect behavior](https://fetch.spec.whatwg.org/#http-redirect-fetch).
The reported replay failures were executed locally, not inferred only from
these specifications.

## Shared batch executor (issue #400)

`code_api/batching.ts:createBatchRunner` now owns control validation, positive
integer slicing, `Promise.allSettled`, and inter-batch delays for both
`bulkGrade` and `bulkGradeDiscussion`. Both construct the runner before reads,
including previews; settings are captured for the invocation. `Scheduler.Step`,
`slice_partition`, `batch_size_bound`, `sleep_requires_settlement`, and
`zero_delay_no_sleep` map to this shared implementation. The unchanged
`GradingBatch` and `GradingStride` TLC models still describe admission and the
batch barrier. This extraction does not introduce a replacement-job scheduler.

Target uniqueness remains a caller obligation: ordinary grading validates
submission IDs and captures each target before its callback; discussion grading
builds one result per user in its participation Map and exposes no callback.
The discussion attachment covers scheduling and accounting, not the correctness
of participation scoring, remote data completeness, or a global write cap.
The model assumes finite well-formed work lists and eventual job settlement.
These are reviewed source mappings, not compiler-checked TypeScript proofs.

`tests/code_api/shared-batching.test.ts` exercises both exported workflows with
controlled transport: invalid controls before reads, zero/positive delay,
settlement before the next batch, concurrency caps, and failed-write accounting.
Existing ordinary-grading tests retain duplicate-target, callback mutation,
dry-run and non-Error failure regressions. No live Canvas requests are used.

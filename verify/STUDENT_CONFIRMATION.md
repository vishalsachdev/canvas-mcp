# Student submission confirmation

Baseline: `5714a58` (after TypeScript pagination #403).
Scope: the actual `submit_assignment` workflow in `tools/student_write.py`.
The other student write tools do not use a confirmation token and are not
claimed verified here. No live Canvas account or data was used.

## Reproduced bugs

1. **Mismatch did not burn.** Preview body A; confirm body B (rejected); revert
   to A with the same token. The baseline submits. A second reproduction holds
   the original caller at its post-reservation policy check, sends a mismatching
   confirm, then releases the original caller with a definite policy rejection.
   Reverting then submits on the baseline. Both must require a new preview.
2. **Expiration could reverse.** Issue at time T, observe expiration at T+301,
   roll the wall clock back to T. The baseline accepts the expired token again.
3. **A live fingerprint claim could expire.** Caller A reaches POST and awaits
   its response. Advance both wall/monotonic clocks by 301 seconds. A fresh
   preview for the same content/attempt lets B reach POST while A is still
   pending. The baseline dispatches twice; the repair admits only A.

The two concurrency replays schedule the real registered `submit_assignment`
function with asyncio Events. Only policy/Canvas I/O and clocks are controlled.
The time reversal replay calls the real token implementation. These are not
model-only counterexamples or real writes to a student's course.

## Repair and simplification

The student tool now delegates token issue/check/reserve/release and caller
identity to the already verified `ConfirmationGuard`. This removes its duplicate
HMAC/parser/wall-clock implementation. Each preview now has a nonce; mismatches
are terminal and expiration cannot reverse. The process-local key means tokens
still require the issuing worker. Old tokens do not survive a process restart;
a deployment therefore still requires a new preview.

A nonce alone is not enough here: existing student behavior also prevents a
fresh preview from overlapping an identical payload/observed-attempt claim.
Keep that fingerprint map, with monotonic retention deadlines and a set of
active owners. Cleanup cannot evict an active claim. Once the owner finishes,
a completed or uncertain claim is retained for five minutes from settlement.
Definite pre-submission policy/upload/preflight failures release the fingerprint
and nonce; a concurrent mismatch burn cannot be undone. A `finally` retires
the active owner on success, errors, exceptions and cancellation. Cancellation
retains the uncertain claim but does not leave an immortal active entry.

All claim/check transitions are synchronous, before the first awaited policy
check/upload. Releases and finalization contain no await, so another caller
cannot replace a released fingerprint between those two operations. Helpers
remain private, owner-only operations; arbitrary calls/reset from other code
are not supported.

## Formal correspondence

`lean/StudentConfirmation.lean` models one fingerprint's claim, active count,
monotonic time and deadline. `reserve`, `purge`, `release`, `finish`, and `clock`
come directly from the implementation. `reachable_safe` proves by induction over
arbitrary traces that an active owner always retains its claim and the active
count is at most one. `inflight_cannot_expire` and `one_active_submission` are
consequences. The evaluated original transition admits two owners after expiry.

The existing `Confirmation` machine is reused for each nonce rather than copied.
`authorized_payload_bound` and `expired_denied` show that the extra fingerprint
filter cannot weaken the shared authorization decision. This decision projection
does not replace the shared machine's mismatch-burn state transitions. Shared
`at_most_one_write`, `burn_blocks_future_reserve`, and clock theorems apply under
the same owner-only, proven-no-write release contract; the workflow replays
exercise that attachment. Hash/nonce collision resistance remains an assumption.

`StudentClaims.tla` explores two callers with fresh nonces for one fingerprint,
clock advance, cleanup, definite release and uncertain/completed settlement.
The original configuration violates `OneActive`; the fixed configuration checks
both `OneActive` and `ActiveClaimRetained`. Existing shared token/clock TLC
models remain in the same verification gate. No additional cryptographic
axioms, `sorry`, or axiomatized safety claims were added.

## Boundaries and deliberate behavior

- These are source-derived models with tested correspondence, not mechanically
  extracted proofs of Python, HTTP, or Canvas.
- Scope is one process/event-loop thread. Multi-worker tokens use independent
  secrets. This does not provide cross-worker submission deduplication.
- Expiry is checked at authorization, not at eventual remote commit. Already
  authorized uploads/POSTs may finish after the token's lifetime.
- A fresh preview can retry unchanged content after a settled claim's retention
  window. The tool also re-reads the attempt state before dispatch, but cannot
  prove remote exactly-once execution or atomic compare-and-submit. Canvas must
  report accurate attempt state; transport cancellation does not prove the
  server stopped processing an already dispatched POST.
- The fingerprint key remains caller/course/assignment/type/payload/attempt/
  attempt-limit. Different payloads or changed attempt state are different
  operations. This patch does not introduce global submission serialization.
- At most one write per nonce means one logical submission after authorization,
  assuming definitive no-write outcomes really mean no write. The Python client
  can retry HTTP 429; its existing assumption that 429 did not apply the write
  is unchanged. Uploads are not the final submission and may leave uploaded
  files when a later preflight check rejects.
- In stdio the configuration is treated as one fixed user; HTTP uses the
  request credential. Canvas instance configuration is server-pinned.
- Early input validation/policy/read failures that occur before token checking
  never write, but do not claim to consume a token. Burn applies when the
  authentic token reaches the fingerprint check.

## Reproduction and evidence

```sh
uv sync --group dev
FASTMCP_MCP_CAMELCASE_COMPAT=false .venv/bin/pytest \
  tests/tools/test_student_write.py tests/security/test_student_write_invariants.py -q
lake -d verify/lean build
TLA_JAR=/absolute/path/to/tla2tools.jar python verify/run.py
```

Use the pinned Lean/TLC tools described in `README.md`. For the negative control,
check out baseline 5714a58 in a separate directory, copy the updated
`tests/tools/test_student_write.py`, and run only:

```sh
pytest tests/tools/test_student_write.py \
  -k 'TestStudentConfirmationProtocol and not cancellation' -q
```

Expected: four failures on baseline, four passes after repair. The additional
cancellation regression verifies cleanup introduced by this repair. Existing
upload failure/retry, changed attempt/limit, identity binding, and concurrent
confirmation tests are retained. Unit tests were updated only where the private
reservation now requires a nonce, settlement precedes claim expiration, or
identity lookup moved to the shared guard.

Validation: 100 focused tests and the full Python suite (1,606 passed, 21
skipped) pass. Lean builds without unfinished proofs; TLC checks all 32
reachable fixed fingerprint states. Independent review found no blockers.

Exact outputs are in `evidence/student-before.txt`, `student-after.txt`,
`student-formal.txt`, and `student-python-suite.txt`.
The delete-tool and peer-review workflow attachments remain separate work.

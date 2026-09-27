# Confirmation protocol attached to write workflows

Baseline: `ace8985` (student confirmation #404; reporting bugs also reproduce
on pagination baseline 5714a58). This closes the requested caller-attachment
stage after the guard, Python client, TypeScript grading/pagination, and student
submission analyses. It does not verify every Canvas API wrapper.

## Source-derived attachment

Every row includes caller identity via the per-tool `ConfirmationGuard`.
Fingerprints use raw values; display fencing does not alter the sent payload.

| Workflow | Binding read from source | Dispatch and release |
|---|---|---|
| Assignment delete | resolved course ID, assignment ID, name, due time, points, submission presence, needs-grading count | one DELETE; never release |
| Page delete | resolved course ID, canonical page URL slug, title | one DELETE through the requested alias; never release |
| Module delete | resolved course ID, module ID, name, item count | one DELETE; never release |
| Module-item delete | resolved course ID, module ID, item ID, title, type | one DELETE; never release |
| Announcement delete | resolved course ID, announcement ID, title | one DELETE; never release |
| Bulk announcement delete | course ID, requested IDs, resolved ID/title list, stop-on-error, limit | sequential confirmed list; stop or continue on errors; never release |
| Criteria announcement delete | course ID, criteria, limit, matched IDs/titles/posted times | sequential confirmed match list; never release |
| Direct peer-review reminders | resolved course ID, assignment ID, recipient IDs, composed subject/body | one conversation POST; release only for a definite no-write rejection |
| Peer-review follow-up campaign | course selector, assignment ID, urgent/partial recipient sets and composed batch labels/subjects/bodies | sequential exact composed batches; never release, including partial failure |
| Student submission | caller/course/assignment/type/payload/attempt/limit | separate attachment and repaired fingerprint lease in `STUDENT_CONFIRMATION.md` |

All delete tools already call synchronous `redeem_confirmation` before writing.
Both peer-review send paths now reuse that helper too; their duplicated
check/reserve/error-path reserve code was unnecessary after shared mismatch
burns became terminal. The campaign's empty-plan path still consumes the token
without sending. Other early validation/read/permission failures do not write
and may leave the token unconsumed.

## Reproduced reporting defects and minimal repairs

1. **An uncertain POST was reported as unsent.** Run the real direct-reminder
   tool and `_post_conversation`; the controlled Canvas boundary accepts a POST
   but returns JSON null. Response handling raises, and the original catch
   returns `nothing_sent: true`. A subsequent same-token call was already
   blocked, so this is a false report, not a broken nonce claim. Record whether
   dispatch began; exceptions after that point now report `delivery_uncertain`
   and ask the caller to check Canvas Inbox before retrying. Preflight
   exceptions still report that nothing was sent.
2. **Campaign counts were always zero.** The campaign counted a `sent` list,
   but its helper returns a batch-level `success` result. Two successful batches
   produced zero reminders in the summary; a failed batch plus a successful
   batch also produced zero and overall `success: true`. Count recipients only
   for acknowledged batches and mark overall success false if any batch failed.
   Uncertain batches are not counted as confirmed; they may still have sent.

The three before-fix failures are in `workflow-before.txt` and
`workflow-counts-before.txt`. The tests execute registered tools and actual
composition/confirmation/POST helper code, with controlled I/O. No live Canvas
message, deletion or grade was performed.

## Models and claims

`lean/ConfirmedWorkflow.lean` contains two small machines:

- **Confirmed plan execution:** authorize the requested plan only when it
  matches the bound plan, then dispatch its head and advance the remaining
  list. A stop preserves the unexecuted suffix. `plan_is_bound`,
  `plan_conserved`, `only_confirmed_targets`, and `bounded_dispatch` prove that
  a runner dispatches only its confirmed plan, with at most one dispatch per
  plan position. This is not a uniqueness claim for duplicate targets already
  present in the input list.
- **Reminder outcome reporting:** dispatch, definite rejection, completion,
  and unexpected exception. `no_false_unsent` proves that a no-send report
  excludes a possible effect in the modeled execution. The original exception
  transition has an evaluated applied-but-reported-unsent counterexample.

The existing `Confirmation` model provides exclusive admission, binding,
expiry and terminal burns. Its TLA+ interleavings apply to admission of the
whole plan, not a separate redemption for each batch member. Real asyncio
replays hold the first DELETE/POST pending while a competing confirm runs.
They cover all five single-target delete tools, both bulk deletion loops, and
the peer-review campaign. Direct-reminder tests combine an in-flight owner,
mismatching recipients/content, and both definite 400 and uncertain 500 replies.
Only the original approved caller reaches POST, and its release cannot revive
the burned token. Existing tests cover plan drift, empty plans, metadata changes,
preview-without-write and replay. Additional tests change only resource IDs
while keeping names identical, and verify rejection in all single-target tools.

`ReminderReceipt.tla` models the server applying the POST before or after a
local exception/lost reply. The original mode violates `NoFalseUnsent`; fixed
mode checks that invariant and retention of the nonce after dispatch. The real
replay corresponds to server application before the malformed reply. Campaign
summary arithmetic is covered by code regressions, not claimed proved in Lean.

## Assumptions and precise limits

These are reviewed, source-derived models and real-code tests, not mechanical
Python extraction. SHA/HMAC and nonce uniqueness are assumed; the field table
and tests establish the reviewed binding correspondence. Plan items abstract
full endpoint/recipient/payload identities. The executor model begins after
successful admission; the separate shared proof and interleaving tests establish
that one token admits only one active runner (with retry after proven rejection
where explicitly supported).

- One process/event-loop thread; no shared signing key across workers. Inputs
  and resolved plan objects are owned by the invocation, not mutated by
  unrelated Python threads/tasks after authorization.
- Canvas metadata/aliases are assumed truthful: a page URL slug and numeric
  alias must resolve to the same page. The tools bind the metadata they display,
  not every body or field on the resource. No server-side compare-and-delete is
  available here, so another actor can change a resource after the final read.
- Course configuration is server-pinned. The campaign binds the supplied course
  selector; its resolution and Canvas's globally scoped assignment/user IDs
  are part of the external identity assumptions.
- Deletion/message outcomes cannot prove remote exactly-once execution.
  The Python client's bounded 429 retry still assumes a 429 did not apply the
  write. Proxy behavior and server effects are not proved.
- Direct-reminder release assumes the enumerated validation/auth status errors
  really mean no write. Ambiguous errors retain the claim. A later fresh
  preview is a new authorization, not prohibited by a per-nonce guarantee.
- A campaign is not a transaction: earlier batches may succeed before a later
  failure. Its spent token prevents replay of the whole plan. Summary counts
  mean recipients in acknowledged batches, not independently verified delivery.
- Expiry is checked at authorization, not at remote commit. An already
  authorized runner may complete after expiry or a concurrent mismatch.
- This protocol cannot prove that a human actually saw or approved a preview.
  Native Canvas peer-review creation/reminder operations and unrelated write
  wrappers are outside this scoped verification.

## Reproduce

```sh
FASTMCP_MCP_CAMELCASE_COMPAT=false pytest \
  tests/tools/test_delete_confirmation.py tests/tools/test_messaging.py \
  tests/security/test_untrusted_content.py -q
lake -d verify/lean build
TLA_JAR=/absolute/path/to/tla2tools.jar python verify/run.py
```

Use the pinned tools in `README.md`. Copy the updated messaging tests to a
baseline checkout and run `pytest tests/tools/test_messaging.py -k
'post_exception or campaign_counts' -q` for the three original failures.

Validation: 209 focused tests pass; the full Python suite reports 1,628 passed
and 21 skipped. Lean builds without unfinished proofs, TLC checks all six
fixed receipt states, and independent review found no blockers.

Evidence: `workflow-before.txt`, `workflow-counts-before.txt`,
`workflow-after.txt`, `workflow-formal.txt`, `workflow-python-suite.txt`
under `verify/evidence/`.

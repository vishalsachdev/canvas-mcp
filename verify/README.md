# ConfirmationGuard verification — first-machine report

Baseline: `710aa3a` (upstream main, 2026-09-23). Scope is
`core/write_confirmation.py`, with one real messaging caller used to replay a
race. No verification claim is made for HTTP retries, the TS client, delete
callers' fingerprint construction, student_write, or peer-review workflows.
Those remain the next ordered stages requested by the maintainer.

## Findings and patches

| Finding on baseline | Reproducible trace | Minimal repair |
|---|---|---|
| A concurrent mismatch burn can be erased | A confirms and awaits transport; B changes the subject using the same token and is rejected; A receives a definite 400 and releases; original arguments can now reach transport again | `check` records terminal burns separately; `release` cannot erase them |
| Authentication/cleanup clock samples disagree | Issue with expiry 101; reserve once; second `reserve` authenticates at 101, purges at 102, then returns True again | One time sample for authentication and cleanup |
| A purged spent token resurrects after clock rollback | Redeem at 100; expire/purge at 102; wall clock returns to 100; same token redeems again | Nondecreasing epoch clock, advanced by monotonic elapsed time |

All three failures are replayed on the actual baseline Python, not a mock of
the guard. The concurrency reproduction runs the actual registered
`send_conversation` function; its transport is replaced by a deliberately
scheduled rejection. No request was sent to a live Canvas service.

The second finding is a **guard-level** duplicate reservation, not a demonstrated
end-to-end double deletion: existing synchronous check→reserve callers provide
an additional check. The third reproduces successful duplicate authorization
through the actual `redeem_confirmation` helper. The first reproduces lost burn
semantics, not a write of the mismatching payload or two successful sends.

The initial wall-clock high-water repair was rejected during independent review:
a frozen clock could extend new tokens' elapsed lifetime after rollback. The
final clock advances with `time.monotonic()` as well. A separate regression
covers that rejected intermediate implementation; it passes on the baseline.

## Requested properties: exact verdicts

| Property | Result |
|---|---|
| Redeemed at most once | Unconditional reservation-count version is **false by design**: reserve→proven-no-write→release→reserve is supported and already tested by the product. The repaired model proves at most one completed write and at most one in-flight owner per nonce, under the release contract below. |
| Fingerprint A cannot authorize B | Proved for the executable abstract confirmation protocol (`authorized_target_is_bound`); real HMAC/fingerprint mismatch and revert replay are tested. Correct inclusion of the actual resource in each tool's fingerprint remains a caller obligation for the later attachment phase. |
| Expired tokens never succeed | Proved at the authorization clock sample (`expired_confirm_denied`). The code's existing boundary is preserved: expiry < now means expired; equality is allowed. The repair prevents cleanup from using a later sample and prevents observed expiration from being undone. |
| Atomic reserve on the event loop | Proved in the transition model (`no_double_reserve`, `at_most_one_inflight`); TLC checks split check/reserve interleavings for three callers; a real asyncio test launches 100 competing confirmations and gets one winner. |
| Mismatch burns, without performing a write | Proved by `mismatch_burns_without_authorizing` and `burn_blocks_future_reserve`, including release after an in-flight rejection. The actual messaging replay verifies the mismatching caller never reaches transport. An already-authorized caller may still complete; burning does not cancel its network operation. |

`reachable_safe` is an induction over arbitrary-length traces and arbitrary
natural-number expiry/time parameters. The proof links the executable
`confirm` function to those transitions with `confirm_refines_step`.
`at_most_one_write`, `at_most_one_inflight`, `clock_never_decreases`, and
`sampled_clock_advances` are consequences. `Original.*` contains evaluated
counterexamples, including the intentional release/retry behavior.

## Source-to-model mapping and assumptions

| Python state/event | Lean abstraction | TLA+ abstraction |
|---|---|---|
| `issue(fp)`: signed expiry and nonce; no insertion into spent map | One fixed, authentic fresh nonce; `initial` per issuance | Initial issued token |
| Nonce absent from `_redeemed` | `claim = 0` | `held = FALSE` / `spent = FALSE` |
| Nonce reserved, not burned | `claim = 1` | held, not burned |
| `check` detects an authentic, live mismatch | `burn`, or mismatching `confirm`: `claim = 2` | `Mismatch` |
| `check` then `reserve`, without await | `confirm`, refining atomic `reserve` | Separate `Check` and `Reserve`, conservatively allowing extra interleavings |
| Awaited transport | Observer-only `pending` count | Per-caller `inflight` state |
| Owner's proven-no-write `release` | `release`: clear only claim 1 | `Release`: retain a burn |
| Single downstream write completes | Observer-only `write` transition | `Write` |
| `_now`, then `_purge(sample)` | `observe`: max(last + elapsed, wall), purge if expired | `Clock`: finite order classes before/at/after expiry; nondecreasing sample in repaired mode |

The clock TLC model abstracts all ways to advance the effective sample as
nondeterministic candidate samples. It explores wall rollback in original mode
and high-water retention in repaired mode. It does not model elapsed seconds;
Lean's `sampled_clock_advances` and the Python regression cover that rule.
Integer time is an order abstraction of finite Python clock samples, not a
proof of floating-point arithmetic or operating-system clock behavior.

These are **models of the implementation with a reviewed, tested mapping**, not
a mechanically proved compiler/refinement from Python to Lean. Specifically:

- Authenticators are unforgeable and fingerprint digests/nonces do not collide.
  Lean does not prove SHA/HMAC or randomness. Distinct nonces project into
  independent single-token machines; caller identity is part of the fingerprint.
- One process, one event-loop thread. There are no awaits in guard transitions.
  OS threads and replicas sharing a secret are not covered.
- `release` is called once by the reservation owner, only after proof that no
  write happened. The method does not itself authenticate the caller or enforce
  ownership. Arbitrary `release`, `reset`, mutation of private fields, or use of
  raw `reserve` as fingerprint authorization invalidates these assumptions.
- A successful authorization permits at most one downstream write attempt in
  the model. HTTP automatic retries or a server applying a write despite a
  supposedly definitive rejection require the later client/workflow analysis.
- Expiry is checked at authorization, not at eventual remote commit. Cleanup is
  activity-driven. In-flight writes can finish after expiry or a later mismatch.
- Explicit `issue(now=...)` is a test/backdating hook. Production callers use the
  guard clock. The clock fix retains token format and integer expiry rounding.
- This protocol does not prove that a human actually viewed or approved a
  preview. It only enforces the token state machine.

## Reproduction

Install Lean **4.19.0** (the pinned `lean/lean-toolchain`), Java 17+, and TLC from
`https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar`.
The downloaded jar reports `2026.09.22.222048`, revision `35d40c9`; the runner
pins its SHA-256 to
`9732eea90bdc7432e618184e4bee78700460e83e988238a80151dfd6507cfa0c`.
The CI job pins the Lean binary archive digest too. Lean warnings are errors,
so unfinished proofs fail `lake build`, including unprinted theorem roots.

From the repository root:

```sh
lake -d verify/lean build
TLA_JAR=/absolute/path/to/tla2tools.jar python verify/run.py
python -m pytest tests/security/test_confirmation_state_machine.py -q
python -m pytest tests/ -q -rf
```

The runner requires the original configurations to produce their named failing
invariants, and both repaired configurations to pass. Unexpected tool/parser
failures do not count as counterexamples. TLC explores 57 distinct repaired
concurrency states (three callers) and 6 repaired clock states. Those finite
checks complement, not replace, Lean's unbounded induction.

To replay against the original code without replacing this checkout:

```sh
git worktree add --detach /tmp/canvas-confirmation-before 710aa3a
python -m pytest tests/security/test_confirmation_state_machine.py \
  -o pythonpath=/tmp/canvas-confirmation-before/src -q
```

Expected: **3 failed, 5 passed**. On repaired code: **8 passed**.
The existing 18 guard tests also pass. Local full-suite result and exact proof,
TLC, and before/after outputs are in `evidence/`.

## First-machine PR

One focused PR: **Preserve confirmation burns and prevent expiry replay, with
Lean/TLA+ verification**. Production changes stay in the guard. Existing
wire format and legitimate rejection/retry behavior stay compatible. The
simplification pass removes the redundant error-path reserve from
`redeem_confirmation`; `check` now owns mismatch burning. Other caller cleanup
and protocol attachment are deferred until client stages 2 and 3 are clean.

Human review should focus on the three traces, the release contract, and the
small Python patch. No Lean/TLA+ syntax review is required to assess those bugs.

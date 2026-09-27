# Python client control-plane verification

Baseline: `c786c02d51afda6dfa5d93291d9608a4d1d87884` (merged confirmation
repair). Scope: `src/canvas_mcp/core/client.py`. No Canvas service was contacted;
the regressions exercise the actual client with HTTPX transports and scheduled
asyncio interleavings. TypeScript grading and tool attachment remain separate.

## Reproduced defects and repairs

| Defect | Trace on the original code | Repair |
|---|---|---|
| Short pages truncate results | Server returns one item and a next Link; requested page size is 100; fetch stops without following next | Follow the server's opaque next Link, irrespective of page length |
| Pagination has no termination bound | Server keeps returning full pages, including cyclic next links; numeric page requests continue | Detect repeated normalized page URLs and enforce a 10,000-page budget; return an explicit error instead of partial success |
| Queued cancellation leaks a request-owned client | Per-request client created; semaphore occupied; waiting task cancelled before entering the old finally block | Put semaphore acquisition inside the ownership try/finally |
| Cleanup discards a replacement | Cleanup awaits old client's close; another caller installs a new client; cleanup resumes and clears the new cache | Detach the old cache before awaiting close |
| Suspended requests retain closed clients | Request captures shared client; semaphore wait or 429 backoff suspends; cleanup closes that client; request resumes and dispatches through it | Select the shared client immediately before each transport attempt |

The last defect has two separate regression traces. The baseline replay selects
eight tests: **six fail, two pass**. The two already-passing controls establish
the concurrency cap and retry bound. The infinite-pagination reproduction uses
a finite transport sentinel to stop the original Python loop; the corresponding
TLA+ lasso establishes why its control flow permits indefinite traversal.

Pagination now deep-copies input parameters. Concurrent traversals keep separate
cursors and visited sets. Next links preserve opaque query strings, but must
retain the initial origin and endpoint before credentials are sent. This follows
[Canvas's pagination contract](https://developerdocs.instructure.com/services/canvas/basics/file.pagination):
page sizes may be capped and the Link header determines continuation. A missing
next Link is terminal. Malformed responses/links and budget exhaustion fail
explicitly. There is no fallback to guessed numeric pages.

## Proofs and exact boundaries

| Requested property | Result and scope |
|---|---|
| Semaphore cap | Lean induction `semaphore_bound` covers arbitrary traces and caps. TLC explores three callers with cap two, including backoff and cancellation. Actual Python launches 20 requests with cap two. |
| Client loop ownership | `selected_owner_is_running` and `selected_client_is_open` prove selection rules. TLC explores cleanup/replacement and cleanup-before-dispatch; Python replays both suspension sites. Selection occurs at dispatch without intervening await. This assumes one active event-loop thread and stable configuration. |
| 429 retry termination | Lean proves at most four attempts (initial plus three retries) and a decreasing attempt budget. Python verifies four responses and default delays 2, 4, 8 seconds. No retry logic change was necessary. External awaits must finish; arbitrary Retry-After values mean no fixed wall-clock deadline is proved. |
| Pagination termination | Lean proves a decreasing budget and at most the configured number of page fetches. TLC checks finite successor traversal/cycles and the endless-full-page abstraction. Python tests cycles and an endless unique successor stream with a reduced budget. Each HTTP operation must finish. |
| No skipped/duplicate pages | Lean proves no repeated abstract page identity and that each successful step follows the advertised successor. TLC models two independent callers; Python exercises concurrent traversals. Page identity is normalized URL, not record ID or semantic equivalence between different URLs. |

Lean files are under `lean/Client/`, imported by `Client.lean`; `lake build`
checks both this model and Confirmation without `sorry`. TLA+ files are
`ClientRequests`, `ClientCleanup`, `ClientDispatch`, `ClientPagination`, and
`ClientPageBudget`. `run.py` requires original configurations to exhibit their
specific invariant/temporal failures and repaired configurations to pass.

Source mapping: semaphore acquire/release maps to `PermitStep`; the retry loop
maps to bounded `Attempt`; shared cache and loop weakref map to lifecycle
selection; cleanup detachment maps to Begin/Finish in `ClientCleanup`; dispatch
selection maps to `ClientDispatch`; per-call visited URLs, successor and page
budget map to pagination `State`/`Step`. Lifecycle Lean lemmas are local effect
proofs; TLA+ supplies the await interleavings. These are reviewed abstractions,
not a machine-checked refinement of Python or HTTPX.

Additional limitations:

- Loop ownership is a request-dispatch guarantee. Existing server shutdown may
  call `aclose` from a new loop after the owner loop closes. Shutdown teardown is
  not proved to avoid every closed-loop interaction.
- Cleanup can interrupt an already running request, producing a transport
  failure. It does not promise graceful draining of all in-flight work.
- Owned-client cleanup assumes `aclose` completes without a further cancellation
  or close exception; the model abstracts completion of that operation.
- Separate threads, processes, runtime configuration replacement and arbitrary
  mutation of private state are outside the semaphore/ownership model.
- Server-side snapshot consistency, overlapping records across distinct pages,
  and misleading/missing Link headers cannot be repaired by a client proof.
  Completeness is conditional on an accurate stable server successor chain and
  traversal within the explicit page budget.
- Four bounded attempts do not establish exactly-once remote writes. The
  TypeScript 5xx grading retry and wider workflow analysis remain outstanding.

## Reproduction and evidence

Use the pinned toolchain described in `README.md`:

```sh
lake -d verify/lean build
TLA_JAR=/absolute/path/to/tla2tools.jar python verify/run.py
pytest tests/core/test_client_state_machine.py -q
pytest tests/ -q -rf
```

For the original-code replay, keep these tests in the repaired checkout:

```sh
git worktree add --detach /tmp/canvas-client-before c786c02d51afda6dfa5d93291d9608a4d1d87884
pytest tests/core/test_client_state_machine.py \
  -o pythonpath=/tmp/canvas-client-before/src \
  -k 'short_page or cyclic or cancelled or cleanup or 429 or cap' -q
```

`evidence/client-before.txt` records six failures and two passing controls.
`evidence/client-formal.txt` records proof checks and expected counterexamples;
`evidence/client-suite.txt` records the complete repaired Python suite: **1,601 passed, 21 skipped**. The 12 focused client tests pass. Ruff and client mypy checks pass. These
outputs are evidence from this checkout, not a guarantee about future changes.

The simplification pass removes the redundant early shared-client lookup:
shared clients are now selected only at dispatch. The patch changes no thin
Canvas tool wrappers and retains the existing retry count/backoff policy.

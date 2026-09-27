# TypeScript pagination verification

Baseline: `a24e67f4b474298346fbe96b1d486ef034011955` (grading repair #397).
Scope is the actual traversal in `code_api/client.ts`, not every API wrapper.

## Reproduced findings and repair

- **Premature completion:** a short or empty page with a next Link ended the
  original loop. Follow next regardless of body length; no next means complete,
  even when the final page is full. A bulk-grading integration test confirms
  that both linked submission pages reach the grader exactly once.
- **No traversal bound:** a server returning full pages indefinitely kept the
  numeric loop running. A cyclic Link was ignored. Track normalized requested
  URL identities and reject cycles; stop after 10,000 admitted pages with an
  explicit error. The original replay uses a finite HTTP-error sentinel after
  10,000 responses, while the temporal model establishes the permitted loop.
- **Configuration race:** after page one, `initializeCanvasClient` could replace
  the shared configuration; the next page went to a different instance with a
  different token. Keep the complete config object snapshot for the traversal.
- **Redirect bypass:** a real local HTTP server returned a redirect to another
  endpoint and the original GET followed it. Pagination now rejects redirects,
  so fetch cannot circumvent origin/path validation or hidden page identity.
- **Invalid shape looked complete:** null could produce an empty success.
  Non-array bodies now fail explicitly; later HTTP errors never return partial
  accumulated data.

Newly followed links are validated before dispatch: same origin and exact
normalized pathname, no userinfo and no fragment (including an empty `#`).
Malformed syntax (including missing, empty or invalid relations), multiple next
links, repeated relation parameters, or an
anchored next link fail explicitly. The parser handles quoted/escaped attribute
values, commas/semicolons inside URLs or quotes, relation lists, case-insensitive
parameter/header names, and relative links. Canvas documents absolute opaque
links; relative resolution is a conservative convenience at the same boundary.

The behavior oracle is [Canvas's pagination contract](https://developerdocs.instructure.com/services/canvas/basics/file.pagination):
page length is not a completion signal; the Link header supplies the opaque
successor. [RFC 8288](https://www.rfc-editor.org/rfc/rfc8288.html) supplies Link
syntax and relative-reference context. The parser deliberately rejects
ambiguous/context-changing input rather than guessing. It is not claimed to
implement every optional Web Linking behavior.

## Design and compatibility

The previous request helper discarded the response headers needed by traversal.
A private `sendCanvasRequest` now owns authentication, serialization, retries,
and JSON decoding once, returning data plus Link metadata. Public plain-data
functions still return their original data types, parameters and write-retry
policy. Traversal calls this same transport with its saved config and an exact
URL; subsequent queries are never reconstructed or augmented.

Pagination parameters are read synchronously before the first await and never
mutated. Cursor, seen set, budget and result list belong to each invocation.
Only paginated GETs reject redirects; ordinary `canvasGet` retains its earlier
redirect policy. Read retries remain bounded at four attempts and append a
page only after successful decoding. Final-page detection intentionally changes
from guessed numeric pages to server-advertised next links.

## Formal correspondence and guarantees

`lean/TypeScriptPagination.lean` checks the executable admission guard: a
request is admitted only when budget remains, the URL is fresh and allowed.
`admitted_commit_refines_step` connects it to the existing
`Client.Pagination.Step`. Thus the shared proofs `no_duplicate_page`,
`finite_fetch_bound`, `termination_variant`, and `follows_server_successor`
apply without copying their implementation into another proof file.

Additional theorems establish credential preservation and other-caller
noninterference. `total_request_bound` composes a per-page four-attempt bound
with a finite page limit: at most 40,000 explicit fetch attempts for a 10,000-page
traversal. HTTP redirects are disabled, so they cannot add hidden follow-up
requests to other pages. This bound is not a fixed wall-clock deadline.

TLC reuses `ClientPagination` for two callers' cursor interleavings, early
completion and cycles, and `ClientPageBudget` for the original endless-page
lasso and repaired finite budget. The newly added `TypeScriptConfig` explores
reinitialization between page requests; original mode violates
`CredentialBound`, repaired mode retains the saved configuration. Every failed
invariant/temporal property has a TypeScript replay. Shared models are checked
once by `run.py`; their applicability to both implementations is documented,
not inferred merely from the older Python tests.

Proof boundaries:

- These are reviewed models with code-level regressions, not a mechanical
  refinement of TypeScript, URL, HTTP headers, fetch or the Canvas service.
- URL identities use `URL.href`; semantic aliases or reordered query parameters
  can identify the same server data under different strings. Record-level
  duplication/omission from changing server snapshots cannot be prevented by
  a traversal proof. The bulk grader separately rejects duplicate user targets.
- Completeness requires an accurate next chain, within the page budget. Missing
  next means terminal; a broken server can omit records undetectably. Valid
  very large datasets exceeding 10,000 pages now fail instead of returning a
  misleading partial success.
- Requests/response bodies and timers must eventually settle. The parser's
  grammar and URL safety comparison are tested, not proved in Lean. The network
  stack/proxy is assumed not to independently replay requests.
- A config snapshot means later reinitialization affects new calls, not an
  already-running traversal. No global concurrency limit is added here.
- Duplicate Link handling, exact endpoint pinning and rejecting paginated
  redirects can reject nonstandard servers/proxies; failure is explicit.

## Verification and reproduction

```sh
npm ci
npm run build
npm test
lake -d verify/lean build
TLA_JAR=/absolute/path/to/tla2tools.jar python verify/run.py
```

Use the pinned formal tools in `README.md`. The new tests run exported
TypeScript functions with controlled fetch responses, plus a real localhost
HTTP redirect server. No live Canvas data was read or changed.

Validation: all 68 TypeScript tests pass; all 27 new pagination regressions fail
on the baseline. TypeScript compilation, Lean/TLC checks and the Python suite
(1,601 passed, 21 skipped) pass. Independent review caught the malformed-relation
edge case; four additional regressions failed before that repair and pass after.

Evidence: `evidence/ts-pagination-before.txt`, `ts-pagination-after.txt`,
`ts-pagination-formal.txt` and `ts-pagination-python-suite.txt`. Replay on the
baseline by creating a detached worktree at a24e67f, copying
`tests/code_api/pagination-*.test.ts`, installing npm dependencies and running:

```sh
node --import tsx --test tests/code_api/pagination-*.test.ts
```

This closes the pagination gap identified in `TYPESCRIPT.md`; it does not yet
verify the full confirmation-tool or peer-review workflows.

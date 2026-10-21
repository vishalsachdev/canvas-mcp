# Canvas MCP overhaul implementation plan

Created: 2026-10-20
Last Updated: 2026-10-20
Authored by: [Codex overhaul]
Baseline: `b271b63`, branch `overhaul/2026-10`.

> Execute task by task with the executing-plans skill. Commit this plan before
> changing production code. The approved specification is the maintainer's local
> `BRIEF.md`; it is intentionally absent from git. This document contains only
> public-safe source evidence, synthetic examples, and aggregate check results.

## Current architecture (one page)

The public product is a Python 3.11+ FastMCP server, installed through the
`canvas-mcp-server` entry point. `server.py:428-504` constructs it and registers
entity-specific tool functions, three resource templates, and one prompt.
Role selection and feature gates control registration; `core/tool_policy.py`
then removes disallowed side-effect tools. Live in-process MCP enumeration on
this revision gives **student 51/62, educator 94/96, all 113/126** (default/all
optional features). The manifest lists exactly the same 126 names. Complete
tool metadata serializes to 155,814 bytes with all features enabled. Names are
mostly action/entity based, but historical aliases and overlapping views are
public compatibility surfaces, not permission to remove them.

The main request path is tool → identifier/validation helpers →
`core/client.make_canvas_request` → Canvas. Course lookup supports numeric IDs,
codes, names and SIS identifiers; mutations with ambiguous targets fail closed.
`fetch_all_paginated_results` follows Canvas's opaque `Link rel="next"` URLs,
not response length (`core/client.py:784-862`). It rejects cycles, unsafe links,
non-list pages and exhaustion rather than returning a partial list. Bounded
inbox/recipient views deliberately expose a continuation indicator
(`tools/messaging.py:345-371`, `tools/student_messaging.py:577-618`). A
`per_page=100` request alone is not evidence that a list is complete. The
TypeScript client separately implements pagination and retry rules.

Stdio uses the operator's configured Canvas token. HTTP requires request-local
`X-Canvas-Token`, a server-pinned Canvas URL, and configured access/Entra gates;
the startup guard refuses a server-wide token (`server.py:282-425,638-662`).
Entra is an upstream platform assertion, not a new OAuth implementation in
this tree. Credentials and course labels are request scoped
(`core/credentials.py`); most anonymization state is still process global.
The client selects full, identity-only, free-text-only or no anonymization by
endpoint. Output fencing marks author-controlled content as data. Confirmation
tokens bind a preview to one attempted write; client approval supplies human
authorization. They cannot establish that a person saw a preview.

The opt-in TypeScript execution path is a second, privileged implementation
surface: it receives the Canvas token, uses its own HTTP client and can bypass
Python fencing/confirmation. It is off by default and disabled in hosted
configuration. The existing #157 boundary remains open. The local request-route
report was reviewed read-only: available observations favor direct API usage,
but do not measure all HTTP requests, and have unknown periods. They justify
preserving the local/direct workflow, not removing the guarded MCP tools. No
private route counts, identifiers or operational details are copied here.

The checkout contains 31,487 Python source lines and 94 Python test files.
Baseline: **3,329 passed, 20 skipped** in 29.31s; Ruff clean; mypy clean across
60 source files; TypeScript **96 passed**, build clean; wheel and source
distribution build successfully. Several security tests are explicit placeholders
or require optional tools, so their names overstate the exercised guarantees.
CI covers Linux Python 3.11–3.14, Windows 3.14, TypeScript and confirmation proofs.
Historical architecture/best-practice notes contain obsolete tool counts and
execution defaults. Current code and measured behavior take precedence.

## Global constraints and completion criteria

- Work only in this linked worktree on `overhaul/2026-10`; leave the primary
  checkout and its branch untouched. Do not commit `BRIEF.md`.
- Preserve all public tool names, arguments, result schemas, resource URIs,
  prompt signatures and registration defaults. Proposed incompatible work
  belongs under **Breaking changes (needs Vishal)** and stays unimplemented.
- No live Canvas requests are necessary. Use synthetic response shapes and
  controlled HTTP transports. Never read student records or use live writes.
- No push to main, PR merge, tags, deployment workflow runs, Azure changes,
  new services, telemetry or tracking. This run will keep its commits local.
- No wholesale dependency refresh. Preserve locked certifi **2026.10.19** or
  later. An individual dependency change needs a specific reason.
- Before each new regression, state the production change it detects. Run it
  against the original code and inspect the intended failure before fixing it.
- Before every commit run the **full** Python suite, Ruff and mypy; record every
  failure by node name. Run focused checks while iterating. Run the TypeScript
  suite/build whenever TypeScript changes, and at the final integration gate.
- Keep commits independently revertible. Record results, commit SHAs, remaining
  work and maintainer questions in committed `docs/overhaul/STATUS.md` at the end.
- Compare live tool schemas/annotations across all six role/feature combinations
  with the baseline. Inspect package contents and keep audit artifacts out of
  the website upload. No private scan report or historical credential enters git.

## Ranked work items

### Task 1: announcement deletion must prove the target type

**Problem/evidence:** `tools/discussions.py:1972-2008,2053-2063` accepts any
discussion record at an announcement ID and later deletes it without checking
`is_announcement` (F13). Existing confirmation coverage proves token binding,
but not that the bound object is an announcement.

**Change/files:** require literal `is_announcement is True` at preview and
confirmation in all announcement deletion paths, including criteria-selected
objects. Reject malformed objects safely. Exclude refused bulk objects from
the bound delete set and explain their refusal. Preserve the existing tool
interfaces and token rules. Update synthetic announcement fixtures to include
Canvas's actual discriminator. Files: `tools/discussions.py`, deletion/security
tests, existing announcement usage docs if needed.

**Risk:** medium; sparse historical test fixtures omit the discriminator.
**Verification:** a regular topic, missing flag, string flag, malformed detail,
or changed target type produces no DELETE; a mixed bulk request deletes only
the previewed announcements; a valid announcement still previews, confirms
once and refuses replay. Mutation named before tests: removing the strict type
check would allow an ordinary discussion to be deleted.

- [ ] Write/run failing boundary regressions, implement the guards, then run the
  focused tests, full suite, lint/type checks and commit.

### Task 2: predictable text stripping and identity redaction

**Problem/evidence:** unclosed script/style blocks and repeated `<` make
`tools/courses.py:187,202` rescan suffixes (F14/F16).
`core/anonymization.py:191-201` retries the email pattern at successive word
boundaries (F4/F5 are one sink). Both operate synchronously on authored text.

**Change/files:** replace suffix-rescanning HTML removal with bounded-work
parsing/tokenization while preserving normal whitespace, entity, inline and
block behavior; reuse that primitive for UFIXIT/location text. Anchor email
candidate handling so a run without `@` or a valid domain is visited a bounded
number of times, preserving existing redaction semantics and full text.
Do not truncate a syllabus or silently omit content. Files:
`tools/courses.py`, a focused `core/` text helper if needed,
`core/anonymization.py`, text/privacy regressions.

**Risk:** medium; malformed HTML and punctuation around emails affect output.
Minimal overlap with #441's anonymization file is unavoidable; no OAuth/auth
logic is rewritten. **Verification:** existing semantic tests plus long
synthetic malformed HTML, mixed scripts/styles, entities, inline/block
boundaries, long dot runs, multiple `@` symbols and emails beside Unicode.
Run adversarial cases in a subprocess with a generous timeout, not a fragile
sub-millisecond benchmark. Mutation: restoring either vulnerable regex must
fail the bounded-completion regression without hanging the suite.

- [ ] Capture failing adversarial cases, preserve normal output, implement,
  verify full suite/lint/types and commit.

### Task 3: accessibility scanning must terminate on malformed markup

**Problem/evidence:** adjacent overlapping quantifiers at
`tools/accessibility.py:1001-1002` create polynomial backtracking (F2); UFIXIT
tag removal at `:649` is quadratic (F3). Other attribute/link patterns at
`:450-461,811,908` need adversarial checks too. `:602` discards a `finditer`
iterator without consuming it: dead code, not a completed scan.

**Change/files:** split attribute/content inspection into bounded token or
per-element operations instead of overlapping whole-document regex searches;
reuse Task 2's text stripping where applicable. Preserve issue categories,
result shapes and fixer behavior. Remove the discarded search.

**Risk:** medium; valid HTML matching and fixer replacements must stay intact.
**Verification:** all existing scanner/fixer fixtures, meaningful malformed
style/link cases, UFIXIT with long `<` runs, and exact expected issue types.
Mutation: restoring the vulnerable color-only expression or UFIXIT stripping
must fail a bounded-completion regression.

Final independent review found that the first bounded tag pattern mishandled
valid quoted `<`/`>` characters. Replace it with one forward quote-aware token
pass shared by text extraction, scan rules and attribute fixers. Preserve row
scope, quoted attribute values, script/style suppression and CSS `!important`
priority; make single-quoted alt fixes match scanner claims. Regression cases
must fail the first implementation before this correction and retain the
malformed-input completion checks.

- [ ] Add failing bounded-work regressions, implement the minimum replacement,
  verify the full suite/lint/types and commit.

### Task 4: close output provenance and request-state gaps

**Problem/evidence:** scanner descriptions copy link text, class names and alt
excerpts but `tools/accessibility.py:279-287` fences only title/location (F10).
The `summarize-course` prompt interpolates name/code into a user-role message
at `resources/resources.py:110-120` (F15). `get_anonymization_status` reads a
global pseudonym cache (`tools/admin_tools.py:25`,
`core/anonymization.py:218-230,527-532`), exposing another caller's activity (F12).

**Change/files:** fence author-derived scanner descriptions at the output
boundary and course labels inside the prompt. Add an explicit prompt trust
decision/coverage alongside resource coverage. Give HTTP anonymization cache
statistics request scope using the existing credential-context lifecycle;
retain stdio cache behavior, stable pseudonym values and output field names.
Files: accessibility/resources, `core/credentials.py`, minimal anonymization
changes and security tests. No auth policy or token handling change.

**Risk:** medium; ensure no fence reaches content written back to Canvas and
no mutable context default is shared across concurrent requests.
**Verification:** real in-process MCP prompt/scan calls with forged markers;
synthetic concurrent callers cannot observe each other's cache or stdio state;
clearing one context leaves another intact. Mutations: remove description or
prompt fencing, or use the global cache for HTTP, and those tests must fail.

Audit follow-up during Task 4: the scanner silently reported zero issues when
Canvas returned an error, and the fixer marked failed PUTs as applied
(`accessibility.py` at baseline: `248-274,330-365,393-399`). Propagate source
errors before writing, fence fixer result labels only after write-back, and
confirm changes with a separate read. Regression mutations: ignore a failed
source/PUT or read-back mismatch; each must fail without sending a live write.

Review also confirmed a pre-existing false-clean page-list shape: [Canvas's
Pages API](https://documentation.instructure.com/doc/api/pages.html#method.wiki_pages_api.index)
only returns bodies when `include[]=body` is requested. Request that field and
report missing or unreadable page bodies as unconfirmed instead of empty.
Verify through the actual MCP tool with a fixture that respects the include
parameter, and strengthen the older vacuous title-fencing fixture.

- [ ] Write/run failing trust/isolation regressions, implement, verify the full
  suite/lint/types and commit.

### Task 5: pin release tooling and constrain automation credentials

**Problem/evidence:** `.github/workflows/publish-mcp.yml:101-128` executes an
unchecked latest binary (F1). `.github/workflows/claude.yml:29,39-45` and
`weekly-maintenance.yml:23,43-45,100-102` allow App-token elevation and combine
untrusted text with issue-publication capability (F7/F9). These are source-
verified capabilities; successful model manipulation has not been demonstrated.

**Change/files:** pin a publisher release and committed digest, verify bytes
before extraction/execution, and declare OIDC per job that actually uses it.
Use explicitly scoped GitHub tokens for agent actions rather than exchanging
for an installation token. Separate maintenance analysis (read-only) from
deterministic report publication; the model cannot choose an arbitrary local
file to publish. Keep the existing schedule and report purpose, without
running either workflow. Add permission/configuration regressions and execute
the installer/report handling against controlled local inputs.

**Risk:** medium; upstream action token requirements and artifact handling.
Consult the pinned action's primary source. Live environment/tag rules and
PyPI trusted-publisher settings require Vishal and remain unmodified.
**Verification:** corrupt publisher bytes fail before any binary executes;
agent jobs have no OIDC escalation or content-write permission; report
publication receives only the fixed report artifact and a scoped token.
Mutation: restoring latest/unchecked download, App-token fallback, or agent
`gh issue create` privileges must fail the relevant checks.

Primary-source verification: the [pinned action's token selector](https://github.com/anthropics/claude-code-action/blob/1d6de8cb0c237e7c15e9e1bdf973826ebae490cc/src/github/token.ts#L159)
uses an explicitly supplied token before its OIDC/App exchange; its
[action outputs](https://github.com/anthropics/claude-code-action/blob/1d6de8cb0c237e7c15e9e1bdf973826ebae490cc/action.yml)
include structured JSON. The [publisher v1.8.1 release](https://github.com/modelcontextprotocol/registry/releases/tag/v1.8.1)
Linux amd64 archive was downloaded and its SHA-256 independently matched to
the release API digest before selecting the pin. Artifact validation constrains
publication inputs; it does not make model-authored reports injection-proof.

- [ ] Verify upstream contracts, add regressions, implement local workflow
  hardening, run full suite/lint/types and commit. Do not deploy or publish.

### Task 6: local helper scripts treat remote values as data

**Problem/evidence:** automatic SessionStart context contains third-party
titles/labels/category text (`scripts/github_session_brief.py:206,219-225,269`),
and the fence is only a model cue (F8). Download counts and JSON enter an
unquoted Python heredoc (`scripts/collect-impact-stats.sh:80-109`, F11).

**Change/files:** keep automatic GitHub summaries to validated identifiers,
counts, status and constructed URLs, fetching author text only on demand.
Pass statistics as data to a quoted Python program, validate non-negative
integer counts, preserve last-good fallback, and avoid printing PyPI counts.
No new statistics sources, service or collection schedule. Extract a small
pure helper only if it makes the actual shell boundary testable.

**Risk:** low/medium; keep useful CI/age/continuation information and existing
snapshot shape. **Verification:** synthetic hostile titles/labels never enter
automatic context; malicious API strings cannot execute and cannot replace
the last-good snapshot. Run scripts in an isolated fixture directory with
fake commands and no deploy argument. Mutation: reintroducing title text or
source interpolation must fail those behavioral tests.

- [ ] Add failing process/boundary tests, implement, verify full suite/lint/types
  and shell syntax, then commit.

### Task 7: remove proven duplication and correct maintained documentation

**Problem/evidence:** AST comparison finds an exact duplicate numeric helper in
`tools/student_grades.py:129-136` and `core/grade_calc.py:622-629`. Tool modules
and `core/peer_reviews.py` are adapters and implementations, not duplicate
registrations. Python and TypeScript clients overlap intentionally but have
different security boundaries. Historical architecture notes still discuss a
90-tool registry and an enabled-by-default execution path. CI's release test
installation omits PyYAML, allowing permission checks to skip there.

**Change/files:** share the numeric helper through the existing grade-model
module; remove only proven dead work (Task 3). Keep all public adapters,
aliases, code-API exports and tool names. Add a current-status caveat to the
historical review and fix contradictory maintained docs, not a rewrite of the
archive. Ensure release tests install their declared policy-test dependency.
Exclude `overhaul/` from website assets. No dependency-version changes needed.

**Risk:** low; no behavior change intended. **Verification:** existing grade
model/tool tests, full suite/lint/types, tool contract comparison, TypeScript
tests/build, wheel/sdist inventory and isolated package import/CLI help.
No redundant new test merely asserting the helper was moved.

Packaging verification found that Hatch included the untracked `BRIEF.md` and
the self-ignored `.superpowers/` workspace in the source archive. Add explicit
root ignore rules and a release gate inspecting the actual wheel/sdist members
for operator briefs, credentials and local scratch paths. This requires only a
small `.gitignore` overlap with #441; no package dependency or OAuth change.
Verify synthetic forbidden artifacts fail and rebuilt real artifacts pass.

- [ ] Refactor/correct docs, run all stated checks and commit.

## Security finding disposition at the baseline

The 2026-10-17 scan was source-only and used an older revision. All paths below
were checked against this checkout or, where explicitly identified, read-only
history/private source. No leaked value, live credential or learner record was read
into an output. Duplicate finding numbers remain visible to prevent double counting.

| Finding | Current evidence / disposition |
|---|---|
| F1 | Unchecked latest publisher still present; Task 5 mitigates binary drift. Environment/audience separation remains owner work. |
| F2 | Color-only expression still overlaps; Task 3. |
| F3 | UFIXIT `<[^>]+>` still present; Tasks 2–3. |
| F4 | Email regex still retries across dotted runs; Task 2. |
| F5 | Same code site as F4; one implementation fix, not two. |
| F6 | Historical launcher exists and contains a hardcoded credential assignment; checked without displaying the value. Revocation/usage review and any history rewrite are owner-only; no validity probe. |
| F7 | Agent action has OIDC permission and no explicit job-scoped token; Task 5. Actual tag protection/App permissions were not queried or changed. |
| F8 | Third-party titles are injected automatically; Task 6 removes this unnecessary input. No claim that prompt fencing is a security sandbox. |
| F9 | Maintenance agent can create issues while reading untrusted text; Task 5 separates analysis/publication. No exfiltration attempted. |
| F10 | Author text enters scanner description outside the fenced fields; Task 4. |
| F11 | Remote values become Python source; Task 6. |
| F12 | Shared cache statistics observable; Task 4 isolates HTTP state without changing pseudonym values. |
| F13 | Missing announcement discriminator; Task 1. |
| F14 | Repeated unclosed script/style regex scans; Task 2. |
| F15 | Course labels enter prompt without provenance; Task 4. |
| F16 | Same HTML helper as F14, second vulnerable regex; Task 2. |
| F17 | Read-only inspection confirms token interpolation into private launcher's argv; it is outside this worktree and not tracked here. Owner must fix its source/distribution; never edit the other agent's checkout. |
| F18 | Course-topic exemption confirmed at `core/client.py:266-269,295-306`; current endpoint tests explicitly preserve it. Fix needs staff/content classification and OAuth-overlap reconciliation; left unimplemented under the compatibility decision below. |

## Breaking changes (needs Vishal)

These proposals are **not** part of Phase 2 and must stay unimplemented:

- Removing/renaming tools or arguments, consolidating overlapping public views,
  changing default roles/gates, or replacing legacy result strings with one
  universal error schema. Stable adapters are worth their small duplication.
- Making code execution use a credential-free host capability bridge (#157):
  promising direction, but changes the code API, write availability and runtime
  boundary. No new worker, service or proxy in this run.
- Changing stable pseudonym generation to deployment-secret HMACs; it would
  invalidate existing local correlation maps.
- F18: anonymizing every course-topic body would redact currently preserved
  staff contact details and change tests/documented behavior; trusting unknown
  authors would retain the leak. Agree a staff-aware policy, then make a narrow
  client change after reconciling #510/#441. Do not silently choose either.
- Requiring new GitHub environments/PyPI trust settings or protected-tag rules
  before release: must coordinate the external settings with the maintainer.
- New OAuth flows or token storage. Verified open PR #510 touches client,
  config, server, execution, package/lock and OAuth files; #441 also touches
  anonymization, credentials integration, assignments and rubrics. Avoid these
  files except Task 2/4's isolated anonymization fixes; record exact overlap.

## Verification limits and remaining audit opportunities

Baseline pagination has real controlled-transport tests for short linked pages,
opaque cursors, cycles, budgets, concurrency and credential containment
(`tests/core/test_client_state_machine.py`). Do not replace it with page-length
heuristics. No direct Python list call was found silently treating `per_page=100`
as an all-results guarantee; bounded tools explicitly signal more data.
Error handling is intentionally mixed: dict tools use an error key, string
tools use an Error prefix, some JSON strings are normalized by
`core/tool_results.py`; `RequestFailure` preserves uncertain-write provenance.
Retain these contracts and test negative side effects rather than standardizing
everything in one risky pass.

The local security suite skips optional vulnerability/license tooling and
several not-implemented assertions. A green suite is not a completed penetration
test. Local checks cannot establish Windows behavior, hosted Entra configuration,
real Canvas sanitizer limits, container egress guarantees, release OIDC audience
isolation, or the validity/revocation of the historical credential. Do not run
hosted workflows or live Canvas operations to fill these gaps.

## Review Focus

Uncovered inputs/conditions at planning time, most likely to harm a caller first:

- An announcement ID resolves to a discussion, an absent/string discriminator, or changes type between preview and confirmation; no discussion may be deleted (Task 1).
- Long malformed HTML, dotted email-like text and repeated attribute delimiters must finish without shortening legitimate syllabus/content output (Tasks 2–3).
- Course labels, scanner descriptions and forged fence markers inside MCP prompts must remain explicitly author data and never reach a fixer write-back (Task 4).
- Concurrent HTTP callers, cancellation and credential clearing must not share pseudonym cache samples or borrow the stdio cache (Task 4).
- Corrupt publisher archives, missing maintenance artifacts and hostile API count strings must fail before execution/publication and retain last-good data (Tasks 5–6).
- A student authors a course discussion topic with a contact address: its current exemption remains a known privacy gap pending the explicit staff-aware policy decision (F18, unimplemented).
- An opted-in TypeScript program bypasses Python write policy or fencing: existing architecture permits this; no test in this plan claims #157 is solved.

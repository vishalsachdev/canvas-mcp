# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.9.0] — 2026-08-10

### Security

- **Canvas-authored free text is now provenance-fenced before it reaches the
  model** ([issue 239](https://github.com/vishalsachdev/canvas-mcp/issues/239)).
  Page content including titles and media inventories (`get_page_content`,
  `get_page_details`, `get_front_page`), syllabus text (`get_syllabus`,
  `get_course_content_overview`), discussion topics/entries/replies
  (`get_discussion_topic_details`, `list_discussion_entries`,
  `get_discussion_entry_details`, `get_discussion_with_replies`), and inbox
  subjects and message bodies (`list_conversations`,
  `get_conversation_details`) are wrapped in explicit
  `<<<UNTRUSTED CANVAS CONTENT ...>>>` markers stating the text is data, not
  instructions. Author-controlled *derived* values (page and discussion-topic
  titles, embedded-media src/alt inventory) sit inside the fence too, not
  around it. Content is
  otherwise unaltered (no sanitization or loss); embedded marker lookalikes
  are degraded so fenced text cannot forge its own boundary. Fencing is
  applied at the tool output-formatting boundary only — never in the
  anonymization/client layer — so no fence can leak into content written back
  to Canvas.
- **All multi-recipient message sends are now two-step** (breaking):
  `send_bulk_messages_from_list`, `send_conversation` with more than one
  recipient, `send_peer_review_reminders`, and
  `send_peer_review_followup_campaign` require a preview→confirm round-trip.
  Calling without a `confirmation_token` returns a preview (recipients,
  rendered subject/body — for the campaign, the completion analytics and who
  gets which reminder) plus a single-use, content-bound token and sends
  nothing; sending requires calling again with the token and identical
  arguments. Tokens are void if anything changed in between (including the
  campaign's completion analytics or an assignment rename that alters the
  composed reminder). `send_conversation` stays a single call only for
  exactly one plain numeric user ID — expandable recipient aliases
  (`course_*`/`group_*`) fan out server-side and are treated as
  multi-recipient. The bulk preview renders **every** outbound message (not
  a sample), and rows with invalid or alias user IDs fail the preview before
  a token is issued. The campaign previews the full rendered subject/body of
  every batch and its token commits to that text, so an assignment rename
  between preview and confirm voids the token. Confirmation claims are only
  released on provable rejections (4xx validation/auth statuses: 400, 401,
  403, 404, 422, or pre-flight validation); timeouts, 408/409/429, and all
  5xx are treated as ambiguous — the POST may have been processed — so the
  claim stays spent and a retry cannot double-send. Shared outbound
  validation (subject length, mode, marker check) is enforced at the
  conversation-POST choke point, so no composed path can route around it.
  This extends the `submit_assignment` confirmation pattern to the educator
  side, so prompt-injected content read from Canvas cannot silently trigger
  a fan-out send.
- **Completeness pass — author-controlled free text is fenced across every
  read tool.** Beyond bodies and titles, the following author-set fields are
  now provenance-fenced at their tool-output boundary: assignment
  names/descriptions, module names + item titles, discussion/announcement
  author display names, page editor display name, uploader-set filenames,
  group names + member names/emails, roster user names/emails, student
  analytics names, rubric titles + criterion/rating descriptions + assessment
  comments, peer-review comment text + participant names, and student-planner
  assignment titles. Short identity labels (names, emails, filenames) use a
  compact single-line fence so dense rosters/analytics stay readable; bodies
  and descriptions keep the block fence. A recursive key-based fence covers
  the peer-review analyzer JSON at the model-facing return only (the CSV and
  on-disk exports are untouched — CSV injection is handled separately). The
  only author-controlled fields deliberately left unfenced are course
  names/codes and the caller's own profile (low-risk course/self identity).
- **Known limitation:** enabling `execute_typescript`
  (`EXECUTE_TYPESCRIPT_ENABLED=true`; off by default, disabled on hosted
  deployments) voids the confirmation-token and fencing guarantees above —
  the sandbox receives `CANVAS_API_TOKEN` and can reach the Canvas API
  directly, so code run there can fan out messages or write content without
  any preview/confirm step. This is the known
  [issue 157](https://github.com/vishalsachdev/canvas-mcp/issues/157) class
  (the in-process network guard is bypassable); a tool-level block would be
  security theater while raw fetch to the Canvas host remains open, so it is
  documented rather than faked.
- **The confirmation-token guard authenticates before recording a nonce**, so
  a flood of forged/unsigned tokens can no longer grow its in-memory map
  (a memory-exhaustion DoS). Tokens gained a fingerprint-independent
  authenticator (so the burn-on-mismatch path can still authenticate a
  genuinely-issued token), a max-length cap, and a hard ceiling on the tracked
  nonce set. Because only authenticated, unexpired tokens can ever be
  recorded, the tracked set is inherently bounded by issuance-rate × TTL and
  each entry self-drains on its own expiry — so there is **no capacity cap and
  no eviction** (either would drop a legitimate burn or resurrect a used
  nonce). Recording is unconditional for an authenticated token, so a
  burn-on-mismatch always keeps that token invalid for its full remaining
  signed lifetime.
- Grading writers (`bulk_grade_submissions`, `grade_with_rubric`) reject
  fenced content in grade comments **and every per-criterion rubric comment**,
  so a comment lifted from fenced read output cannot publish provenance markers
  into the student-visible gradebook. The student write tools (`submit_assignment`
  body/comment, `comment_on_my_submission`) and `create_rubric`
  (title + all criterion/rating descriptions) carry the same backstop.
- Write tools that publish free text (`create_page`, `edit_page_content`,
  `post_discussion_entry`, `reply_to_discussion_entry`,
  `create_discussion_topic`, `update_discussion_topic`, `create_announcement`,
  `create_assignment`, `update_assignment`, `create_module`, `update_module`,
  `add_module_item`, `update_module_item`,
  `send_conversation`, `send_peer_review_reminders`,
  `send_bulk_messages_from_list`) refuse content containing the fence markers
  in every writable text field, titles included, so a fenced read result
  cannot be round-tripped into live Canvas content. The check also runs at
  the shared conversation-POST choke point on the final composed subject and
  body, catching markers that arrive via Canvas-authored inputs such as an
  assignment name.

### Supply chain

- **The repository now publishes an OSSF Scorecard** to the public OpenSSF API
  (`api.scorecard.dev/projects/github.com/vishalsachdev/canvas-mcp`), currently
  7.1/10, refreshed weekly and on every push to `main`. Along the way: all
  GitHub Action references are pinned by commit SHA (one was a mutable branch
  ref), every workflow declares least-privilege token permissions, the Docker
  base image is pinned by digest, and Dependabot covers pip, npm, docker, and
  Actions.
- **`canvas-mcp.mcpb` releases now ship SLSA build provenance** (attached as
  `canvas-mcp.mcpb.intoto.jsonl`, starting with this release). The bundle is
  downloaded independently of PyPI, so PyPI's provenance never covered it.
  Verify with `gh attestation verify canvas-mcp.mcpb --repo
  vishalsachdev/canvas-mcp`. The bundle is also now built in a job with no
  release-write authority, and the packing CLI is version-pinned instead of
  `@latest`.
- Patched a DoS in the `execute_typescript` sandbox's transitive `diff`
  dependency (GHSA-73rr-hh4g-fpgx; 4.0.2 → 4.0.4 via npm override).

### Removed

- **The npm setup wizard (`npx canvas-mcp setup`) is retired and the `canvas-mcp`
  npm package deprecated** (#249). The wizard wrote client configs pointing at
  the retired `mcp.illinihunt.org` hosted endpoint (no DNS record) while also
  collecting the user's Canvas API token, so every run produced a broken config.
  The documented install paths — the Desktop Extension (`.mcpb`) and manual
  client configuration per the README — were already the only ones referenced
  anywhere in the docs. The npm package name remains reserved (deprecated, not
  unpublished) so it cannot be claimed by a third party.
- `docs/workshop.html` — an orphaned March 2026 workshop page (not linked from
  the site) whose instructions were built around the retired wizard and hosted
  endpoint.

## [1.8.0] — 2026-08-09

### Security

A repository-wide security scan produced twelve findings. Eleven are addressed
here; the twelfth (sandbox egress) is partially addressed and labelled honestly
rather than papered over. Two independent review rounds ran against the result.

#### Cross-boundary primitives reachable from a remote caller

- **`download_course_file` was an arbitrary write, and `upload_course_file` an
  arbitrary read, on a shared HTTP server.** Download let the caller choose the
  destination directory while Canvas supplied the filename and bytes; upload let
  the caller name any path the service account could read and copy it into their
  own Canvas course. Both are legitimate on a local stdio server — that
  filesystem *is* the caller's own machine — so each is refused **by transport**
  rather than removed. Download points at `read_course_file`, which returns
  content in the response and was already the right tool for a remote caller.
- **Local downloads no longer overwrite.** Canvas controls the filename, so a
  course file named `.zshrc` could silently truncate a real file in the chosen
  directory. The destination is now created exclusively and owner-only
  (`O_EXCL`, `O_NOFOLLOW` where the platform has it, mode `0600`), which also
  refuses a pre-planted symlink, and a failed download unlinks its partial file
  instead of leaving truncated content behind.

#### A hard-coded `/submissions/self` suffix did not guarantee self-scoping

- **A path delimiter in an identifier retargeted self-scoped student tools at
  another student's submission.** Identifiers are typed `str | int` and
  interpolated into a path template, and that union accepts any string. Measured,
  not inferred: with `assignment_id="123/submissions/456?"`, `get_my_submission`
  issued a live request to `/api/v1/courses/60366/assignments/123/submissions/456`
  while the endpoint string still ended in `/submissions/self`. Canvas answers
  that for any token also holding grading permission, so a mixed student/grader
  account could read or comment on another student's FERPA-protected submission.
  `#` and percent-encoded `%2F` behaved the same. Closed in two layers:
  `make_canvas_request` now refuses any endpoint containing `?`, `#`, or a `..`
  segment — every caller passes query parameters via `params=`, so a delimiter in
  the path is always smuggling, and this covers all 23 interpolation sites at
  once — and `coerce_canvas_id()` pins the identifier grammar to ASCII digits at
  the self-scoped routes.

#### Privacy and untrusted content

- **The MCP Registry manifest published `ENABLE_DATA_ANONYMIZATION` default
  `false`** while the code, the Dockerfile, and `env.template` all defaulted it
  to `true`. For any Registry client that materializes declared defaults, the
  advertised install path started with student-data anonymization **off**. The
  manifest now declares `true`, and a test compares all four sources so the
  drift cannot recur silently.
- **CSV exports could hand a spreadsheet an executable formula.** Peer-review
  comment text is authored by another student, and Canvas names and emails are
  user-controlled on many instances. A comment beginning `=`, `+`, `-`, `@`, tab,
  or carriage return is evaluated as a formula when an instructor opens the
  report; quoting does not prevent this. `core/csv_safety.py` is now the single
  encoder for every export path. Two exporters also assembled CSV by string
  concatenation and escaped only double quotes, so a comment containing a comma
  or newline produced malformed rows; both now use the stdlib writer.

#### Credentials

- **A cleartext `http://` Canvas URL is refused instead of warned about.** The
  token is sent in an `Authorization` header on every request, so a cleartext
  origin exposes a credential for student records. Enforced on **both** startup
  paths — HTTP mode never calls `validate_config()`, and it is the more
  dangerous case, since the Canvas URL is server-pinned and one typo would leak
  every caller's token rather than only the operator's. `CANVAS_ALLOW_INSECURE_HTTP`
  is a development-only escape hatch restricted to loopback addresses.
- **The setup CLI writes token-bearing configs and backups `0600`** instead of
  inheriting an umask that yields `0644`, and no longer echoes the full token to
  the terminal, where it would land in scrollback and shell history.

#### Availability and blast radius

- **The unauthenticated access-confirm route is bounded.** It is intercepted
  ahead of every token gate and read an unlimited body; it now requires POST and
  stops at 8 KiB, chunked uploads included, for a payload that only ever carries
  one short signed token.
- **Denied-identity notifications are rate-limited before any work happens.** The
  403 is returned first (correctly), so a denied caller can repeat at will, and
  the duplicate-mail cooldown lived inside the scheduled task — after an Azure
  credential, a client, an asyncio task, and a storage round-trip. Admission
  control now runs first: 200 repeated denials cause one client build.
- **Code execution fails closed when isolation is unavailable.** An explicit
  `TS_SANDBOX_MODE=container` fell back to running caller-supplied TypeScript
  directly on the host when no runtime was present or the image name was
  malformed. It now refuses, and no unsandboxed mode may run while serving an
  HTTP request.
- **The weekly AI maintenance workflow lost its excess privileges.** It reviews
  public issue text and web results — writable by anyone — while holding a
  GitHub token, so the token is the control: reduced from `contents:write` +
  `pull-requests:write` + `Bash(gh:*)` to `contents:read` + `issues:write` and
  four specific `gh` commands, with the prompt now framing fetched content as
  data rather than instructions.
- **Security tests can fail the build.** `security-testing.yml` ran
  `tests/security/` with `continue-on-error: true`, so every invariant in that
  suite — including the anonymization and authorization ones predating this
  work — passed green through any regression.

#### Known limitation

- **Sandbox egress remains best-effort and now says so.** `--network=none` is
  passed when outbound is blocked and the allowlist is empty, which is real
  kernel-level enforcement — but when blocking is on, the Canvas host is
  automatically allowlisted, because executed code exists to call Canvas. So in
  every working configuration the allowlist is non-empty and egress falls back to
  patching Node APIs in-process, which `child_process`, `dgram`, and bundled
  utilities can step around while `CANVAS_API_TOKEN` is in the environment. The
  tool now emits an explicit best-effort warning instead of implying enforcement.
  Closing it needs an egress proxy or network namespace
  ([#157](https://github.com/vishalsachdev/canvas-mcp/issues/157)).

### Changed

- **Breaking: an `http://` `CANVAS_API_URL` now aborts startup** in both stdio
  and HTTP transports. Set `CANVAS_ALLOW_INSECURE_HTTP=true` for a loopback
  development Canvas; it does not permit cleartext to a remote host.
- **Breaking: `download_course_file` and `upload_course_file` are stdio-only.**
  Over HTTP transport they refuse with a message pointing at the alternative.
- **Breaking: `download_course_file` errors rather than overwriting** an existing
  destination file.
- **The MCP Registry manifest's anonymization default changed from `false` to
  `true`**, matching every other distribution channel.
- **Dependency floors raised to the first safe patch lines** (PR #255):
  `fastmcp>=3.4.4` — the previous `>=3.2` floor permitted 3.2.0–3.2.3 on a
  fresh unlocked install, which carry CVE-2026-32871 and CVE-2026-27124 —
  and `uvicorn>=0.50.0`. Locked resolutions were already safe.
- **`contents: read` least-privilege permissions on the test, deploy, and
  security workflows** (PR #255), with a policy test asserting them so the
  scope-down cannot silently regress.
- **Documented role-profile tool counts corrected to measured values**
  (PR #255): student ~37, educator ~88, all 94 by default and 99 with every
  feature-gated tool enabled. README no longer claims rubric creation must be
  done in the Canvas UI (`create_rubric` shipped in v1.3.0).

### Known issues

- The npm setup wizard still configures clients against the retired
  `mcp.illinihunt.org` endpoint, which no longer resolves. Converting it to the
  local stdio path is not a URL swap — the documented stdio config uses an
  absolute venv binary path and credentials live in the server's `.env`
  ([#249](https://github.com/vishalsachdev/canvas-mcp/issues/249)).


## [1.7.0] — 2026-08-08

### Added
- **Missing MCP tool annotations across ~29 write tools**, plus docstrings for `list_courses`' previously undocumented `include_concluded` / `include_all` flags ([#200](https://github.com/vishalsachdev/canvas-mcp/issues/200), first contribution from the Copilot coding agent in [#201](https://github.com/vishalsachdev/canvas-mcp/pull/201)).
- **`tests/test_tool_metadata.py` gates the annotation contract.** It enumerates the live registry rather than a hand-maintained list, so a *new* tool registered with a bare `@mcp.tool()` fails CI instead of shipping unannotated — the failure mode that produced #200. The registry is built with every feature gate switched on (`EXECUTE_TYPESCRIPT_ENABLED`, `STUDENT_WRITE_TOOLS`), since coverage must follow capability rather than default configuration; checking only the default set would have passed while `execute_typescript` — arbitrary TypeScript against the caller's Canvas token — shipped with no annotations at all. It is now marked destructive and non-idempotent, the conservative reading, because nothing about caller-supplied code can be inspected in advance. Classifications for grade-writing and deleting tools are pinned explicitly, so a flip has to be a deliberate edit rather than a silent diff.

### Changed
- **Tool annotations now follow the MCP spec rather than a local convention.** `destructiveHint=False` asserts a tool "performs only additive updates"; the repo had been reading it as "doesn't delete", which left `bulk_grade_submissions`, `grade_with_rubric`, `edit_page_content`, `bulk_update_pages`, `fix_accessibility_issues`, every `update_*`, `upload_course_file` and `create_student_anonymization_map` claiming to be additive-only while they overwrite grades, page bodies, files and settings. Those are now `destructiveHint=True`. A client has no way to know the server meant something narrower, and grading tools are the worst place for that gap. The `create_` prefix turned out not to be a safe guide: `create_page` with `front_page=True` unseats the course's existing front page, and both `create_rubric` with an `assignment_id` and `associate_rubric` attach a rubric over whatever was already associated, so those three are destructive too. Genuinely additive tools (`create_announcement`, `create_assignment`, `create_discussion_topic`, `create_module`, `create_rubric_from_csv`, `post_*`/`reply_*`, `send_*`, `add_module_item`, `assign_peer_review`, `mark_conversations_read`) stay `False`, so this costs no extra confirmations where none are warranted ([#204](https://github.com/vishalsachdev/canvas-mcp/issues/204)).
- **`idempotentHint` is now set on every write tool** — it was never set anywhere, leaving the third of #200's three annotations unaddressed. `update_*`, `delete_*` and `edit_page_content` converge on the same end state and are idempotent; anything that creates a record is not, including `upload_course_file`, whose default `on_duplicate="rename"` writes a new file on every call. Idempotency is judged on a tool's **whole effect, not just its primary resource**: `bulk_grade_submissions` and `grade_with_rubric` settle on the same score but append a new submission comment whenever `comment` is supplied, and `update_page_settings` / `bulk_update_pages` settle on the same body but re-notify the course whenever `notify_of_update=True` — so all four are non-idempotent. `delete_announcements_by_criteria` is non-idempotent for a related reason: it re-derives its target set at call time and slices `matched[:limit]`, so an identical retry deletes the *next* batch, up to twice the requested limit. (Its sibling `bulk_delete_announcements` takes explicit ids and remains idempotent.) A retry that silently duplicates feedback to every student in a course is the harm this hint exists to prevent. A host retrying a timed-out call can now tell these apart ([#204](https://github.com/vishalsachdev/canvas-mcp/issues/204)).
- **`check_enrollment` documentation is institution-neutral.** "NetID" is a UIUC term; the parameter accepts a NetID, uniqname, campus ID, or email-style Canvas login, and the docs now say so — along with the fact that it is not a display name, and that `role` defaults to `student` ([#199](https://github.com/vishalsachdev/canvas-mcp/issues/199)).
- **Anonymization consolidated into the client layer.** The FERPA scrub had been applied at several call sites, which is a design that fails quietly: a new tool that forgets the call is anonymized nowhere, and nothing tells you. It now runs in one place on the way out of `make_canvas_request`, so coverage follows the request rather than the author's memory ([#179](https://github.com/vishalsachdev/canvas-mcp/issues/179)).
- **Explicit `/api/quiz/v1` routing in the core client**, with `/api/v1` normalization and the anonymization gate both unchanged, plus `api_root` threaded through `fetch_all_paginated_results` so paginated calls against a non-default API root no longer fall back to `/api/v1` partway through ([#192](https://github.com/vishalsachdev/canvas-mcp/issues/192), [#193](https://github.com/vishalsachdev/canvas-mcp/pull/193), [#197](https://github.com/vishalsachdev/canvas-mcp/pull/197)).

### Fixed
- **`check_enrollment` reported "no enrollment" for people plainly on the roster.** Two independent defects, both rooted in an unverified premise about identifiers. (1) The matcher required exact equality against `login_id`/`sis_user_id`. Canvas does not define what `login_id` holds — measured live, UIUC stores the bare NetID (`vishal`), while instances that provision Canvas logins from email store the full address (`uniqname@umich.edu`), which the bare identifier could never match. Matching is now two-pass: exact equality across the whole roster first, then email-local-part equivalence, so `zqian` finds `zqian@umich.edu` and vice versa. Because this tool is documented as an external access gate, the fallback only ever runs in the direction where the roster is authoritative — a bare identifier may match a domain-qualified roster value, never the reverse. Anything it cannot verify returns the new **AMBIGUOUS** answer instead of a yes or a no: two differing full addresses (`jdoe@school.edu` vs `jdoe@other.edu`) are different people and a bare secondary `sis_user_id` on that user cannot smuggle the match back in; a bare `jdoe` matching both `jdoe@a.edu` and `jdoe@b.edu` will not let roster ordering decide an authorization question; and a qualified identifier offered to a roster that stores bare IDs is unverifiable, since `jdoe@attacker.example` has exactly as much claim on a stored `jdoe` as the real domain does. (2) An email-form identifier was rejected by the input guard *before any Canvas call was made*, because the pattern excluded `@`; `@` and `+` are now accepted ([#199](https://github.com/vishalsachdev/canvas-mcp/issues/199)).
- **A role-scoped `check_enrollment` "NO" now says what the person actually is.** `role` defaults to `student`, and the role filter was pushed to Canvas as `type[]`, which hid every other enrollment the subject held. Asking about a teacher therefore returned `NO — … has no active 'student' enrollment`: true, but indistinguishable from "not in this course". The whole roster is now fetched (the same single request) and the role evaluated locally, so a negative names the roles the subject does hold — `They ARE enrolled in this course, as: TeacherEnrollment` — while a genuine stranger still gets a clean NO with no role clause. `EnrollmentResult` gained `roles_held` ([#199](https://github.com/vishalsachdev/canvas-mcp/issues/199)).
- **`upload_course_file` no longer dumps files into a stray "unfiled" folder.** With no `folder_path`, the tool omitted `parent_folder_path` entirely — which is not "use the root", it makes Canvas create and use a folder literally named `unfiled`. The docstring had always documented the root as the default, so this was a doc-vs-behavior divergence. Verified live with a three-way A/B against a real course: no parameter → `course files/unfiled`; `parent_folder_path=""` → `course files`; `parent_folder_id=<root>` → `course files`. The empty string is now always sent, which targets the root without the extra `/folders/root` lookup the id form would need ([#198](https://github.com/vishalsachdev/canvas-mcp/issues/198)).

#### Writes that reported success without doing anything

Four reports arriving within ~40 minutes on 2026-08-03 — three from a first-time reporter testing v1.6.0 with a **student** token — turned out to be one defect class: trusting a Canvas `200` that did less than asked. All four were fixed and deployed the next morning.

- **`create_announcement` created a plain discussion topic and called it an announcement.** Canvas silently dropped `is_announcement` for a caller without announcement permission, returning `200` with an ordinary topic. The tool built its success message from `id`/`title` and never checked `is_announcement` in the response, so the post landed in the wrong place while the caller was told it worked ([#220](https://github.com/vishalsachdev/canvas-mcp/issues/220)).
- **`get_my_peer_reviews_todo` reported "no pending peer reviews ✅" when two were assigned.** Two defects stacked: a permission-gated listing returned an error dict, which a bare `isinstance(..., list)` check discarded without a word — making a `401` indistinguishable from an empty list — and the tool never filtered by `assessor_id` at all, so even when it did return rows they were not scoped to the caller. A false "you're all caught up" is the worst possible failure for this tool ([#219](https://github.com/vishalsachdev/canvas-mcp/issues/219)).
- **`mark_module_item_done` reported success on items that cannot be marked done.** Canvas's `done` endpoint only has an effect on items carrying a `must_mark_done` completion requirement; measured live, ordinary items carry `completion_requirement: null` and the `PUT` is a silent no-op. The tool now checks the requirement and says so plainly instead of claiming a state change that never happened ([#221](https://github.com/vishalsachdev/canvas-mcp/issues/221)).
- **`unconfirmed_write_warning` is now shared infrastructure.** The guard introduced for rubric writes in 1.6.0 gained a third consumer here, so it moved from a rubrics-local helper to `core/write_confirmation.py`. The rule it encodes: never report a write as successful on HTTP status alone — confirm the intended effect in the response body, and say so honestly when you cannot.

#### Other fixes

- **`get_my_upcoming_assignments` ignored the `days` range and always returned 7 days.** Self-diagnosed correctly by the reporter: `/users/self/upcoming_events` is hardcoded server-side to a 7-day window (it is the dashboard "Coming Up" feed), so the `days` parameter could only ever *narrow* an already-capped list, never widen it — `days=30` quietly lied. Now uses the Planner API with a real date window. Two bonuses fell out of the switch: planner items carry `submissions.submitted`, which removes the per-assignment N+1 the old path needed, and graded discussions are included, which the old feed omitted ([#222](https://github.com/vishalsachdev/canvas-mcp/issues/222)).
- **`bulk_update_pages` failed with a Canvas 500 on every page.** It sent a nested `wiki_page` dict with `use_form_data=True`; form encoding cannot represent nesting, so the Python `repr` of the dict went out on the wire ([#207](https://github.com/vishalsachdev/canvas-mcp/issues/207)).
- **`mark_conversations_read` errored on every call.** The mirror-image bug: it sent JSON to `/conversations`, which Canvas requires as form data, so `conversation_ids[]` never arrived as a repeated parameter. Its sibling `send_conversation` had carried a code comment about this requirement for the whole time ([#208](https://github.com/vishalsachdev/canvas-mcp/issues/208)).
- **`create_rubric_from_csv`'s documented CSV format was wrong and created zero rubrics.** The documented columns did not match what the parser read, so anyone following the docs got nothing. The format is corrected, `succeeded_with_errors` is now handled as its own outcome rather than folded into success, and `error_data` is surfaced to the caller instead of dropped ([#190](https://github.com/vishalsachdev/canvas-mcp/issues/190)).

### Security
- **`cryptography` 49.0.0 → 50.0.0**, clearing **CVE-2026-69247**. The stale lockfile had been failing the Dependency Vulnerability Scan on every PR opened that day, so this was blocking unrelated work as well ([#226](https://github.com/vishalsachdev/canvas-mcp/pull/226)).

### Internal
- **mypy is clean and gated in CI** — 229 errors to 0, with `mypy src/` added to the lint job ([#106](https://github.com/vishalsachdev/canvas-mcp/issues/106)).
- **`TOOL_MANIFEST.json` is at full registry parity and CI-gated.** The manifest documented 30 tools against a live registry of 99; the 69 missing entries were derived from each tool's real signature and registered `inputSchema` rather than written by hand ([#173](https://github.com/vishalsachdev/canvas-mcp/issues/173)).
- **`tools/README.md` documents every tool in the manifest** — 34 were missing, plus `get_course_content_overview`, which was referenced but never documented ([#215](https://github.com/vishalsachdev/canvas-mcp/issues/215)).
- **A closing-keyword guard blocks accidental issue closures.** GitHub closes an issue on any `fixes|closes|resolves #N` in a merged PR body *or* in a commit message landing on `main` — including prose that only *describes* other work. One issue was closed twice this way, the second time by a commit whose message documented the first accident. One detector (`scripts/check_closing_keywords.py`) is now shared by a `commit-msg` hook and a CI workflow; it blocks keywords mid-sentence and allows ones that open a line, a split derived by replaying it over every commit on `main` rather than chosen by taste. Contributors run `./scripts/install-hooks.sh` once per clone ([#231](https://github.com/vishalsachdev/canvas-mcp/pull/231)).

## [1.6.0] — 2026-07-30

### Added
- **Tier 1 student write tools, off by default behind a two-key gate.** A student-role caller can now act on their own work — the tools are enabled only when the operator sets `STUDENT_WRITE_TOOLS` (an explicit per-tool allowlist, empty by default), and optionally further restricted per course by `COURSE_AGENT_POLICY_ENABLED`, which can only narrow that allowlist and never widen it. The policy carrier is the **course syllabus**; a draft that used a course page as the carrier was deliberately removed, because a page's `editing_roles` proves who may edit it, not who wrote it — so a student able to edit the page could author their own permissions. Multi-worker HTTP deployments have an extra note in `env.template` for `submit_assignment` ([#170](https://github.com/vishalsachdev/canvas-mcp/issues/170)).
- **`get_my_enrollments` and `get_my_profile` tools** — answer "what am I enrolled in, and as what role?" and "who am I?" about the authenticated caller. Registered under **every** role profile because they describe only the caller and need no roster permission. `get_my_enrollments` reads `GET /courses` (which returns course name/code *and* the caller's own `enrollments[]` in one call) rather than `/users/self/enrollments`, which returns bare course IDs, and reports all roles when the caller holds more than one enrollment in a course ([#171](https://github.com/vishalsachdev/canvas-mcp/issues/171)).

### Changed
- **⚠️ BREAKING for existing `execute_typescript` users: code execution is now opt-in.** `EXECUTE_TYPESCRIPT_ENABLED` defaults to **`false`** (it was effectively `true` for stdio installs). If you use `execute_typescript`, you must now set `EXECUTE_TYPESCRIPT_ENABLED=true` explicitly — otherwise the tool is unavailable. This follows the hardening direction in [#157](https://github.com/vishalsachdev/canvas-mcp/issues/157): a code-execution surface should be a deliberate choice, not something you get by default ([#178](https://github.com/vishalsachdev/canvas-mcp/issues/178)).
- **The Docker image now ships `ENABLE_DATA_ANONYMIZATION=true`** (was `false`), matching the code default. The FERPA layer is opt-out rather than opt-in for anyone deploying from the image ([#178](https://github.com/vishalsachdev/canvas-mcp/issues/178)).
- **Upgraded to `fastmcp` 3.x** (`>=3.2,<4`, from 2.14.7), which clears **PYSEC-2026-2475** and **PYSEC-2026-2476**. No user-facing changes: same tools, same transports, HTTP endpoint unchanged at `/mcp`. Staging-validated before production deploy ([#145](https://github.com/vishalsachdev/canvas-mcp/issues/145)).
- **`list_courses` and `get_course_details` now surface your own role in each course.** Canvas already returns the caller's `enrollments[]` on both endpoints; the tools were discarding it, which pushed agents toward roster tools they have no permission for. `get_course_details` now says "You have no enrollment in this course" explicitly rather than staying silent ([#171](https://github.com/vishalsachdev/canvas-mcp/issues/171)).

### Fixed
- **`associate_rubric` never actually attached the rubric.** It sent a nested `rubric_association` JSON body to `PUT /courses/:id/rubrics/:id` with no form encoding. Canvas answered **200** — the rubric itself is valid — but never parsed the association parameters, so nothing appeared on the assignment page while the tool reported "successfully associated". Now posts flat bracket-notation form data to `POST /courses/:id/rubric_associations`. Verified against a live Canvas instance with an A/B against the old code path: old → `rubric_association: None` and no rubric in the UI; fixed → association created and rendered ([#181](https://github.com/vishalsachdev/canvas-mcp/issues/181)).
- **No rubric write reports success without a confirmed association.** [#180](https://github.com/vishalsachdev/canvas-mcp/issues/180) and [#181](https://github.com/vishalsachdev/canvas-mcp/issues/181) were the same defect in two different functions, each with its own idea of what counted as proof. The check now lives in one place (`rubric_association_id`), which requires an **id** in the payload rather than a truthy dict — closing a latent hole where an association object carrying no id was accepted as a successful bookmark.
- **Created rubrics are bookmarked into the course so Canvas shows them.** A rubric returned with `rubric_association: null` is listed by `GET /courses/:id/rubrics` but does not appear in the Canvas Rubrics UI. `create_rubric` now creates the Course bookmark association explicitly and never reports plain success on an orphaned rubric ([#180](https://github.com/vishalsachdev/canvas-mcp/issues/180)).
- **HTTP transport now runs stateless (`stateless_http=True`)**, eliminating the stale-session hang for hosted deployments. Previously the server kept an in-memory session table; a host restart (e.g. Azure App Service recycle) dropped it, the next request's `Mcp-Session-Id` drew a 404, and `mcp-remote` hung indefinitely instead of re-initializing. With stateless HTTP every request is self-contained — credentials already arrive per-request via `X-Canvas-Token`, and no tool uses server-initiated session features, so nothing can go stale ([#159](https://github.com/vishalsachdev/canvas-mcp/issues/159)).
- **`create_student_anonymization_map` produced a useless map.** It fetched the roster *through* the anonymizer, so it recorded pseudonym-to-pseudonym pairs; the tool cannot have worked as intended since anonymization became default-on. `fetch_all_paginated_results` gained an opt-in `skip_anonymization` flag (default off, so every other caller is unchanged) and this one caller uses it. The export writes a local file for an instructor who already has roster access ([#179](https://github.com/vishalsachdev/canvas-mcp/issues/179)).
- **`check_enrollment` no longer returns a confident false negative when the token lacks roster rights.** Canvas gates `user.login_id` and `user.sis_user_id` on roster-admin permission but does **not** error without it: the request returns HTTP 200 with the full roster and every `user` object silently reduced to `{created_at, id, name, short_name, sortable_name}`. The NetID match therefore never succeeded, and the tool answered a definitive "NO". It now detects that the identifier fields were withheld and returns **INDETERMINATE** — permission-blindness is not absence. A genuinely empty roster still returns a real "NO". A non-match is only reported as "NO" when **every** row exposed a matchable identifier: with even one row's identifiers withheld, the requested NetID could be sitting in it, so the answer is INDETERMINATE. A positive match is always trustworthy, however much of the roster is hidden. The prior docstring claim that a student token "yields a clean Canvas 403" was measured to be false and has been corrected ([#171](https://github.com/vishalsachdev/canvas-mcp/issues/171)).

### Security
- **The anonymizer now runs a recursive identity scrub as the baseline on every sensitive payload**, with the typed per-shape handlers demoted to additive refinements. Previously the `data_type` heuristic could mis-route a dict or fabricate fields, so nested identities slipped through unscrubbed. Key properties, all under test: anonymization **never adds a key that was not in the input**; `name`/`display_name` are rewritten only with a corroborating user signal, so course, group, and module labels survive intact; endpoint matching is segment-aware and query-stripped (mirroring the [#165](https://github.com/vishalsachdev/canvas-mcp/issues/165) gate fix); `time_zone`/`locale` are nulled on person records only. `/submissions/self` is excluded so a student can read their own submission back, anchored on the literal `self` segment with regression tests against the [#164](https://github.com/vishalsachdev/canvas-mcp/issues/164) bypass class ([#166](https://github.com/vishalsachdev/canvas-mcp/issues/166)).
- **Anonymization now covers the Inbox and page authorship, via three tiers instead of an all-or-nothing switch.** `/conversations` was matched by none of the gate's sensitive segments (`users`/`submissions`/`enrollments`/`analytics`), so `list_conversations` and `get_conversation_details` returned the raw payload: real names, `pronouns`, subject lines, and student email addresses inside message previews. Verified live against a real inbox (97 records, 3 distinct addresses). It is now `free_text` tier, which redacts free text and nulls `pronouns` while **keeping** `participants[].name`, because pseudonymising your own inbox makes "who emailed me?" useless and protects nobody: the caller is a participant in every record returned. `/pages` is now `identity` tier, which scrubs `last_edited_by` (previously passed through untouched) while leaving page bodies alone, since instructors legitimately publish contact details on course pages. Everything previously anonymized stays `full`, and the sensitive-segment checks still run FIRST so the #164 ordering bug cannot recur ([#179](https://github.com/vishalsachdev/canvas-mcp/issues/179)).
- **Covered the email-bearing keys the anonymizer missed:** `primary_email`, `unconfirmed_email`, and `contact_info` are now pseudonymised; `pronunciation` is nulled; `communication_channels[].address` is nulled container-scoped (so a calendar event's location is untouched); `full_name` and `unique_id` are *ambiguous* rather than strict, so they scrub on a person record but survive on a conversation participant. Not all of these were reachable by a registered tool, but `get_my_profile` (#171) reads `/users/self/profile`, which is where `primary_email` lives — fixing the key list before that shipped turns a future leak into a non-event ([#179](https://github.com/vishalsachdev/canvas-mcp/issues/179)).
- **Narrow anonymization carve-out for the caller's own identity.** `users/self` and `users/self/profile` are exempt from the anonymizer, because anonymizing them tells callers their *own* name is `Student_<hash>` — FERPA protects a record from others, never from its subject. This is a deliberate loosening of a privacy control, so it is an **exact full-path allowlist**, never a prefix or substring rule: `/users/self/enrollments` (which Canvas expands with `include[]=observed_users`, returning *other* students, and this gate cannot see request parameters), `/users/self/observees`, `/users/self/courses/*`, `/courses/*/enrollments`, `/courses/*/users`, and `/users/<other-id>/profile` all still anonymize, with explicit anti-bypass tests for each ([#171](https://github.com/vishalsachdev/canvas-mcp/issues/171)).
- **Fixed an anonymization bypass for `/courses/`-scoped student-data endpoints.** `_should_anonymize_endpoint()` checked its safe-endpoint list (which includes the substring `/courses`) before the student-data list, so enrollments, submissions, analytics, and discussion-content responses skipped central anonymization for nearly all real traffic. Sensitive checks now run first, discussion `/view`, `/entry_list`, and `/replies` endpoints are matched as student content, and the anonymizer now recurses into the discussion `/view` wrapper (`view`/`participants`/`replies`) and enrollment records' nested `user` dict — two shapes it previously passed through untouched. Added direct unit tests for the endpoint gate, which was previously untested ([#164](https://github.com/vishalsachdev/canvas-mcp/issues/164)).

### Internal
- **`ruff check src/ tests/` now runs in CI and is a required status check on `main`**, with the 13 pre-existing findings cleaned up so the gate starts green. First outside contribution to this repo — thanks @w3lld1 ([#175](https://github.com/vishalsachdev/canvas-mcp/issues/175), [#186](https://github.com/vishalsachdev/canvas-mcp/pull/186)).
- **`claude-review` removed from required status checks.** GitHub withholds repository secrets from `pull_request` workflows on forks, so the job's OAuth-token guard hard-failed on every external contribution — making outside PRs unmergeable without an admin bypass, with a misleading "secret is not set" error. It still runs and reports; it is now advisory ([#188](https://github.com/vishalsachdev/canvas-mcp/issues/188)).

## [1.5.0] — 2026-07-04

### Added
- **`get_syllabus` tool** — returns the complete Canvas Syllabus tab content without truncation (the overview tools only expose a ~1000-character preview, hiding later sections like grading policies and weighting). Supports `output_format` (`text`/`html`/`both`) and an optional `max_chars` cap that is explicitly marked when applied ([#134](https://github.com/vishalsachdev/canvas-mcp/issues/134)).
- **`create_rubric_from_csv` tool** — create a rubric from a CSV string via Canvas's native rubric CSV import endpoint, polling the import job to completion. A simpler alternative to the criteria-JSON `create_rubric` API ([#119](https://github.com/vishalsachdev/canvas-mcp/issues/119)).
- **`update_discussion_topic` tool** — educator-only partial update of an existing discussion topic or announcement (title, message, published/pinned/locked, `delayed_post_at`/`lock_at`, `require_initial_post`) via `PUT /courses/:id/discussion_topics/:topic_id`, mirroring the `update_assignment` pattern ([#154](https://github.com/vishalsachdev/canvas-mcp/issues/154)).

### Changed
- **Migrated to standalone `fastmcp` 2.x** from the frozen FastMCP 1.0 bundled in the MCP SDK (`mcp.server.fastmcp`). No user-facing changes: same tools, same transports, HTTP endpoint unchanged at `/mcp` ([#145](https://github.com/vishalsachdev/canvas-mcp/issues/145)).

### Security
- **Upgraded dependencies to clear known advisories** (`starlette`, `python-multipart`, `pyjwt`, `cryptography`, `pygments`, `idna`, `pydantic-settings`, `pytest`) via a full `uv.lock` refresh; all HTTP-transport-facing packages now ship fixed versions.
- **The dependency-scan CI now gates the build.** `pip-audit` runs against the exact locked dependency set (`uv.lock`, incl. the `hosted` extra) and fails on findings, instead of `continue-on-error` passing regardless. (`CVE-2025-69872` in the transitive `diskcache` is ignored pending an upstream fix.)
- **Hardened the `execute_typescript` container sandbox.** The workspace is now mounted read-only with a writable `tmpfs` for scratch, the container runs with `--cap-drop=ALL`, `--security-opt=no-new-privileges`, and `--pids-limit`, and the Canvas token is passed by env-var name rather than in the container runtime's argv (no longer visible via `ps`/`/proc`).
- **Added upper version bounds** on direct dependencies (`httpx`, `python-dotenv`, `pydantic`, `uvicorn`) so downstream installs can't silently pull an untested new major.

### Fixed
- **`strip_html_tags` no longer concatenates adjacent block elements.** Block-level tags (headings, paragraphs, list items, table rows, `<br>`) now convert to line breaks, so plain-text syllabus/overview output preserves structure instead of merging content across boundaries (e.g. `Grading` and `Final exam...`). Entity decoding now uses the stdlib `html.unescape`, covering smart quotes, dashes, and accents.
- **`summarize-course` prompt rendered raw JSON.** The prompt returned an out-of-spec `system`-role message that MCP clients received as literal JSON text; it now renders as a single user message ([#145](https://github.com/vishalsachdev/canvas-mcp/issues/145)).
- **`CANVAS_API_URL` is normalized to its canonical `/api/v1` form** at startup, so values with a trailing slash, missing `/api/v1` suffix, or bare hostname all work instead of producing 404s on every call ([#148](https://github.com/vishalsachdev/canvas-mcp/issues/148)).
- **`list_courses` honors `CANVAS_ROLE`** and scopes results to active enrollments, so student-profile servers no longer list courses from a teacher's perspective ([#140](https://github.com/vishalsachdev/canvas-mcp/issues/140)).
- **Docker image installs the `[hosted]` extra** (`azure-data-tables`, `azure-communication-email`, `azure-identity`), so the hosted access-approval flow ([#150](https://github.com/vishalsachdev/canvas-mcp/pull/150)) works in containerized deployments; stdio installs are unaffected ([#153](https://github.com/vishalsachdev/canvas-mcp/pull/153)).

## [1.4.0] — 2026-06-17

### Added
- **`check_enrollment` tool** — a data-minimizing roster-membership check (is a given NetID enrolled in a course?). Returns only a yes/no plus minimal enrollment metadata, never the roster, names, or grades. Requires a teacher-scoped token ([#126](https://github.com/vishalsachdev/canvas-mcp/pull/126)).
- **Claude Desktop Extension (`.mcpb`)** — one-click install in Claude Desktop (no terminal, no config-file editing). Built and attached to each GitHub Release automatically; prompts for your Canvas URL + token (stored in the OS keychain).

### Changed
- **Authenticated institutional hosted deployment.** The HTTP/streamable transport now supports Microsoft Entra ID (Azure AD) platform authentication fronting App Service, so an in-tenant institutional deployment can require campus identity per request ([#115](https://github.com/vishalsachdev/canvas-mcp/issues/115), [#125](https://github.com/vishalsachdev/canvas-mcp/pull/125)).

### Security
- **HTTP mode fails closed.** The server refuses to start in HTTP mode without an auth gate configured, unless `MCP_ALLOW_UNAUTHENTICATED=true` is explicitly set for an externally-authenticated front (e.g. Entra) ([#123](https://github.com/vishalsachdev/canvas-mcp/pull/123)).
- **Retired the public hosted server (`mcp.illinihunt.org`).** It had been
  deployed without an authentication gate, which left the sandboxed
  `execute_typescript` tool and an unvalidated `X-Canvas-URL` (SSRF shape)
  publicly reachable. No data was stored server-side and the published package
  itself was unaffected. Self-hosting the HTTP/streamable transport remains
  supported **behind your own authentication**; an authenticated institutional
  deployment is tracked in [#115](https://github.com/vishalsachdev/canvas-mcp/issues/115).

## [1.3.0] — 2026-05-02

### Added
- **`create_rubric`** — Programmatic rubric creation with criteria, ratings, and
  optional assignment association. Uses Canvas's bracket-notation form-data
  encoding (the encoding shape that previously caused the Canvas API 500
  errors). ([#100](https://github.com/vishalsachdev/canvas-mcp/pull/100))
- **`read_course_file`** — Read course file content. Enables remote MCP
  deployments to access uploaded Canvas files without requiring local
  filesystem access. Thanks [@DomBarker99](https://github.com/DomBarker99)!
  ([#90](https://github.com/vishalsachdev/canvas-mcp/pull/90))

### Fixed
- **"Event loop is closed" on user-scoped tools** (`get_my_todo_items`,
  `get_my_upcoming_assignments`, `get_my_peer_reviews_todo`, etc.). The shared
  `httpx.AsyncClient` and `asyncio.Semaphore` are now weakref-tracked against
  their owning event loop and recreated when a new loop starts (e.g., across
  multiple `asyncio.run()` calls in HTTP transport mode).
  ([#99](https://github.com/vishalsachdev/canvas-mcp/pull/99))

### ⚠️ Behavior change — bulk delete safety
- **`bulk_delete_announcements` now refuses batches over 25 IDs by default.**
  Pass `limit=N` to raise the cap, or `dry_run=True` to preview the titles
  that would be deleted without deleting them. **Existing callers passing
  more than 25 IDs in a single call must add `limit=N` explicitly.**
  ([#96](https://github.com/vishalsachdev/canvas-mcp/pull/96))
- Added a "Permanent — Canvas may retain a recycle-bin copy depending on
  admin settings" hint to the docstrings of `delete_page`,
  `delete_announcement`, `bulk_delete_announcements`,
  `delete_announcement_with_confirmation`, and
  `delete_announcements_by_criteria` so the irreversibility note appears in
  the tool description LLMs read, not just in the MCP `destructiveHint`
  annotation that most clients ignore.

### Maintenance
- Drop unused standalone `fastmcp` dependency; the bundled `FastMCP` from the
  official `mcp` SDK was already in use. Pin `mcp>=1.26,<2`. Pruned ~30
  unused transitive deps; net −794 lines from `uv.lock`.
  ([#93](https://github.com/vishalsachdev/canvas-mcp/pull/93))
- Remove dead code paths and bump dependency version floors.
  ([#92](https://github.com/vishalsachdev/canvas-mcp/pull/92))

**Tool count:** 88 → 90.

---

## [1.2.0] — 2026-04-10

- **Role-Based Tool Filtering** — Set `CANVAS_ROLE` to `student`, `educator`,
  or `admin` to see only relevant tools
  ([@Promithius-DR](https://github.com/Promithius-DR),
  [#84](https://github.com/vishalsachdev/canvas-mcp/pull/84))
- **Accessibility Remediation** — New `fix_accessibility_issues` tool for
  automated WCAG fixes; scanner expanded from 4 to 20 checks
- **Security Hardening** — Path traversal and symlink protections across all
  file I/O operations
- **Windows Support** — Fixed `execute_typescript` compatibility on Windows
  ([#85](https://github.com/vishalsachdev/canvas-mcp/pull/85))
- **CI Improvements** — Consolidated workflows (11 → 8 checks), fork-aware
  pipelines

## [1.1.0]

- Hosted Server (`mcp.illinihunt.org`)
- Learning Designer tools + 3 skills
- Agent Skills on skills.sh
- File Management ([@Metzpapa](https://github.com/Metzpapa),
  [#75](https://github.com/vishalsachdev/canvas-mcp/pull/75))
- Token Optimization
- Generic Distribution

## [1.0.8]

- Security Hardening (PII sanitization, audit logging, sandbox-by-default)
- Ruff linting
- 235+ tests

## [1.0.7]

- Assignment Update Tool (`update_assignment`), complete CRUD, 9 tests

## [1.0.6]

- Module Management (7 tools), Page Settings (2 tools), 235+ tests

## [1.0.5]

- Claude Code Skills, GitHub Pages site

## [1.0.4]

- Code Execution API (99.7% token savings), Bulk Operations, MCP 2.14 compliance

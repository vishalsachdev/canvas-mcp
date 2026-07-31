# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **`check_enrollment` reported "no enrollment" for people plainly on the roster.** Two independent defects, both rooted in an unverified premise about identifiers. (1) The matcher required exact equality against `login_id`/`sis_user_id`. Canvas does not define what `login_id` holds — measured live, UIUC stores the bare NetID (`vishal`), while instances that provision Canvas logins from email store the full address (`uniqname@umich.edu`), which the bare identifier could never match. Matching is now two-pass: exact equality across the whole roster first, then email-local-part equivalence, so `zqian` finds `zqian@umich.edu` and vice versa. Because this tool is documented as an external access gate, the fallback is deliberately conservative — it applies only when at least one side is unqualified (so `jdoe@school.edu` never matches `jdoe@other.edu`) and only when it identifies exactly one person; a bare `jdoe` against a roster holding both `jdoe@a.edu` and `jdoe@b.edu` raises the new `AmbiguousIdentifier` and the tool answers **AMBIGUOUS** rather than letting roster ordering decide an authorization question. (2) An email-form identifier was rejected by the input guard *before any Canvas call was made*, because the pattern excluded `@`; `@` and `+` are now accepted ([#199](https://github.com/vishalsachdev/canvas-mcp/issues/199)).
- **A role-scoped `check_enrollment` "NO" now says what the person actually is.** `role` defaults to `student`, and the role filter was pushed to Canvas as `type[]`, which hid every other enrollment the subject held. Asking about a teacher therefore returned `NO — … has no active 'student' enrollment`: true, but indistinguishable from "not in this course". The whole roster is now fetched (the same single request) and the role evaluated locally, so a negative names the roles the subject does hold — `They ARE enrolled in this course, as: TeacherEnrollment` — while a genuine stranger still gets a clean NO with no role clause. `EnrollmentResult` gained `roles_held` ([#199](https://github.com/vishalsachdev/canvas-mcp/issues/199)).
- **`upload_course_file` no longer dumps files into a stray "unfiled" folder.** With no `folder_path`, the tool omitted `parent_folder_path` entirely — which is not "use the root", it makes Canvas create and use a folder literally named `unfiled`. The docstring had always documented the root as the default, so this was a doc-vs-behavior divergence. Verified live with a three-way A/B against a real course: no parameter → `course files/unfiled`; `parent_folder_path=""` → `course files`; `parent_folder_id=<root>` → `course files`. The empty string is now always sent, which targets the root without the extra `/folders/root` lookup the id form would need ([#198](https://github.com/vishalsachdev/canvas-mcp/issues/198)).

### Changed
- **`check_enrollment` documentation is institution-neutral.** "NetID" is a UIUC term; the parameter accepts a NetID, uniqname, campus ID, or email-style Canvas login, and the docs now say so — along with the fact that it is not a display name, and that `role` defaults to `student` ([#199](https://github.com/vishalsachdev/canvas-mcp/issues/199)).

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

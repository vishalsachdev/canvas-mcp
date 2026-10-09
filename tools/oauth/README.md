# Canvas OAuth scope inventory and institutional pilot

Related: [issue #236](https://github.com/vishalsachdev/canvas-mcp/issues/236).
Source snapshot: `3170ca69ee51c603f1f35f1671efcfebdbbca296` (main).
Documentation checked October 8, 2026 (America/Chicago).

This is a documentation inventory, **not implemented OAuth support or evidence of
live scope enforcement**. Personal `CANVAS_API_TOKEN` authentication remains
supported. Do not implement authorization, refresh, callback or credential-store
infrastructure until a scoped institutional Developer Key pilot establishes the
required behavior. No credentials should be posted to GitHub or sent to maintainers.

## What is included

[endpoint-inventory.csv](endpoint-inventory.csv) maps Python tool, resource and
shared-helper HTTP call sites to Canvas's published Developer Key scopes, including
preflight reads, course policy, identity, course resolution and post-write reads.
Dynamic course/group discussion prefixes and migration/planner/accessibility paths
are expanded into their supported routes. Function names identify callers; private
helper names are not additional MCP tools. Line numbers are snapshot references.

[documented-read-scopes.txt](documented-read-scopes.txt) and
[documented-write-scopes.txt](documented-write-scopes.txt) contain deduplicated,
one-per-line published scopes for reference/pasting. They are **supersets, not a
recommended key configuration**: select the smallest pilot capability below and
its dependencies. All listed scopes remain unverified against a real scoped key.
The inventory contains 104 distinct published scopes: 65 GET and 39 write scopes.
Canvas also documents an authorization-request size limit; scope count alone does
not guarantee a full superset fits. Prefer small capability subsets.

Canvas scope names use `url:VERB|/api/v1/...` with the **published parameter names**,
which can differ from the variable names in our code. For example `/users/self`
uses `url:GET|/api/v1/users/:id`, and a self-submission read uses the documented
`:user_id` scope. Never paste runtime IDs, `self`, or Python brace expressions in
place of the documented route parameters.

Scope availability and user/role authorization are different boundaries. A scope
does not grant enrollment, staff rights, group membership, or access to another
student's grades. `CANVAS_ROLE` controls tool registration, not Canvas permissions.
`ALLOWED_WRITE_TOOLS`, `STUDENT_WRITE_TOOLS`, course policy and confirmation rules
still apply independently. A GET scope can expose sensitive data and is not
permission to read every course or student.

## Required, optional and unverified

| Classification | Meaning |
|---|---|
| Required baseline | Startup token validation needs `GET /users/:id`; course lookup/name resolution and display can need `GET /courses` and `GET /courses/:id`, even when a tool's primary endpoint is elsewhere. Include them in the initial pilot. |
| Required for capability | Every endpoint on the selected execution path, including permission checks, previews, identity/membership checks and verification reads. Use CSV callers plus the shared dependencies below. |
| Optional | A capability or branch deliberately excluded from the pilot: writes, groups, inbox, uploads, peer reviews, migrations, rubric import, grading standards, or GraphQL fallback. A scope is not optional when that selected path calls it. |
| Unverified mapping | GraphQL and non-REST transfer steps below have no established scope mapping here. Keep them outside the first pilot; do not invent scope strings. |
| Documented; pilot pending | Exact scope appears in Canvas resource documentation, but runtime enforcement, institution availability, includes and response shape are not yet tested. |

There is no universal minimum set for all tools. Permissions and helper dependencies
can cause an apparently simple tool to call several endpoints. Start with a small
read-only profile and collect the actual sanitized request trace. Cache hits are
not proof that lookup scopes are unnecessary: repeat tests with a fresh process.

## Capability selection

All profiles add the baseline above. The CSV supplies exact paste-ready scope
names; the routes below describe how to select them, rather than a second source
of truth for scope spelling.

| Capability | Audience / effect | Additional endpoint families and dependencies |
|---|---|---|
| Course content | Student + educator, read | Course details/syllabus, assignments, pages/front page, modules/items; select only the content tools being tested. MCP course/assignment resources use the same scopes. |
| Student planning | Student, read | `/planner/items`, `/users/self/todo`, course assignments; peer-review todo adds self identity and assignment peer reviews. |
| Own grades / what-if | Student, read | Course details and assignment groups (with assignments/submissions included); optional course grading standard. No grade write scope. |
| Groups / discussions | Student + educator, read | Self groups, group detail/users/files, course groups and permissions for shared discussion checks; course/group topic, entries, replies, view and entry_list routes as used by the selected read. Group membership remains enforced. |
| Announcements / activity | Student, read | Courses plus `/announcements`, self activity stream and summary. Course announcement tools instead read course discussion topics. |
| Quiz awareness | Student, read | Classic quizzes and details, assignments for New Quizzes metadata; permissions and self identity before classic quiz submission lookup. No quiz-taking scopes and no `/api/quiz/v1` calls in this snapshot. |
| Educator analytics / peer reviews | Educator, read | Course users/enrollments, assignment/submission/peer-review reads, analytics student_summaries. Roster rights remain required; these are not student baseline scopes. |
| File reads | Shared, read | Course/group files and file metadata; download URL transfer is a separate step below. |
| Educator content writes | Educator, write | Selected assignment/page/module/item/topic/syllabus write plus its preflight and verification reads. Announcement creation also needs topic DELETE for cleanup if Canvas creates an unintended discussion. |
| Educator grading / rubrics | Educator, write | Assignment/rubric reads; submission PUT for grades/comments; rubric POST/PUT and rubric-association POST. CSV rubric import additionally uses upload POST and import-status GET. |
| Student submission | Student, opt-in write | Assignment read, own submission read, course policy read; submission POST. File submissions additionally need submission-file upload initiation and transfer. Commenting uses own submission PUT; no educator grade action is implied. |
| Student module completion | Student, opt-in write | Module-item GET and PUT done, course policy GET, course resolution. |
| Planner / personal calendar | Student, opt-in write | Selected planner-note/calendar-event POST/PUT/DELETE plus ownership reads; planner overrides GET/POST/PUT and reads of the linked course object. Course planner completion also needs module-completion permission at the tool-policy layer. |
| Inbox | Shared reads; student/educator writes | Conversations list/detail/unread_count, recipients search; POST conversation or add_message and course checks. Marking read uses PUT conversations. Student send/reply also requires identity, recipient/enrollment and course-policy checks. |
| Course copy | Educator, opt-in write | Source/target courses; target assignments/pages/modules/discussions/files for occupancy; migration POST and migration/progress/issues GET. |

Shared dependencies to inspect: `core/cache.py` (course resolution/display),
`core/course_policy.py` (course syllabus policy), `core/enrollment.py` (enrollments),
`core/peer_reviews.py`, `core/peer_review_comments.py`, and helpers in the selected
tool module. Grading calculations, content parsing and discovery do not themselves
require new API scopes; their input-fetching tools do.

## Bundled TypeScript call coverage

These wrappers add no distinct scope to the CSV. They are optional and excluded
from the initial pilot with code execution disabled.

| Source under `src/canvas_mcp/code_api/canvas/` | Methods / routes already inventoried |
|---|---|
| `courses/listCourses.ts`, `courses/getCourseDetails.ts` | GET courses and course detail |
| `assignments/listSubmissions.ts` | GET assignment submissions |
| `grading/gradeWithRubric.ts`, `grading/bulkGrade.ts` | GET assignment; PUT user submission (bulk delegates to gradeWithRubric) |
| `discussions/listDiscussions.ts`, `discussions/postEntry.ts` | GET topics; POST topic entries |
| `discussions/bulkGradeDiscussion.ts` | GET topic entries/replies; PUT user submission |
| `communications/sendMessage.ts` | POST conversations |

## Boundaries requiring separate verification

- **GraphQL:** the opt-in anonymous-discussion fallback sends a read-only query via
  `POST /api/graphql`. HTTP POST here is not a Canvas write. No scope mapping is
  asserted; it is excluded from both paste lists. Keep
  `DISCUSSION_GRAPHQL_ENABLED=false` initially. Measure scoped-key behavior
  separately rather than widening the key to unscoped access.
- **File transfers:** course uploads and student submission uploads first call
  documented REST initiation endpoints. The returned storage URL, multipart POST,
  possible redirect/finalization, and download URL GET are not ordinary fixed REST
  tool routes. Test the entire transfer lifecycle with disposable files before
  declaring the initiation scope sufficient. Never log signed URLs, tokens or
  upload parameters. See `core/client.py` upload/download helpers and `tools/files.py`.
- **Code execution:** bundled TypeScript operations use the same course,
  assignment/submission, discussion/entry/reply and conversation endpoints already
  listed. `execute_typescript` can also issue arbitrary requests; a static inventory
  cannot bound those scopes. Keep `EXECUTE_TYPESCRIPT_ENABLED=false` for the pilot.
- **Pagination:** follow-up requests keep the endpoint scope; test multiple pages
  and fresh-process course resolution. Do not add fabricated per-page scopes.
- **Includes:** Canvas's Developer Key setting “Allow Include Parameters” is
  separate from endpoint scopes. With it disabled, Canvas documents that includes
  are ignored. Tools relying on submissions, assignment groups, permissions or
  module items may return incomplete results despite successful HTTP responses.
  Compare actual fields/counts with it enabled and disabled; a 200 alone is not a pass.

## Small institutional validation matrix

Use disposable sandbox courses, one educator, one student, and one unenrolled
account if available. The institutional tester manages registration and OAuth
credentials locally through their existing gateway or test harness. Canvas OAuth
and MCP gateway/client OAuth are different layers: success refreshing another MCP
server with `mcp-remote` does not establish Canvas refresh behavior.

Set a student/educator role as appropriate, disable code execution and GraphQL,
leave student writes disabled, and set `ALLOWED_WRITE_TOOLS=none` for initial reads.
Do not grant all 104 scopes just to make a failed test pass. Run an allowed request
and an omitted-scope request with the same user and valid token to isolate scopes
from role permissions. Repeat after clearing caches/restarting.

| Test | Setup / action | Expected evidence | Result |
|---|---|---|---|
| P1 Scope syntax | Paste baseline plus one content capability into an Enforce Scopes Developer Key. Compare with the institution's scope picker/catalog. | Every chosen string accepted; record Canvas version and any absent scope. | Not run |
| P2 Allowed read + dependencies | Fresh process: validate identity, list courses, read one assignment; repeat by course code and numeric ID; test pagination. | Correct identity, complete expected fields/results; sanitized method/path trace matches selected scopes. | Not run |
| P3 Omitted scope | With a newly issued valid scoped token, omit the selected assignment GET scope but retain baseline; call that exact endpoint. | Canvas documents missing scope as 401; capture observed status/error and ensure no automatic privilege widening. Distinguish expiration and role errors using P2 control. | Not run |
| P4 Includes | Repeat assignment/grade/module reads with Allow Include Parameters off and on, using newly issued credentials where needed. | Record field/count differences, especially own submissions and nested assignments; identify incomplete outputs. | Not run |
| P5 User boundary | Student reads own submission, then attempt a different student's submission and an unenrolled course; test nonmember group access separately. | No unauthorized data. Record Canvas response and tool refusal separately; scopes do not override role/membership. | Not run |
| P6 Optional write | After read tests, allow only one student write in a disposable course (or a disposable planner note); include its preflight/read-back scopes. Run preview where supported, confirm explicitly, then repeat with write scope omitted. | Preview has no write where supported; authorized confirmed write succeeds and is verified; omitted write scope prevents mutation. Creation/completion tools that write immediately require explicit tester approval. | Not run |
| P7 Refresh / revocation | In tester-managed OAuth harness, exercise token expiry and refresh, key disable, scope removal, and fresh authorization after scope changes. | Sanitized timing/status report; scope set never grows during refresh. Scope removal invalidates derived tokens per Canvas docs; added scopes need a newly issued token. Observe behavior rather than assume refresh rotation. | Not run |
| P8 API-token regression | Separate clean configuration with existing personal-token path; run the same safe reads. | Existing token mode works independently without Developer Key/gateway configuration. | Not run |

Optional follow-on tests: full file upload/download, rubric CSV import, course-copy
occupancy and terminal issue reporting, group discussion routes, GraphQL, and
operator/tool-policy denial despite an allowed endpoint scope. These are outside
the initial read-only pilot; each needs its own explicit scope subset and report.

Report only: repository SHA, Canvas version, selected scope strings, include setting,
role/tool-policy configuration, sanitized method + route template, HTTP status,
expected/observed field presence and mutation outcome, transport/gateway version,
and pass/fail/blocked. Use synthetic IDs/content. **Never attach tokens, client
secrets, authorization headers, signed transfer URLs, student records or messages.**

## Maintaining the inventory

For each endpoint/tool change, update the CSV call sites, canonical scope,
capability/requirement classification and documentation URL, then regenerate the
deduplicated GET/write text lists from the nonempty CSV scope column. Review the
shared helper dependencies, feature-gated tools, resources, TypeScript wrappers,
and dynamic branches, not only the changed primary request. Update the snapshot
SHA/date and counts. Preserve unverified rows until a published mapping or pilot
result supports them; do not silently include guessed scopes in paste lists.

A reproducible audit starts with:

```sh
rg -n 'make_canvas_request|fetch_all_paginated_results|canvasGet|canvasPost|canvasPut|fetchAllPaginated' src/canvas_mcp
rg -n 'api_root|upload_url|download_url|canvas_authenticated_client' src/canvas_mcp
```

Inspect multiline calls and endpoint-variable definitions. The CSV records
expanded endpoints; it is not a generated proof of every possible execution path.
Scope spelling is verified against the `Scope:` labels in the linked Canvas
resource pages, not inferred from our parameter names. Deduplication and coverage
can be checked using Python's standard `csv` library; no application dependency
or authentication change is required.

## Authoritative references

- [Canvas Developer Keys](https://developerdocs.instructure.com/services/canvas/oauth2/file.developer_keys): scope format/enforcement, paste UI, includes, and scope-change behavior.
- [Canvas API Token Scopes](https://developerdocs.instructure.com/services/canvas/resources/api_token_scopes): account scope catalog (beta). This admin discovery endpoint is not called by canvas-mcp and is not part of runtime baseline scopes.
- Per-endpoint Canvas resource documentation is linked in the CSV.
- [Issue #236 maintainer pilot decision and contributor offer](https://github.com/vishalsachdev/canvas-mcp/issues/236).

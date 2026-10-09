# Student-feature security review — 2026-10-08

Reviewed main `eeeb4799eaaa6b9806434c01943c17b99a6efeeb` following integrations #471–#476 and release #478. This is a focused code/regression review, not a FERPA compliance certification or live production assessment.

## Findings and fixes

| Finding | Impact | Proposed repair |
| --- | --- | --- |
| Process-global course alias/label caches and shared in-flight refresh task reused across HTTP credentials | Course metadata disclosure; wrong-course operation if the second caller can access both courses | #480: caller-authorized HTTP resolution and request-local labels; no HTTP publication into stdio caches |
| Legacy exact-code shortcut bypasses alias ambiguity checks | Wrong-target operations in shared tools, including stdio; preexisting core defect | Separate ambiguity PR stacked on #480: refuse ambiguous aliases before numeric selection or SIS fallback |
| Raw Canvas/proxy error bodies returned unfenced | Conditional prompt-injection channel; no student-controlled reflection exploit established | #481: status-only HTTP errors, bounded provenance-fenced other errors, including quiz permissions/identity failures |
| README claimed all planner writes preview first | Agents could mutate on what they believed was a preview | #479: distinguish immediate writes and warn about module progression |

## Boundaries checked

- Grades use caller-owned submission data; quantitative-data restrictions fail closed and observer/list-shaped submissions are rejected. Grade scenarios are calculations, not grade writes.
- Groups re-read `/users/self/groups` and require membership before group-scoped reads. Group roster outputs allowlist name/ID and omit direct identifiers such as email/login/SIS ID. Shared discussion group access also has membership/explicit staff-permission guards.
- Cross-course announcements request active caller courses and backstop returned contexts. Activity reads use `/users/self/activity_stream`; no read-marking call is made.
- Quiz tools never start attempts and avoid plural attempt routes that can queue grading. Staff/unknown permissions refuse attempt reads; returned attempts are checked against the caller ID.
- Messaging rejects expandable aliases, duplicate/non-numeric recipients and more than five recipients. Send lookup is course-scoped. Confirming calls re-derive recipients/audience and policy; replies require caller participation and explicitly address the bound audience. Bodies are limited and fence markers are refused. Tokens are caller/content-bound, single-use and tool-specific; uncertain deliveries spend tokens and advise checking Canvas before retrying.
- Calendar edits/deletes check ownership and personal context; course/group/appointment events cannot masquerade as personal deletes. Planner completion requires the module-write gate for course progression effects.
- `STUDENT_WRITE_TOOLS` defaults empty. `ALLOWED_WRITE_TOOLS` narrows registration and removed tools cannot be called. HTTP credentials fail closed without a caller token; no server-token fallback is allowed.

## Deployment and approval evidence

The review submissions returned for all six integrations #471–#476 are COMMENTED; none is APPROVED. Their final-head pull-request workflow runs returned successful Enhancement Testing, Security Testing, Closing Keyword Guard and Claude review results. A successful workflow is not a human approval.

Production workflow source deploys on `v*` tags or manual dispatch from main, not ordinary main merges. It does not itself verify human approval or read live Azure gate settings. A tag is therefore a deployment action requiring separate authorization.

Locally reproduced the reported configuration (`CANVAS_ROLE=educator`, `ALLOWED_WRITE_TOOLS=none`, code execution disabled, student-write list empty): 51 read tools registered, all side effects removed, sampled new student tools absent. This proves code behavior under those inputs only. **Live Azure app settings, running image digest/commit, authentication configuration and exposed tool list remain unverified: no authenticated Azure access was available.** The release author's production claim is not independent evidence.

## Verification and review limits

Initial focused student/security run: 1,588 passed, 19 skipped. Documentation branch full suite: 3,187 passed, 20 skipped. Each reproducible code defect received failing regressions before repair; exact final suite counts are recorded in the individual PRs. Ruff is clean on the published changes. Initial full runs failed three HTTP transport tests because the runner lacked optional `socksio`; installing it locally resolved the environment failure, with no repository dependency edit.

A separate AI reviewer inspected the source and proposed fixes, and repository Codex/Claude reviews were requested or triggered. Cloud review identified the repeated-label-request performance regression in #480; a request-local label cache and 100-item regression address it. **AI review is not human APPROVED review.** A human maintainer must review final heads before release or student-write enablement.

Remaining limitations: tokens do not prove a person approved; client approval is necessary. Fencing marks provenance but cannot eliminate prompt injection. Stable pseudonyms can be correlated when the same person is named as staff elsewhere. Canvas ultimately enforces account/section permissions; local controlled tests do not establish every institution's live permissions. No live Canvas writes, merge, release tag, deployment, or student-write enablement was performed for this investigation.

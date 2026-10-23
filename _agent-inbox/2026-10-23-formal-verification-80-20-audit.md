# Formal verification: value assessment and bounded 80/20 audit

**Repo:** canvas-mcp
**File:** verify/, src/canvas_mcp/code_api/, src/canvas_mcp/core/, relevant local entrypoints/configuration
**Priority:** normal
**Requested by:** Vishal, 2026-10-23
**Authored and committed by:** [Codex]
**Snapshot audited:** `a4fa557ee980094e8331431920bb00db3f5e792b` on main, 2026-10-23 UTC

## Scope and authorization

Vishal asked whether the formal-verification exercise was useful or overkill, and what worthwhile next work fits an 80/20 approach. He also asked to leave unresolved evidence for his local agent to audit. **This note authorizes an audit/report, not implementation, new PRs, publishing, deployment, live Canvas writes, or external contact.** Existing repair/release work remains with its current maintainer. Refresh repository state before acting.

## Verdict

**Useful hardening; not proof of the entire application.** The strongest evidence is concrete defects reproduced against the old executable implementation, followed by repairs and regression tests. This is more than model-only discovery. It does not establish that Lean/TLA+ was uniquely necessary to find those defects, or that its incremental cost beat a focused review plus tests: engineering time/cost and a counterfactual are not available.

The high-return scope is the small shared machinery: write retries, admission/ownership, pagination, and scheduling. Proving every wrapper would be poor next-step value. Preserve the existing small proof suite; spend new effort on real entrypoints, high-impact write outcomes, caller boundaries, and model/code correspondence.

### Verified evidence, not just README claims

I inspected all six verification reports, the committed before/after receipts, representative real regression tests, Lean/TLA+ artifacts, the runner, current production source, and current CI metadata. Historical receipts were inspected, not independently rerun in this audit.

| Area | Receipt inspected | What it establishes |
|---|---|---|
| Shared confirmation | [before](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/python-before.txt), [after](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/python-after.txt) | Three baseline failures: lost mismatch burn, inconsistent clock samples, rollback resurrection; repaired eight new guard tests plus eighteen existing tests pass. The clock-sample defect is guard-level duplicate reservation, not a demonstrated double deletion. |
| Python client | [before](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/client-before.txt), [report](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/CLIENT.md) | Six failed baseline tests and two already-passing controls: truncated linked pages and cancellation/cleanup races; repaired report records twelve focused passes. |
| TypeScript grading | [before](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/typescript-before.txt), [after](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/typescript-after.txt), [real localhost test](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/tests/code_api/grading-commit-response.test.ts) | Actual client sends twice after simulated committed grade/comment plus 503, disconnect, malformed JSON, or 307. Also duplicate targets and callback target mutation. Twenty-eight failing baseline cases, three controls; forty-one complete repaired-suite passes. |
| TypeScript pagination | [before](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/ts-pagination-before.txt), [after](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/ts-pagination-after.txt) | Twenty-seven baseline failures, including truncated results, changed credential/config snapshot, unbounded traversal and redirect validation; sixty-eight complete repaired-suite passes. |
| Student submission | [before](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/student-before.txt), [after](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/student-after.txt) | Four baseline failures, including two concurrent POSTs after a still-running fingerprint claim expired; one hundred focused repaired-suite passes. |
| Reminder reporting | [before](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/workflow-before.txt), [count failures](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/workflow-counts-before.txt), [after](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/evidence/workflow-after.txt) | Three baseline failures: possible delivery falsely reported unsent, and incorrect campaign totals/success; two hundred nine focused repaired-suite passes. |

These are **test-case counts, not distinct bug counts**; parameterized cases overlap. Controlled servers/transports demonstrate implementation behavior, not observed incidents against production Canvas.

The [runner](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/run.py) checks named original counterexamples and repaired models; parser failures do not count as counterexamples. [Lean configuration](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/verify/lean/lakefile.toml) builds seven library roots with warnings as errors. This is a real, bounded verification pipeline, not missing CI.

At the audited SHA, [test run 39979309421](https://github.com/vishalsachdev/canvas-mcp/actions/runs/39979309421) passed TypeScript, Python 3.11–3.14, Windows, lint, and formal verification. The [formal job](https://github.com/vishalsachdev/canvas-mcp/actions/runs/39979309421/job/120502077766) took approximately 43 seconds including setup; this is one observed run, not an engineering-cost estimate. The aggregate gate explicitly requires it. Separately, the [dependency scan](https://github.com/vishalsachdev/canvas-mcp/actions/runs/39979309425/job/120502078106) failed; existing security/release follow-ups already own that work. Do not describe all security checks as green.

## Important routing distinction

“Uses a TypeScript file” does **not** imply either “all safeguards apply” or “all safeguards are bypassed.”

- [`code_api/client.ts`](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/src/canvas_mcp/code_api/client.ts) itself calls Canvas REST. Its `canvasPost/Put/Delete/PutForm` exports retain no-automatic-write-retry and write-redirect rejection. `fetchAllPaginated` adds bounded, validated Link traversal and a config snapshot.
- `bulkGrade` adds validated controls, duplicate-target rejection and captured targets; the shared batch runner also serves discussion grading. Direct low-level calls do not inherit bulk-grading semantics merely by importing the client.
- [`execute_typescript`](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/src/canvas_mcp/tools/code_execution.py#L351-L388) can import those helpers, but explicitly performs immediate writes with **no Python confirmation-token step**, anonymization or untrusted-content fencing. Arbitrary script `fetch`/other HTTP clients can also avoid the shared TypeScript transport. This is a capability boundary, not a newly demonstrated exploit.
- Python tool confirmations bind previewed arguments and caller identity; they **do not prove human approval**. Tool availability and client-side approval are separate boundaries. [`tool_policy.py`](https://github.com/vishalsachdev/canvas-mcp/blob/a4fa557ee980094e8331431920bb00db3f5e792b/src/canvas_mcp/core/tool_policy.py) defaults hosted HTTP to read-only and distinguishes code execution; stdio defaults are less restrictive among enabled tools.
- The catalog and effect registry currently contain 126 tools: 72 read, 49 Canvas-write, four local-write, one code-execution. This inventory is not a count of formally verified workflows.

**Actual personal call routes, frequency, installed versions, and active settings are unverified.** Do not infer them from the repository or turn a hypothetical bypass into a usage claim.

## Ranked next work — audit first, reuse existing machinery

Effort below is a rough scope estimate for one maintainer, not measured cost or authorization to implement.

1. **Resolve actual route and version coverage.** High impact; roughly 30–60 minutes if representative scripts/config are available. Trace one ordinary grade/message, one bulk workflow, and one destructive workflow actually used. Determine whether each imports this client, uses guarded MCP tools, or uses its own transport, and which installed commit supplies it. **Stop** once those representative paths have an evidence-backed guard matrix; report unknowns rather than sweeping session history. This determines which existing repairs actually protect usage.

2. **Audit ambiguous outcomes on the highest-impact writes.** High impact; roughly half to one day for a focused gap review. Reuse localhost/HTTPX fault harnesses for committed-then-timeout/503/malformed reply, cancellation, partial batch success, and explicit rejection. Require no accidental second dispatch, honest “uncertain” reporting, and no released reservation without typed no-write evidence. Existing student send/reply and ordinary conversation already use owning claims; direct peer-review reminders still use token-only release and prose-based status classification. Treat migration as a simplification candidate, **not a newly proven bug**. Python 429 retries still assume no write applied. **Stop** when each selected path has an existing passing test or one precise missing-test/contract finding; no blanket rewrite or exactly-once service.

3. **Protect caller isolation using the existing real-client harness.** High hosted impact; roughly half a day for focused review. Reuse `test_course_cache_isolation.py`, `test_course_policy_caller_boundary.py`, and `test_discussion_hint_isolation.py`; these already cover different callers, credential rotation, cached grants, and overlapping requests. Audit changed/new shared caches and credential paths against them, not a duplicate new proof system. **Stop** after targeted checks establish that caller B cannot consume A's metadata/policy/token, missing HTTP credentials fail closed, and no new cache escapes the request boundary. Local single-user and hosted multi-user risk differ.

4. **Keep a tiny source → property → test map current.** Medium/high leverage; a few hours. Formal reports honestly describe manual models, not compiler-checked Python/TypeScript refinement. Current guarded rubric updates, syllabus replacement, content migration and newer student messaging extend beyond the named original attachment table; this does not mean they lack tests. Link their existing binding/replay/outcome tests and flag only uncovered cases. Require a short correspondence review when shared guard/client/batching code changes. **Stop** at a concise map plus targeted gaps; keep the existing green Lean/TLC gate, do not prove all 126 tools.

The proof assumptions remain: one process/event-loop thread, honest no-write evidence, no cryptographic collisions/forgeries, accurate server pagination/metadata, and eventually settling external operations. No proof covers real human consent, server-side exactly-once effects, arbitrary callback writes, complete rubric/grade semantics, or every deployment.

## Local agent: exact unresolved evidence to return

Return a small sanitized table:

`workflow | entrypoint | installed version/commit | import/call chain | transport | mutation | confirmation/human approval | retry/pagination | receipt/readback | evidence/gap`

Use only relevant known project scripts and configuration:
- Resolve actual imports to their installed source, not just matching function names or a current source checkout. Record whether execution is MCP `execute_typescript`, a standalone local script, or a guarded MCP tool.
- Report policy flags/transport and approval behavior without token values, raw environment dumps, private endpoints, user identifiers, or student data.
- Identify any custom retry loop, raw fetch, caller-mutable target, or swallowed partial failure along those paths; reading code is sufficient for this audit. Use synthetic controlled I/O only for separately authorized tests.
- Confirm the deployed/installed revision containing the relevant fixes. Do not assume green main equals the runtime version; existing release notes already flag a possible deployment lag.
- Verify whether the aggregate test gate is actually required by branch protection/rulesets. This audit's read of `GET /repos/vishalsachdev/canvas-mcp/branches/main/protection` returned **403 Resource not accessible by integration**. Workflow configuration and successful checks were verified; enforcement settings were not. No permission workaround was attempted.
- If representative local inputs are unavailable, list the exact missing script/config and mark the row unknown. No broad history sweep and no secrets or private session transcripts in this public inbox.

## Recent non-Lean testing is already the right direction

Current main includes ordinary executable adversarial regressions in `tests/security/test_text_processing_cost.py` and `test_accessibility_processing.py` (malformed HTML and repeated text in subprocesses with eight-second timeouts), `test_impact_stats_boundary.py` (executable-looking remote counters must not create a marker or replace the previous good snapshot, with a valid control), and `test_announcement_delete_boundary.py` (real FastMCP calls with controlled I/O reject non-announcements and target-type changes after preview). These are concrete boundary/fault tests, not another formal-proof campaign or necessarily a new fuzzing framework. Extend this pattern only where the ranked audit finds a gap.

## Research context

[AWS's 2015 experience](https://cdn.amazon.science/67/f9/92733d574c11ba1a11bd08bfb8ae/how-amazon-web-services-uses-formal-methods.pdf) supports targeted design verification while acknowledging the implementation gap. [S3's lightweight formal methods work](https://www.amazon.science/publications/using-lightweight-formal-methods-to-validate-a-key-value-storage-node-in-amazon-s3) emphasizes executable models, property-based operation sequences and concurrency checking. These support the direction, not a numeric ROI claim for this project. If a real sequence-coverage gap remains, [model-based testing](https://fast-check.dev/docs/advanced/model-based-testing/) is a smaller next experiment than whole-program proof.

Deliver the audit to Vishal; propose any necessary repair separately. Do not duplicate the existing maintainer's security/release tasks or interpret this note as permission to merge, publish or deploy.


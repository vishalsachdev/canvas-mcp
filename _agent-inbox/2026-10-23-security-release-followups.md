# Clear security-scan blockers and prepare the next canvas-mcp release

**Repo:** canvas-mcp
**File:** pyproject.toml, uv.lock, .github/workflows/, _agent-inbox/2026-10-20-rat-stack-code-mode-boundary.md
**Priority:** high
**Requested by:** Vishal, 2026-10-23
**Authored and committed by:** [Codex]

## What to change

Pick up the following verified follow-ups from the October 23 weekly status review. Refresh GitHub state before making changes; the observations below were made against main `ebab8d6969ccc63eef8164800725946bafc50f92`.

1. **Restore the dependency vulnerability scan.** Main locks `black==26.5.1` and `opentelemetry-api==1.43.0`. Update to patched releases, minimally Black 26.10.1 and OpenTelemetry API 1.45.1, with any resolver-required compatible dependency changes. Consider an appropriate minimum-version constraint so a fresh installation cannot resolve the affected telemetry dependency. Preserve the MCP security floor `mcp>=2.2,<3`; do not suppress the new advisories merely to get green CI.
   - Black: [GHSA-cg8m-r9f2-5wm2 / CVE-2026-114134](https://github.com/advisories/GHSA-cg8m-r9f2-5wm2), affected <26.10.1. This specifically concerns the bundled GitHub Action with `use_pyproject: true`. No `psf/black` action or `use_pyproject` setting was found in this repository's workflows, so distinguish scanner findings from demonstrated exposure.
   - OpenTelemetry: [GHSA-xcq7-p3pf-p88h / CVE-2026-114603](https://github.com/advisories/GHSA-xcq7-p3pf-p88h), affected <=1.45.0, patched 1.45.1. Untrusted tracestate parsing can consume excessive CPU on an event loop. The dependency is brought in by MCP/FastMCP; review the actual ingress path and upstream header limits.
   - [Failing main security run](https://github.com/vishalsachdev/canvas-mcp/actions/runs/39889927697), dependency job 120206979173. The run reports two vulnerabilities. Application tests, security tests, secret scanning, static analysis and CodeQL pass.
   - Keep the update narrow; inspect the resolved diff, rerun the workflow-equivalent dependency scan, frozen test suite, Ruff and mypy. Do not equate an old green dependency scan with current advisory clearance.

2. **Prepare [PR #516](https://github.com/vishalsachdev/canvas-mcp/pull/516) for integration.** At inspected head `8d6e6f7c5335165685a83e5c41b59f6894d29382`: 18 successful checks, one expected skip, two neutral checks; no unresolved inline threads. It is behind main. Update safely and rerun checks after the dependency repair. It restricts interactive Claude triggers and moves overhaul planning/status documents out of the website tree. The only formal review is COMMENTED from the PR author's account; this does not satisfy independent approval. Vishal previously said he would arrange approval on GitHub.

3. **Fix [PR #518](https://github.com/vishalsachdev/canvas-mcp/pull/518)'s provenance finding.** At head `00e1a702d66ee4573ee9bfe611e045e29d916180`, one unresolved P2 thread asks that the update line explicitly identify Codex as the author of the added Pi codemode research. Preserve Xplorer's original attribution and add Codex's contribution clearly. This is a documentation-only change; no implementation test is needed. It is behind main, has no formal approval, and its passing security scan predates the new advisories.

4. **Re-review [PR #510](https://github.com/vishalsachdev/canvas-mcp/pull/510) after normal fork CI can run.** Latest inspected head `2dc594b1222f13c627f19c18b5037549a7ddc57a` has four workflows in `action_required` and no check runs. A maintainer must approve workflow execution through the normal secretless fork path. This is distinct from approving the code.
   - The contributor has responded and pushed fixes; do not repeat older triage claims that they have not responded.
   - Their response claims sanitized credential validation errors, native keyring storage with explicit file fallback/Windows ACLs, recovery after transient refresh failure, typing fixes, preservation of #511, and state validation on error callbacks. Independently verify these against the current SHA.
   - CHANGES_REQUESTED remains. Outstanding review includes supported authorization to reuse the mobile-client registration, PKCE/redirect design, cross-platform long-lived-secret storage/fallback, multi-process refresh behavior, child-process filesystem trust, and sanitized institutional SSO/MFA/scope/revocation evidence.
   - Preserve PAT precedence and per-caller hosted credential isolation. Keep [#236](https://github.com/vishalsachdev/canvas-mcp/issues/236)'s scoped Developer Key pilot separate.
   - Do not execute the fork in a privileged same-repository workflow, use pull_request_target to run untrusted code, expose secrets, or weaken the fork gate.

5. **Prepare a current release after verification and approval.** [Production deployment 39535535840](https://github.com/vishalsachdev/canvas-mcp/actions/runs/39535535840) succeeded October 20 Central / October 21 UTC, but deployed `v1.14.0` at `4696c166722becf7608f1f197a0c72c83048d224` (October 7 Central / October 8 UTC). That deployed source predates the subsequent submission guards, caller-isolation repairs, dependency patches and overhaul. The inspected main is 103 commits ahead. Recheck the actual production SHA before rollout.
   - [#515](https://github.com/vishalsachdev/canvas-mcp/pull/515) merged October 21 and changes 37 files across 14 commits. All six inline threads are resolved. Targeted live Canvas validation is still needed for accessibility sanitizer/readback behavior and announcement-deletion safeguards, using an authorized sandbox with synthetic data.
   - Restricted-grader and scoped-key validation from the prior report remain outstanding. Publisher binary/Registry validation is documented in #516; actual Actions OIDC, protected release settings and production publishing still require their own evidence.

## Why

The code and security checks improved substantially this week, but current main's dependency scan is red and the latest verified production deployment uses older source. The small workflow-security follow-up should be integrated before another release once the required approval and current checks are satisfied.

## Notes

- This handoff was explicitly requested by Vishal: "Put these notes for the canvas-mcp agent on the inbox."
- Codex made no implementation changes during the follow-up. A local `uv lock --upgrade-package black --upgrade-package opentelemetry-api` attempt was stopped by automatic approval review because it interpreted the earlier scheduled report's read-only scope as still active. This was an execution-authorization block, not a dependency resolution or test result. The local worktree remained clean. Do not report the fixes as completed.
- Make implementation changes on branches and use the repository's PR workflow. Preserve required independent approval; do not self-approve, bypass protections, merge, publish, deploy, or post contributor-facing replies without Vishal's explicit authorization for that action.
- [#441](https://github.com/vishalsachdev/canvas-mcp/pull/441) remains unchanged at `294cb11`: merge conflicts, no CI and 22 unresolved privacy/security/grading threads. A maintainer has already requested a fresh OAuth-only branch from main; do not repeat that request without checking for a response.
- New [#513](https://github.com/vishalsachdev/canvas-mcp/issues/513) requests opt-in submission bodies/comments; preserve untrusted-content fencing, permission checks, anonymization and bounded output in any proposal. [#391](https://github.com/vishalsachdev/canvas-mcp/issues/391) now reports that uv discovery was fixed, followed by a distinct Python 3.15 installation failure. [#505](https://github.com/vishalsachdev/canvas-mcp/issues/505) is a partial maintenance report, not verified dependency freshness or Canvas compatibility.

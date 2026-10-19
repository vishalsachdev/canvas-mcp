# Consider Harness²-style recursive improvement for Canvas agent skills

**To:** any
**From:** Grok (via user request on X post)
**Repo:** canvas-mcp
**Kind:** task
**Priority:** normal
**Requested by:** Vishal (via Grok) 2026-10-19
**Needs Vishal:** yes

## What

Evaluate integrating or adapting Google's Harness² (recursive agent harnessing: Propose–Probe–Compose on the current task + accumulating lessons/harnesses for future tasks) into our Canvas MCP agent skills.

Context: @openmys plugged Harness² into JEV 1.14, enabling the vision system to rewrite prompts, build tools, and distill experience without touching model weights, with gains on vision benchmarks. See https://x.com/openmys/status/2112024812751294954.

Our 8 agent skills (weekly plan, morning check, bulk grading, peer review, course QC, etc.) and tools form a harness around the model. Recursive refinement could help on novel course structures, student edge cases, or accessibility audits.

## Why

Fixed skills work well for common flows but may underperform on unseen tasks. Harness² is designed exactly for open-world adaptation without labels. Canvas workflows are varied (different courses, institutions, policies), so self-improving tool guidance and skill recipes could raise success rates and reduce manual skill updates.

## Notes

- Public repo: keep this item free of secrets/student data.
- Prefer issues for longer discussions; this is a directive for an agent to pick up.
- Related evaluation also filed in claude-config/_agent-inbox/.
- Repo: https://github.com/google-research/harness2

## Result

**Authored by:** [Claude control], 2026-10-19 16:25 CDT. Evaluation only. Nothing installed, run or spent.

### Verified facts

- `google-research/harness2` is real. Apache-2.0, created 2026-10-06, the README says "not an officially supported Google product".
- Paper is real: arXiv 2610.14224, "Harness^2: Recursive Agent Harnessing for an Open World" (Xu et al., Google), posted 2026-10-09.
- The gains are "up to" figures for one refinement step on GLM-5 / Gemini 3.5 Flash: +11.5 WorkBuddy-Bench, +4.5 JobBench, +11.8 pp LAB.
- Executors are OpenCode (default) or Codex. The README says executor network access is unrestricted and Codex runs with its sandbox disabled. Model-backed runs use Vertex AI.
- "No ground-truth verifier" means an LLM chooses among anonymized candidate outputs. Lessons are stored as cue / lesson / evidence per domain.
- Not verified: the X post and the "JEV 1.14" vision demo (the post could not be fetched; nothing found by search).

### Fit for this repo's skills

| Skill | Fit | Reason |
|---|---|---|
| canvas-course-qc | yes | Read-only, so probes are harmless. A seeded sandbox course gives a real verifier (known defects). |
| canvas-accessibility-auditor | yes | Read-only. Seeded WCAG defects give a real verifier. A good second target. |
| canvas-week-plan, canvas-morning-check | maybe | Read-only, but "good output" is a judgment. It needs a rubric before probing means anything. |
| canvas-course-builder | maybe | Writes content. Probe only in a throwaway sandbox course. |
| canvas-bulk-grading, canvas-peer-review-manager, canvas-discussion-facilitator | no | They touch learner work and grades. A self-editing harness breaks reproducibility, and probes would re-run on learner data. |

### Smallest prototype

Do Propose-Probe-Compose by hand on **canvas-course-qc**, with k=1. Do not use Harness² code.
1. Make a sandbox course with about 10 planted defects (empty module, unpublished item inside a published module, due date after lock date, graded assignment with no rubric, broken internal link) and no learners.
2. Baseline: run the skill unchanged and record which planted defects it reports.
3. Propose two edits to `skills/canvas-course-qc/SKILL.md`. Probe each edit on the same sandbox course and compose the better parts.
4. Measure: recall of planted defects goes up with no new false positives. Then check transfer on a second sandbox course with different defects.
5. Keep any adopted change as a normal PR with the cue / lesson / evidence written in the PR description.

Cost: about 4 to 6 agent runs of one read-only skill.

### Needs maintainer approval

- Creating and seeding the sandbox course (the only Canvas write).
- Whether a probe harness, if it works, ships in the repo (for example as a `tests/skill-evals/` fixture) or stays maintainer-local.

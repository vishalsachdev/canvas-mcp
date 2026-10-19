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

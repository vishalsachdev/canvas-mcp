# [Doodle bot] One-off local Graphify trial on canvas-mcp

**Repo:** canvas-mcp
**File:** none (local run only)
**Priority:** normal
**Requested by:** Vishal 2026-11-09
**Authored and committed by:** [Doodle bot]

## What to change

Nothing in the repo. Run a one-off local trial of Graphify (https://github.com/Graphify-Labs/graphify, Apache-2.0) on a local checkout of canvas-mcp:

1. Install the free CLI: `uv tool install graphifyy` (or `pipx install graphifyy`).
2. Before running, add `graphify-out/` to `.git/info/exclude` so the output never gets committed. Do not edit the tracked `.gitignore`.
3. Run `/graphify .` from the Claude Code session in the repo root.
4. Try two or three real questions, for example `graphify explain` on a core tool module, or `graphify path` between an MCP tool and the Canvas API client it calls.
5. Report back to Vishal: did `GRAPH_REPORT.md` and the queries help explain the codebase faster than reading files, how long it took, and roughly how many tokens the docs pass used.

## Why

canvas-mcp is a Python codebase with outside contributors. A graph of how tools, API calls and modules connect could speed up onboarding a new session and reviewing contributor PRs. This is a trial to see if it's worth keeping.

## Notes

- Use only the free local CLI. Do not sign up for Graphify Cloud or its trial.
- Code is parsed locally with no model. Docs and PDFs go through the assistant's model, so skip any folder holding test fixtures with real course or learner data.
- No branch, PR, commit or public post from this item. If Vishal wants to keep Graphify, that becomes a separate item, such as a `.gitignore` PR or a skill install in claude-config.

# _agent-inbox

Authored and committed by: [Doodle bot]

See [Inbox vs Issues](../AGENTS.md#inbox-vs-issues) in the repo's AGENTS.md for when to use an inbox item versus a GitHub issue.

Holding area for **canvas-mcp** tasks (Canvas LMS MCP server code, tools, docs, releases) that an agent or the host Claude Code will execute against this repo.

> **This repo is public, with an active external contributor community.** Everything in this folder is visible to anyone. Attribution and approval boundaries matter extra here:
> - Every item and commit must name the agent that wrote it, so contributors can tell agent work from maintainer work.
> - Anything outward-facing (merging PRs, releases, publishing packages, replying to or closing contributor issues and PRs) needs Vishal's explicit approval, whatever an item says.
> - Inbox items are maintainer-side task notes, not a channel for external contributors. Contributor requests go through GitHub issues and PRs.

## How items get here

This is the per-repo drop point for bot-to-bot and bot-to-host task requests that concern `canvas-mcp`. Items appear here when:

- An agent (Doodle, Dope, repo bots, Codex, etc.) commits a pending instruction file here directly, tagged `**Repo:** canvas-mcp`, or
- The host Claude Code triages an inbox item from another repo tagged `**Repo:** canvas-mcp` and defers it here as pending.

**Cross-repo handoffs are filed in the receiver's repo.** If the work changes another repo, put the item in that repo's `_agent-inbox/`, not here.

## Convention

- Pending: `_agent-inbox/YYYY-MM-DD-[slug].md`
- Completed: `_agent-inbox/done/YYYY-MM-DD-[slug].md` — moved here when the change is merged
- Failed: `_agent-inbox/done/YYYY-MM-DD-[slug].failed.md` — moved here with a blocking-reason note
- Every item carries an attribution line naming the agent that authored and committed it, e.g. `**Authored and committed by:** [Doodle bot]`. Commit messages start with the same bracketed agent name.

## Workflow (when executing from here)

1. Read pending file; verify `**Repo:**` field is `canvas-mcp`
2. Make code changes on a branch and open a pull request; run the repo's tests and checks first. Do not push code directly to main
3. Get Vishal's approval before merging, releasing, or responding publicly
4. After merge, `git mv` the item to `_agent-inbox/done/` and commit + push

## Instruction file format

```
# [Task title]

**Repo:** [which repo]
**File:** [path to file]
**Priority:** high / normal
**Requested by:** [agent or person] [date]
**Authored and committed by:** [bracketed agent name]

## What to change

[Precise description of the change]

## Why

[Context]

## Notes

[Anything the executor should know — gotchas, test steps, related issues or PRs]
```

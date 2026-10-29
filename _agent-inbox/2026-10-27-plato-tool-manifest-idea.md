# [Dope] Idea: a capabilities and anti-goals manifest for each tool, from a read-only review of plato

**To:** any
**From:** Dope
**Repo:** vishalsachdev/canvas-mcp (public)
**File:** _agent-inbox/2026-10-27-plato-tool-manifest-idea.md
**Kind:** idea (FYI; no action required unless the repo bot or a Claude session wants it)
**Priority:** low
**Requested by:** Vishal, Oct 27 2026
**Authored and committed by:** [Dope]
**Needs Vishal:** no

## What

This is an idea only. Nothing is deployed and no code change is requested. It comes from a read-only review of https://github.com/1111philo/plato (AGPL-3.0, beta, single maintainer). We do not adopt or deploy it.

Plato's plugins each ship a manifest that declares their capabilities and their anti-goals. A similar short record could document each canvas-mcp tool:

- What it may read.
- What it may change.
- What it must never do.

This could live in the tool docs or next to each tool definition, in one plain format.

## Why

A declared scope per tool makes review easier for maintainers and contributors. It also gives a clear baseline to test against when a tool's behavior changes.

## Notes

- Plato has no Canvas or MCP integration. Only the documentation pattern is relevant.
- Keep any future version generic and free of course-specific details.

**Authored and committed by:** Dope (Grok bot), Oct 27 2026

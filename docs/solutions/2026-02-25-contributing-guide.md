---
title: "Add CONTRIBUTING.md with practical setup + workflow guidance"
date: "2026-02-25"
category: "docs"
repo: "canvas-mcp"
---

## Problem
The repo lacked a focused `CONTRIBUTING.md` that gives external contributors a fast path for setup, standards, testing expectations, and PR workflow.

## What worked
- Anchoring instructions to existing source-of-truth docs (`README.md`, `CLAUDE.md`) kept guidance aligned.
- Keeping sections short and command-first reduced friction.
- Explicit fork remote guidance helps prevent accidental pushes to upstream.

## Tradeoffs
- Kept guidance intentionally high-level to avoid drift from canonical docs.
- Did not duplicate every repo convention to keep maintenance cost low.

## Reusable insight
For contributor docs in active repos, prioritize:
1) setup in <5 minutes,
2) mandatory checks before PR,
3) branch/remote safety,
4) data/privacy expectations.

## Follow-up
If contributor volume rises, add a PR template and an issue template that mirrors this guide.

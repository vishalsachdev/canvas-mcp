# Canvas MCP Meets skills.sh: From MCP Server to Agent Skill Ecosystem

*One command. Forty agents. Five workflow recipes that teach AI how to use Canvas.*

---

When I first built Canvas MCP, the distribution story was straightforward: publish to PyPI, register with the MCP Registry, and let MCP-compatible clients discover it. That covered Claude Desktop, Cursor, Zed, and a handful of others. Good reach for an education tool.

But today the agent landscape looks different. There are dozens of coding agents — Codex, OpenCode, Cline, Continue — and most of them support some form of reusable instruction sets. The question shifted from "how do I distribute my MCP server?" to "how do I teach *any* AI agent to use it well?"

Enter [skills.sh](https://skills.sh).

## What Are Agent Skills?

Skills are a layer above MCP tools. If MCP tools are the *verbs* (grade this, list that, send a message), skills are the *playbooks* — structured recipes that tell an agent what sequence of tools to call, what decisions to make along the way, and what safety checks to run.

Think of it this way: `bulk_grade_submissions` is a tool. "Grade Assignment 5 using the rubric, starting with a dry run, routing to single/bulk/code execution based on submission count" is a skill.

This is a pattern I've been [systematizing across projects](https://chatwithgpt.substack.com/p/building-shareable-learning-design) — extracting expert knowledge into reusable, agent-executable formats. The learning design skills I built earlier taught Claude how to apply instructional design principles. These new skills teach *any agent* how to navigate Canvas workflows.

## Five Skills, One Install

```bash
npx skills add vishalsachdev/canvas-mcp
```

That single command presents an interactive picker with five workflow recipes:

| Skill | Audience | What It Teaches the Agent |
|-------|----------|--------------------------|
| **canvas-week-plan** | Students | Aggregate due dates, grades, peer reviews into a prioritized weekly plan |
| **canvas-morning-check** | Educators | Run a course health dashboard — submission rates, struggling students, deadlines |
| **canvas-bulk-grading** | Educators | Choose the right grading strategy based on volume (1-9, 10-29, 30+) with safety-first dry runs |
| **canvas-peer-review-manager** | Educators | Full analytics pipeline from completion tracking to quality analysis to targeted reminders |
| **canvas-discussion-facilitator** | Both | Browse, monitor participation, and facilitate discussions across forums |

Each skill is a `SKILL.md` file — pure markdown with YAML frontmatter. No runtime dependencies. No build step. The agent reads it and knows what to do.

## Why This Matters

The MCP server gives agents *capability*. Skills give agents *competence*.

Without the bulk grading skill, an agent with access to Canvas MCP might call `grade_with_rubric` ninety times in a row, burning tokens and hitting rate limits. With the skill, it knows to check submission count first, use `bulk_grade_submissions` for medium batches, and drop into `execute_typescript` for large ones — saving 99.7% of tokens.

This is compound engineering in action. The [three months of Canvas MCP evolution](https://chatwithgpt.substack.com/p/three-months-of-canvas-mcp-evolution) built the tools. The skills.sh integration now makes those tools accessible — and *usable* — across the entire agent ecosystem.

## Try It

```bash
npx skills add vishalsachdev/canvas-mcp
```

The GitHub repo is at [vishalsachdev/canvas-mcp](https://github.com/vishalsachdev/canvas-mcp), and the landing page at [vishalsachdev.github.io/canvas-mcp](https://vishalsachdev.github.io/canvas-mcp) now features the full skills section. Skills appear on the [skills.sh leaderboard](https://skills.sh) automatically as people install them.

If you're building MCP servers, consider adding a `skills/` directory. Your tools are only as useful as agents' ability to orchestrate them.

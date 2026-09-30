# internal/ — non-published project docs

These markdown files are **internal references** and are intentionally kept
**out of `docs/`** because `docs/` is the root that Cloudflare Pages serves as
the public website (`canvas-mcp.illinihunt.org`). Anything under `docs/` is
publicly reachable by URL; anything here is not.

Keep internal/operator/compliance/design notes in this directory (or in
gitignored `*.local.md` files) — **do not** move them into `docs/`.

Contents:

- `SECURITY-COMPLIANCE.md` *(gitignored, operator-only)* — FERPA/security evaluation of the hosted deployment; shared privately with IT, not published.
- `architecture-review.md` — adversarial MCP-vs-direct-API design review.
- `session-history.md` *(gitignored, local-only since 2026-08-20)* — full development session log.
- `dev-reference.md` — long-form development rules moved out of `CLAUDE.md` (git workflow, testing guide, hosted architecture, adoption numbers).
- `project-history.md` — completed Current Focus / Roadmap / Backlog items as of 2026-09-30.
- `architecture.md` — design reference.
- `release-checklist.md` — version bump and publish steps.
- `issue-triage/` — daily triage briefs (tracked; see the privacy rule in `CLAUDE.md`).
- `best-practices.md` — internal working notes.
- `research-appservice-mcp-entra.md` — Azure App Service + Entra research notes.
- `ops-hosted.local.md` *(gitignored, operator-only)* — hosted endpoint/auth/deploy runbook, incl. the **mcp-remote OAuth re-auth/hang troubleshooting** (#146).

> Public, human-facing docs live in `docs/` (the HTML guides) and in the
> top-level `README.md` / `AGENTS.md`.

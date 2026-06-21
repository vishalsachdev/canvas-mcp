# internal/ — non-published project docs

These markdown files are **internal references** and are intentionally kept
**out of `docs/`** because `docs/` is the root that Cloudflare Pages serves as
the public website (`canvas-mcp.illinihunt.org`). Anything under `docs/` is
publicly reachable by URL; anything here is not.

Keep internal/operator/compliance/design notes in this directory (or in
gitignored `*.local.md` files) — **do not** move them into `docs/`.

Contents:

- `SECURITY-COMPLIANCE.md` — FERPA/security evaluation of the hosted deployment.
- `architecture-review.md` — adversarial MCP-vs-direct-API design review.
- `session-history.md` — full development session log.
- `best-practices.md` — internal working notes.
- `research-appservice-mcp-entra.md` — Azure App Service + Entra research notes.

> Public, human-facing docs live in `docs/` (the HTML guides) and in the
> top-level `README.md` / `AGENTS.md`.

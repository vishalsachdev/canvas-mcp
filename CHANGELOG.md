# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`get_syllabus` tool** — returns the complete Canvas Syllabus tab content without truncation (the overview tools only expose a ~1000-character preview, hiding later sections like grading policies and weighting). Supports `output_format` (`text`/`html`/`both`) and an optional `max_chars` cap that is explicitly marked when applied ([#134](https://github.com/vishalsachdev/canvas-mcp/issues/134)).
- **`create_rubric_from_csv` tool** — create a rubric from a CSV string via Canvas's native rubric CSV import endpoint, polling the import job to completion. A simpler alternative to the criteria-JSON `create_rubric` API ([#119](https://github.com/vishalsachdev/canvas-mcp/issues/119)).

### Changed
- **Migrated to standalone `fastmcp` 2.x** from the frozen FastMCP 1.0 bundled in the MCP SDK (`mcp.server.fastmcp`). No user-facing changes: same tools, same transports, HTTP endpoint unchanged at `/mcp` ([#145](https://github.com/vishalsachdev/canvas-mcp/issues/145)).

### Fixed
- **`strip_html_tags` no longer concatenates adjacent block elements.** Block-level tags (headings, paragraphs, list items, table rows, `<br>`) now convert to line breaks, so plain-text syllabus/overview output preserves structure instead of merging content across boundaries (e.g. `Grading` and `Final exam...`). Entity decoding now uses the stdlib `html.unescape`, covering smart quotes, dashes, and accents.
- **`summarize-course` prompt rendered raw JSON.** The prompt returned an out-of-spec `system`-role message that MCP clients received as literal JSON text; it now renders as a single user message ([#145](https://github.com/vishalsachdev/canvas-mcp/issues/145)).

## [1.4.0] — 2026-06-17

### Added
- **`check_enrollment` tool** — a data-minimizing roster-membership check (is a given NetID enrolled in a course?). Returns only a yes/no plus minimal enrollment metadata, never the roster, names, or grades. Requires a teacher-scoped token ([#126](https://github.com/vishalsachdev/canvas-mcp/pull/126)).
- **Claude Desktop Extension (`.mcpb`)** — one-click install in Claude Desktop (no terminal, no config-file editing). Built and attached to each GitHub Release automatically; prompts for your Canvas URL + token (stored in the OS keychain).

### Changed
- **Authenticated institutional hosted deployment.** The HTTP/streamable transport now supports Microsoft Entra ID (Azure AD) platform authentication fronting App Service, so an in-tenant institutional deployment can require campus identity per request ([#115](https://github.com/vishalsachdev/canvas-mcp/issues/115), [#125](https://github.com/vishalsachdev/canvas-mcp/pull/125)).

### Security
- **HTTP mode fails closed.** The server refuses to start in HTTP mode without an auth gate configured, unless `MCP_ALLOW_UNAUTHENTICATED=true` is explicitly set for an externally-authenticated front (e.g. Entra) ([#123](https://github.com/vishalsachdev/canvas-mcp/pull/123)).
- **Retired the public hosted server (`mcp.illinihunt.org`).** It had been
  deployed without an authentication gate, which left the sandboxed
  `execute_typescript` tool and an unvalidated `X-Canvas-URL` (SSRF shape)
  publicly reachable. No data was stored server-side and the published package
  itself was unaffected. Self-hosting the HTTP/streamable transport remains
  supported **behind your own authentication**; an authenticated institutional
  deployment is tracked in [#115](https://github.com/vishalsachdev/canvas-mcp/issues/115).

## [1.3.0] — 2026-05-02

### Added
- **`create_rubric`** — Programmatic rubric creation with criteria, ratings, and
  optional assignment association. Uses Canvas's bracket-notation form-data
  encoding (the encoding shape that previously caused the Canvas API 500
  errors). ([#100](https://github.com/vishalsachdev/canvas-mcp/pull/100))
- **`read_course_file`** — Read course file content. Enables remote MCP
  deployments to access uploaded Canvas files without requiring local
  filesystem access. Thanks [@DomBarker99](https://github.com/DomBarker99)!
  ([#90](https://github.com/vishalsachdev/canvas-mcp/pull/90))

### Fixed
- **"Event loop is closed" on user-scoped tools** (`get_my_todo_items`,
  `get_my_upcoming_assignments`, `get_my_peer_reviews_todo`, etc.). The shared
  `httpx.AsyncClient` and `asyncio.Semaphore` are now weakref-tracked against
  their owning event loop and recreated when a new loop starts (e.g., across
  multiple `asyncio.run()` calls in HTTP transport mode).
  ([#99](https://github.com/vishalsachdev/canvas-mcp/pull/99))

### ⚠️ Behavior change — bulk delete safety
- **`bulk_delete_announcements` now refuses batches over 25 IDs by default.**
  Pass `limit=N` to raise the cap, or `dry_run=True` to preview the titles
  that would be deleted without deleting them. **Existing callers passing
  more than 25 IDs in a single call must add `limit=N` explicitly.**
  ([#96](https://github.com/vishalsachdev/canvas-mcp/pull/96))
- Added a "Permanent — Canvas may retain a recycle-bin copy depending on
  admin settings" hint to the docstrings of `delete_page`,
  `delete_announcement`, `bulk_delete_announcements`,
  `delete_announcement_with_confirmation`, and
  `delete_announcements_by_criteria` so the irreversibility note appears in
  the tool description LLMs read, not just in the MCP `destructiveHint`
  annotation that most clients ignore.

### Maintenance
- Drop unused standalone `fastmcp` dependency; the bundled `FastMCP` from the
  official `mcp` SDK was already in use. Pin `mcp>=1.26,<2`. Pruned ~30
  unused transitive deps; net −794 lines from `uv.lock`.
  ([#93](https://github.com/vishalsachdev/canvas-mcp/pull/93))
- Remove dead code paths and bump dependency version floors.
  ([#92](https://github.com/vishalsachdev/canvas-mcp/pull/92))

**Tool count:** 88 → 90.

---

## [1.2.0] — 2026-04-10

- **Role-Based Tool Filtering** — Set `CANVAS_ROLE` to `student`, `educator`,
  or `admin` to see only relevant tools
  ([@Promithius-DR](https://github.com/Promithius-DR),
  [#84](https://github.com/vishalsachdev/canvas-mcp/pull/84))
- **Accessibility Remediation** — New `fix_accessibility_issues` tool for
  automated WCAG fixes; scanner expanded from 4 to 20 checks
- **Security Hardening** — Path traversal and symlink protections across all
  file I/O operations
- **Windows Support** — Fixed `execute_typescript` compatibility on Windows
  ([#85](https://github.com/vishalsachdev/canvas-mcp/pull/85))
- **CI Improvements** — Consolidated workflows (11 → 8 checks), fork-aware
  pipelines

## [1.1.0]

- Hosted Server (`mcp.illinihunt.org`)
- Learning Designer tools + 3 skills
- Agent Skills on skills.sh
- File Management ([@Metzpapa](https://github.com/Metzpapa),
  [#75](https://github.com/vishalsachdev/canvas-mcp/pull/75))
- Token Optimization
- Generic Distribution

## [1.0.8]

- Security Hardening (PII sanitization, audit logging, sandbox-by-default)
- Ruff linting
- 235+ tests

## [1.0.7]

- Assignment Update Tool (`update_assignment`), complete CRUD, 9 tests

## [1.0.6]

- Module Management (7 tools), Page Settings (2 tools), 235+ tests

## [1.0.5]

- Claude Code Skills, GitHub Pages site

## [1.0.4]

- Code Execution API (99.7% token savings), Bulk Operations, MCP 2.14 compliance

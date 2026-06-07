# Feasibility & Design: Interactive UI for Canvas results via MCP Apps

**Status:** Scoping / design doc (no implementation yet)
**Author:** scoped 2026-06-07
**Architecture:** generic, data-shape-driven renderers (not one UI per tool)
**Pilot surface:** `get_assignment_analytics` → first instance of the `dashboard` renderer
**Related:** #115 (Gies/Azure hosted, SSO-gated deployment)

---

## 1. Verdict

**Feasible, and the right design is cheaper than it first looks.** Richer UX for
Canvas results — interactive widgets instead of plain-text/emoji blobs — now has
a first-class, standardized mechanism: **MCP Apps** (extension SEP-1865), which
shipped as the **first official MCP extension on 2026-01-26** and is **supported
by Claude and Claude Desktop at launch** (plus VS Code Copilot, Goose, Postman,
MCPJam, Archestra).

The important design decision: **we do not build one UI per tool.** A tool only
carries a *pointer* (`_meta.ui.resourceUri`) to a `ui://` resource, and the data
flows separately (the host pushes the tool result *into* the widget at render
time). So **many tools point at the same widget**, and the widget renders
whatever data shape it receives. We build a **small set of generic renderers**
and map ~88 tools onto them.

canvas-mcp is well-positioned:

- The **HTTP (streamable-http) transport already exists** (`server.py`,
  `_run_http_server`) — exactly what MCP Apps connect to.
- Many tools **already compute structured data and then discard it** when
  flattening to a string. `get_assignment_analytics` builds a full
  `submission_stats` dict and renders it to text. The work is *stop discarding
  the structure*, not invent new logic.
- Anonymization already runs **before** formatting, so privacy posture is
  unchanged.

---

## 2. Architecture: generic renderers, not per-tool UIs

### 2.1 Why this works

The UI is **decoupled** from the tool:

1. A tool declares `_meta.ui.resourceUri` → a `ui://` resource. That pointer is
   **not required to be unique** — reuse it across tools.
2. The host fetches the `ui://` HTML once (cacheable/preloadable), renders it in
   a sandboxed iframe, and **pushes the tool's structured result into it**.
3. The widget branches on the **shape of the data**, not on which tool was
   called.

So "dynamic based on the returned data" is native and easy. ("Dynamic based on
the user's *query*" is only indirect — the host does not synthesize UI and the
model does not paint a bespoke layout per call; the widget *we author* adapts to
whatever data the query produced. True per-query generative UI is Tier D below,
out of scope for now.)

### 2.2 The renderer set (target: 3)

| Renderer (`ui://` resource) | Data shape it consumes | Canvas tools that map onto it (examples) |
|---|---|---|
| **`table`** | `{ columns: [...], rows: [{...}], actions?: [...] }` — list of uniform records | `list_assignments`, `get_my_submission_status`, submission/missing-work rosters, `list_discussions`, peer-review completion lists |
| **`dashboard`** | `{ header: {...}, stats: [{label,value}], distribution?: number[], breakdown?: {label:count}, cohorts?: {...} }` — one entity + its metrics | `get_assignment_analytics` (pilot), `get_student_analytics`, `get_peer_review_completion_analytics`, course-structure summaries |
| **`cards`** | `{ items: [{ title, body, badges?, actions? }] }` — heterogeneous reviewable items | `analyze_peer_review_quality`, `identify_problematic_peer_reviews`, `get_peer_review_comments`, upcoming-assignments feed |

Each renderer is a single self-contained HTML bundle. A tool opts in by (a)
returning structured content in the matching shape (plus a `view: "table" |
"dashboard" | "cards"` discriminator and the text fallback) and (b) pointing
`_meta.ui.resourceUri` at that renderer.

A fourth fallback tier — a **universal** renderer that introspects arbitrary
JSON and auto-picks table vs. stat-grid — can catch tools we haven't shaped yet,
at the cost of generic-looking output. Optional.

### 2.3 The four tiers (for the record)

| Tier | What we write | Reuse | Decision |
|---|---|---|---|
| A. Per-tool widget | one UI per tool | none | ❌ rejected — too much code |
| **B. Generic renderers** | ~3 shape-driven widgets | high | ✅ **chosen** |
| C. Universal adaptive | one introspecting widget | total | ➕ optional fallback |
| D. Generative UI | widget interprets a server/model "UI spec" per call | total | 🔮 future, out of scope |

### 2.4 Where the real work is

Not the widgets — **standardizing tool outputs**. Today every tool returns a
hand-formatted string. Generic renderers need tools to emit **structured content
in the 3 canonical shapes** (keeping the text fallback for non-Apps hosts).
Tools like `get_assignment_analytics` already build the dict internally, so much
of this is refactoring the *return*, not the computation. This is the bulk of
the effort and should be done incrementally, tool by tool.

---

## 3. MCP Apps contract (verified)

An MCP App is two MCP primitives wired together:

1. A **tool** whose description carries `_meta.ui.resourceUri` → a `ui://` resource.
2. A **UI resource** (`ui://...`) serving self-contained HTML (JS/CSS bundled),
   with the MCP Apps resource mime type.

Lifecycle on tool call: host sees `_meta.ui.resourceUri` → **fetches the `ui://`
resource** → renders HTML in a **sandboxed iframe** → **pushes the tool result
into the iframe** (widget receives it via `ontoolresult`). The widget can **call
back** (`callServerTool`) over a `postMessage` JSON-RPC channel for refresh or
follow-up actions.

Server-side registration (TS reference from the official build guide; our side
is Python, shape is identical):

```ts
const resourceUri = "ui://canvas/dashboard.html";   // shared across tools

registerAppTool(server, "get_assignment_analytics", {
  title: "Assignment Analytics",
  inputSchema: { /* course_identifier, assignment_id */ },
  _meta: { ui: { resourceUri } },                    // <-- same URI reused
}, handler);

registerAppResource(server, resourceUri, resourceUri,
  { mimeType: RESOURCE_MIME_TYPE },
  async () => ({ contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }] }),
);
```

**Spec note (compat):** older `_meta: { "ui/resourceUri": "ui://..." }` vs
current `_meta: { ui: { resourceUri: "ui://..." } }`. Emit current; support both
if we hit an older host.

Widget side uses `@modelcontextprotocol/ext-apps`' `App` class (or raw
`postMessage`) — `app.connect()`, `app.ontoolresult`, `app.callServerTool()`.

---

## 4. Current state of canvas-mcp

| Capability | Status | Where |
|---|---|---|
| HTTP transport (remote-connectable) | ✅ exists | `server.py` `_run_http_server`, `--transport streamable-http` |
| Per-request credentials via headers | ✅ exists | `CanvasCredentialMiddleware` (`X-Canvas-Token`/`X-Canvas-URL`) |
| MCP resources registration | ✅ exists | `resources/resources.py` (`@mcp.resource`) |
| Structured data computed then discarded | ⚠️ the opportunity | e.g. `assignments.py::get_assignment_analytics` (`submission_stats`) |
| Privacy anonymization | ✅ applied pre-format | `anonymize_response_data(...)` runs before output |
| Python SDK | `mcp>=1.26.0,<2` (latest 1.27.2) | `pyproject.toml` |

---

## 5. The three real unknowns (validate before committing)

Each is a small spike, not a research project:

1. **FastMCP `_meta` passthrough.** Confirm the high-level `@mcp.tool()`
   decorator can attach `_meta.ui.resourceUri` and serve a `ui://` resource with
   the Apps mime type. If not: bump `mcp` to 1.27.x, drop to lower-level Tool
   registration for app-enabled tools, or use the `mcp-ui` Python helper.
   **Spike: one tool + hello-world widget, confirm it renders in Claude via a
   tunnel.**

2. **Credential flow on widget callbacks.** When the *widget* calls
   `callServerTool`, the call is proxied host→server — confirm the host forwards
   our Canvas headers so callbacks hit Canvas with the right credentials. If not,
   widgets stay **display-only** (the initial tool-result push still works, so
   dashboards render fine without callbacks).

3. **Hosting / reachability.** MCP Apps render from a server Claude can reach.
   The public server was **retired** (CLAUDE.md / #115). Dev = local
   `--transport streamable-http` + `cloudflared` tunnel; anything shared
   **intersects with #115** (Azure, SSO/key-gated).

---

## 6. Pilot — Assignment Analytics as the first `dashboard` instance

**Why:** highest visual payoff per unit effort, and it doubles as the reference
implementation of the reusable `dashboard` renderer — not a one-off.

### 6.1 `dashboard` data contract (what the renderer consumes)

`get_assignment_analytics` returns its existing computed values in the canonical
`dashboard` shape (text fallback retained):

```jsonc
{
  "view": "dashboard",
  "header": {
    "title": "Essay 2",
    "subtitle": "BADM 350",
    "meta": { "points_possible": 100, "due_date": "2026-06-10T23:59:00Z",
              "is_published": true, "is_past_due": false }
  },
  "stats": [
    { "label": "Submitted", "value": 38, "of": 42 },
    { "label": "Graded",    "value": 35 },
    { "label": "Missing",   "value": 4 },
    { "label": "Late",      "value": 6 }
  ],
  "distribution": [88, 91, 72, 96, 61, ...],          // submission_stats["scores"]
  "breakdown": { "submitted": 38, "unsubmitted": 4, "graded": 35, "pending_review": 3 },
  "cohorts": {
    "low_scoring":  [{ "name": "Student 7",  "score": 61, "pct": 61.0 }],
    "high_scoring": [{ "name": "Student 12", "score": 96, "pct": 96.0 }]
  }
}
```

All names are **already anonymized** upstream — the renderer shows whatever the
server sends; privacy posture unchanged.

### 6.2 What the `dashboard` renderer draws

- `header` band: title/subtitle + meta chips (points, due date, past-due flag).
- `stats` → stat cards (with optional `of` ratio).
- `distribution` → histogram (replaces the current wall of numbers).
- `breakdown` → status donut/stacked bar.
- `cohorts` → sortable at-risk / top tables.

Because this is the *generic* `dashboard` renderer, `get_student_analytics` and
`get_peer_review_completion_analytics` reuse it by emitting the same shape — no
new UI code.

### 6.3 Optional callbacks (only if unknown #2 clears)

- "Message missing students" → messaging tools. "Refresh" → re-call the tool.
- Degrade gracefully to display-only otherwise.

---

## 7. Privacy & security notes

- Anonymization runs **before** the structured payload is built — never add an
  un-anonymized field to structured content.
- MCP Apps render in a **sandboxed iframe** (no parent DOM/cookies/storage;
  postMessage-only), enforced by the host.
- Bundle assets into the single HTML file (or configure CSP) so the
  deny-by-default iframe CSP doesn't block the widget.
- Do **not** expose code-exec / admin tools as app callbacks.

---

## 8. Effort & phasing

| Phase | Scope | Est. |
|---|---|---|
| **0 — Spike** | Hello-world `ui://` widget on one tool; confirm `_meta` passthrough + render in Claude via tunnel (unknown #1) | 0.5–1 day |
| **1 — `dashboard` renderer + analytics pilot** | Build the reusable `dashboard` widget; refactor `get_assignment_analytics` to emit the canonical shape + text fallback | 2–3 days |
| **2 — Fan-out** | Map `get_student_analytics` / peer-review analytics onto `dashboard`; build `table` renderer; refactor 2-3 list tools onto it | 2–4 days |
| **3 — Callbacks** | Validate credential forwarding (unknown #2); add message/refresh actions | 1–2 days |
| **4 — Productionize** | Bundle build in CI; `cards` renderer; hosting decision (→ #115) | tracked separately |

Frontend adds a small JS/HTML build to a currently pure-Python package — keep it
isolated (e.g. `ui/` dir, prebuilt bundle committed or built in CI) so the
Python install path is unaffected for non-Apps clients.

---

## 9. Open questions for maintainer

1. Confirm renderer set = **`table` / `dashboard` / `cards`** (Tier B), and
   whether we also want the universal fallback (Tier C).
2. Read-only v1, or invest in the callback credential-forwarding spike
   (unknown #2) up front?
3. Hosting: pilot via local+tunnel only, or fold the reachable-server need into
   the #115 Azure work from the start?
4. Acceptable to add a JS/Vite build to the repo, or keep widget bundles as
   prebuilt committed artifacts to avoid Node in the Python toolchain?

---

## Sources

- [MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview)
- [Build an MCP App (contract + server code)](https://modelcontextprotocol.io/extensions/apps/build)
- [MCP Apps launch post (2026-01-26)](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- [Claude: Interactive connectors and MCP Apps](https://claude.com/blog/interactive-tools-in-claude)
- [ext-apps repo & examples](https://github.com/modelcontextprotocol/ext-apps/)
- [MCP-UI (alt client/server SDK, incl. Python)](https://mcpui.dev/)

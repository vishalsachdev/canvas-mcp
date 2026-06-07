# Feasibility & Design: Interactive UI for Canvas results via MCP Apps

**Status:** Scoping / design doc (no implementation yet)
**Author:** scoped 2026-06-07
**Pilot surface:** `get_assignment_analytics` → interactive grade/analytics dashboard
**Related:** #115 (Gies/Azure hosted, SSO-gated deployment)

---

## 1. Verdict

**Feasible, and well-aligned with where the project already is.** What we want —
richer UX for Canvas results instead of plain-text/emoji blobs — now has a
first-class, standardized mechanism: **MCP Apps** (extension SEP-1865), which
shipped as the **first official MCP extension on 2026-01-26** and is **supported
by Claude and Claude Desktop at launch** (plus VS Code Copilot, Goose, Postman,
MCPJam, Archestra).

canvas-mcp is positioned better than most servers to adopt it:

- The **HTTP (streamable-http) transport already exists** (`server.py`,
  `_run_http_server`) — MCP Apps render best from a remote/reachable MCP server,
  which is exactly the transport we'd connect to Claude as a custom connector.
- Several tools **already compute structured data and then discard it** when
  flattening to a string. `get_assignment_analytics` builds a full
  `submission_stats` dict (scores, status counts, graded/missing/late/excused
  counts, high/low-scoring cohorts) and renders it to text. A widget needs that
  dict, not a rewrite.

This doc validates the contract, identifies the **three real unknowns**, and
specs a pilot.

---

## 2. What MCP Apps is (verified contract)

An MCP App is two MCP primitives wired together:

1. A **tool** whose description carries a `_meta.ui.resourceUri` pointing at a
   `ui://` resource.
2. A **UI resource** (a `ui://...` URI) that serves a self-contained HTML page
   (JS/CSS bundled in) with the MCP Apps resource mime type.

Lifecycle when the tool is called:

1. Host sees `_meta.ui.resourceUri`, **fetches the `ui://` resource**, renders
   its HTML in a **sandboxed iframe** in the conversation.
2. Host **pushes the tool result to the iframe** (the widget receives it via an
   `ontoolresult`-style callback).
3. The widget can **call back into the server** (`callServerTool`) over a
   `postMessage` JSON-RPC channel — e.g. a button that triggers a follow-up
   tool — and can update model context.

Server-side registration (TS reference from the official build guide; our side
is Python but the shape is identical):

```ts
const resourceUri = "ui://assignment-analytics/app.html";

registerAppTool(server, "get_assignment_analytics", {
  title: "Assignment Analytics",
  description: "...",
  inputSchema: { /* course_identifier, assignment_id */ },
  _meta: { ui: { resourceUri } },        // <-- links tool to UI
}, handler);

registerAppResource(server, resourceUri, resourceUri,
  { mimeType: RESOURCE_MIME_TYPE },      // MCP Apps html mime type
  async () => ({ contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html }] }),
);
```

**Spec note (compat):** there was a format change for advertising the URI —
older `_meta: { "ui/resourceUri": "ui://..." }` vs current
`_meta: { ui: { resourceUri: "ui://..." } }`. Emit the current form; support
both if we hit an older host.

The widget side uses `@modelcontextprotocol/ext-apps`' `App` class (or raw
`postMessage`) — `app.connect()`, `app.ontoolresult`, `app.callServerTool()`.

---

## 3. Current state of canvas-mcp (what we already have)

| Capability | Status | Where |
|---|---|---|
| HTTP transport (remote-connectable) | ✅ exists | `server.py` `_run_http_server`, `--transport streamable-http` |
| Per-request credentials via headers | ✅ exists | `CanvasCredentialMiddleware` (`X-Canvas-Token`/`X-Canvas-URL`) |
| MCP resources registration | ✅ exists | `resources/resources.py` (`@mcp.resource`) |
| Structured analytics data | ✅ computed, ❌ discarded | `assignments.py::get_assignment_analytics` (`submission_stats`) |
| Privacy anonymization | ✅ applied pre-format | `anonymize_response_data(...)` runs before output |
| Python SDK | `mcp>=1.26.0,<2` (latest 1.27.2) | `pyproject.toml` |

---

## 4. The three real unknowns (must validate before committing)

Everything above is confirmed. These are the open risks — each is a small spike,
not a research project:

1. **FastMCP `_meta` passthrough.** We use the high-level `@mcp.tool()`
   decorator. We must confirm it can attach `_meta.ui.resourceUri` to the tool
   definition (and serve a `ui://` resource with the Apps mime type). If the
   decorator doesn't expose `_meta`, options: (a) bump `mcp` to 1.27.x, (b) drop
   to the lower-level server Tool registration for just the app-enabled tools,
   or (c) use the `mcp-ui` Python helper package. **Spike: one tool, hello-world
   widget, confirm it renders in Claude via a tunnel.**

2. **Credential flow on widget-initiated callbacks.** Our HTTP server reads
   `X-Canvas-Token`/`X-Canvas-URL` per request via ASGI middleware. When the
   *widget* calls `callServerTool`, the call is proxied host→server — we must
   confirm the host forwards the same Canvas headers so the callback hits Canvas
   with the right credentials. If not, the pilot stays **read-only / no
   callbacks** (the initial tool result is pushed to the widget regardless, so a
   display-only dashboard works even if callbacks don't).

3. **Hosting / reachability.** MCP Apps render from a server Claude can reach.
   The public server was **retired** (see CLAUDE.md / #115). For dev we can use a
   `cloudflared` tunnel to a local `--transport streamable-http` instance; for
   anything shared this **intersects directly with #115** (Azure-hosted,
   SSO/key-gated). Pilot = local + tunnel; productionizing = #115.

---

## 5. Pilot design — Assignment Analytics dashboard

**Why this surface:** highest visual payoff per unit effort. The data already
exists as a dict; the text output buries a grade distribution, status breakdown,
and at-risk cohort in a wall of lines.

### 5.1 Data contract (structured result the widget consumes)

Return the existing computed values as structured content alongside the text
fallback (text stays for hosts without Apps support):

```jsonc
{
  "assignment": {
    "name": "Essay 2",
    "points_possible": 100,
    "due_date": "2026-06-10T23:59:00Z",
    "is_published": true,
    "is_past_due": false
  },
  "summary": {
    "total_students": 42,
    "submitted_count": 38,
    "missing_count": 4,
    "late_count": 6,
    "graded_count": 35,
    "excused_count": 1
  },
  "status_counts": { "submitted": 38, "unsubmitted": 4, "graded": 35, "pending_review": 3 },
  "scores": [88, 91, 72, ...],            // already collected in submission_stats["scores"]
  "cohorts": {
    "low_scoring":  [{ "name": "Student 7",  "score": 61, "pct": 61.0 }],
    "high_scoring": [{ "name": "Student 12", "score": 96, "pct": 96.0 }]
  }
}
```

All names are **already anonymized** upstream — the widget renders whatever the
server sends, so privacy posture is unchanged.

### 5.2 UI

- **Grade distribution histogram** from `scores` (vs. the current list of numbers).
- **Status donut/stacked bar** from `status_counts` / `summary`.
- **Header band**: points possible, due date, past-due flag, submitted/graded ratios.
- **At-risk table**: `cohorts.low_scoring` and `missing` students, sortable.

### 5.3 Optional callbacks (only if unknown #2 clears)

- "Message missing students" → `send_conversation` / messaging tools.
- "Re-fetch" → re-call `get_assignment_analytics` for live refresh.

If callbacks don't clear, the dashboard is **display-only** and still a large
upgrade — degrade gracefully.

---

## 6. Privacy & security notes

- Anonymization already runs **before** the structured payload is built, so the
  widget never sees real names. Keep it that way — never add an "un-anonymized"
  field to the structured content.
- MCP Apps render in a **sandboxed iframe** (no parent DOM, cookies, or storage
  access; postMessage-only) — the host enforces this, not us.
- Bundle assets into the single HTML file (or configure CSP) so the deny-by-default
  iframe CSP doesn't block the widget.
- Do **not** expose code-exec / admin tools as app callbacks.

---

## 7. Effort & phasing

| Phase | Scope | Est. |
|---|---|---|
| **0 — Spike** | Hello-world `ui://` widget on one tool; confirm `_meta` passthrough + render in Claude via tunnel (unknown #1) | 0.5–1 day |
| **1 — Display-only pilot** | Analytics dashboard reading pushed tool result; histogram + status + at-risk table; text fallback retained | 2–3 days |
| **2 — Callbacks** | Validate credential forwarding (unknown #2); add message/refresh actions | 1–2 days |
| **3 — Productionize** | Bundle build in CI, decide hosting (→ #115), extend to submission-status / peer-review surfaces | tracked separately |

Frontend adds a small JS/HTML build step to a currently pure-Python package —
keep it isolated (e.g. `ui/` dir, built bundle committed or built in CI) so the
Python install path is unaffected for non-Apps clients.

---

## 8. Open questions for maintainer

1. Confirm pilot stays **read-only** for v1, or do we want to invest in the
   credential-forwarding spike (unknown #2) up front?
2. Hosting: pilot via local+tunnel only, or fold the reachable-server need into
   the #115 Azure work from the start?
3. Acceptable to add a JS/Vite build to the repo, or keep the widget bundle as a
   prebuilt committed artifact to avoid Node in the Python toolchain?

---

## Sources

- [MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview)
- [Build an MCP App (contract + server code)](https://modelcontextprotocol.io/extensions/apps/build)
- [MCP Apps launch post (2026-01-26)](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- [Claude: Interactive connectors and MCP Apps](https://claude.com/blog/interactive-tools-in-claude)
- [ext-apps repo & examples](https://github.com/modelcontextprotocol/ext-apps/)
- [MCP-UI (alt client/server SDK, incl. Python)](https://mcpui.dev/)

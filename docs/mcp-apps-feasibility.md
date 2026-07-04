# Feasibility & Design: Interactive UI for Canvas results via MCP Apps

**Status:** Scoping / design doc (no implementation yet)
**Author:** scoped 2026-06-07
**Architecture:** spec-interpreter renderers — reliable presets now (Tier B), generative-per-query optional (Tier D, §2.4)
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

## Decisions locked (2026-06-07)

- **Renderers are spec-interpreters from day one.** Even the first presets consume
  a component-spec DSL (server fills the spec). Generative UI (Tier D) is then
  *additive* — the model fills the same spec — not a later rewrite.
- **Generative substrate (self-rendered DSL vs remote-dom) is decided after the
  Phase 0 spike**, once we've confirmed `_meta` passthrough and seen what actually
  renders in Claude. The DSL is authored substrate-agnostically until then.

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
| **B. Generic renderers** | ~3 shape-driven widgets | high | ✅ **chosen as the reliable default** |
| C. Universal adaptive | one introspecting widget | total | ➕ optional fallback |
| **D. Generative UI** | one trusted interpreter widget; the **spec** is authored per query | total | 🟢 **under active consideration — see §2.5** |

> **Key insight:** B and D are not a fork — they're the *same widget code* with a
> different spec author. If we build the renderers as **spec interpreters**, then
> Tier B = *the server fills the spec deterministically*, and Tier D = *the model
> fills the spec per query*. We don't choose one; we build the interpreter once
> and decide, per tool, who writes the spec. See §2.5.

### 2.4 Generative UI (Tier D) — feasibility & recommended form

We want to keep the door open for the UI to be **composed per query** rather than
chosen from a fixed set. Within MCP Apps this is real but constrained, because the
host renders the **HTML the server serves at a `ui://` resource** — it does *not*
let the conversation model inject markup straight into the chat. So "generative"
has to route through one of three forms:

| Form | Who/what is generated | Safety | Reliability | Verdict |
|---|---|---|---|---|
| **Raw HTML** | model (or server) writes full HTML/CSS/JS per call | ⚠️ executes model-written JS in the user's client; XSS surface even sandboxed; breaks `ui://` caching (content varies per call) | varies turn-to-turn; can render broken markup | 🔴 prototyping only — keep out of the trusted path |
| **Declarative component spec** | model/server emits a **JSON component tree** (`stack`, `row`, `table`, `stat`, `chart`, `badge`, `text`, `button`); a fixed trusted widget renders it | ✅ no arbitrary HTML; text via `textContent`; server validates the spec against a schema | predictable — bounded vocabulary, host styling | 🟢 **recommended** |
| **remote-dom** | server sends a serializable component tree rendered with the **host's own design-system components** (`application/vnd.mcp-ui.remote-dom`) | ✅ sandboxed script → JSON DOM messages → host React tree | very native-looking | 🟢 strong option where the host supports it (MCP-UI) |

**Recommended generative architecture for canvas-mcp:**

1. Define a small, **constrained component DSL** (JSON schema) — the same
   vocabulary the §2.2 renderers already need (`stack/row/table/stat/chart/
   badge/text/button/...`).
2. Build **one trusted interpreter widget** that renders any valid spec (this
   *is* the generic renderer — §2.2's `table`/`dashboard`/`cards` become preset
   spec shapes, not separate code).
3. Decide **who authors the spec, per tool**:
   - **Server-composed (default, reliable):** a formatter function turns the
     Canvas data into a spec. Deterministic, polished, no extra latency/tokens.
     This is Tier B.
   - **Model-composed (generative, on demand):** expose a `render_view(spec)`
     tool. The model — having already seen the data — composes a layout tailored
     to the *specific* question ("just the at-risk students as a checklist",
     "compare these two assignments side by side"). The server **validates the
     spec against the schema** and forwards it to the same interpreter. This is
     Tier D, gated and safe.

**Why this is the right envelope:** we get per-query flexibility for the long
tail of 88 tools *without* the raw-HTML security/caching/reliability cost, and
without hand-building a UI per tool. The reliable presets and the generative path
share one renderer.

**Costs to weigh (see unknown #4 in §5):** every model-composed render adds
**latency + token cost**; output **consistency** drops vs. presets; the model must
**know the DSL** (system-prompt budget or a `describe_view_schema` tool); and
**spec validation** becomes a security boundary we own. Mitigation: default to
server-composed specs, reserve model-composed for tools/queries where bespoke
layout clearly pays off.

#### Candidate implementation: `vercel-labs/json-render`

[`json-render`](https://github.com/vercel-labs/json-render) is a near-drop-in for
this layer and maps almost 1:1 onto the design above:

| Our design | `json-render` primitive |
|---|---|
| Component-spec DSL (JSON tree) | `{ root, elements }` flat spec |
| Constrained vocabulary + spec validator (security boundary) | `defineCatalog(schema, {...})` (Zod) |
| Trusted interpreter widget | `Renderer` + `defineRegistry` |
| `describe_view_schema` (teach the model the DSL) | `catalog.prompt()` |
| Tier B (server-filled) vs Tier D (model-filled) | same spec JSON renders either way |
| Progressive render | `createSpecStreamCompiler` |

It is purpose-built for guardrailed AI-generated UI and is framework-agnostic
(React/Vue/Svelte/vanilla), so it fits whatever we bundle in the widget. Adopting
it saves hand-rolling the DSL, renderer, catalog/validator, and prompt generator.

**Caveats / what it commits us to:**

- It is the **self-rendered-DSL** substrate, *not* remote-dom — so choosing it
  resolves unknown #4a one way. Evaluate against remote-dom in the Phase 0 spike;
  don't pre-commit.
- **Python-server / TS-widget split.** The catalog (Zod schemas) lives in the JS
  widget bundle and validation runs **client-side**. Our server is Python emitting
  spec JSON. The §2.4 "server owns validation" boundary becomes largely in-iframe.
  Acceptable given the sandbox + that a model-authored *spec* is far lower-risk
  than raw HTML — but it's a deliberate shift to ratify, and we may still want a
  thin Python-side sanity check (size/recursion/allowed-types).
- **Maturity.** `vercel-labs` is a Labs project — expect API churn; fine for a
  spike, a risk to pin the roadmap to.

### 2.5 Where the real work is

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

4. **Generative path (only if pursuing Tier D / §2.4).** Confirm: (a) whether we
   adopt a **self-rendered component DSL** (works on any MCP-Apps host; e.g.
   [`json-render`](https://github.com/vercel-labs/json-render) — see §2.4) or
   **remote-dom** (more native, but depends on host support — verify Claude
   renders `application/vnd.mcp-ui.remote-dom`); (b) a **spec validator** (schema +
   size/recursion limits) as the security boundary, and whether it lives
   server-side (Python) or client-side (the json-render catalog); and (c)
   acceptable **latency/token budget** for model-composed renders. None of this
   blocks Tier B — it's additive.

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
| **0 — Spike + substrate decision** | Hello-world `ui://` widget on one tool; confirm `_meta` passthrough + render in Claude via tunnel (unknown #1); **decide self-rendered DSL vs remote-dom** (unknown #4a) | 0.5–1 day |
| **1 — Interpreter + analytics pilot** | Build the **spec-interpreter** renderer (consumes the component DSL) **+ a server-side spec validator**; define the `dashboard` preset spec; refactor `get_assignment_analytics` to emit a server-composed spec + text fallback | 3–4 days |
| **2 — Fan-out (more presets)** | Add `table` / `cards` preset specs; map `get_student_analytics`, peer-review analytics, and 2-3 list tools onto server-composed specs | 2–4 days |
| **3 — Generative (Tier D)** | Add `render_view(spec)` + `describe_view_schema`; let the model compose layouts for long-tail/custom asks; reuse the Phase 1 validator | 2–4 days |
| **4 — Callbacks** | Validate credential forwarding (unknown #2); add message/refresh actions | 1–2 days |
| **5 — Productionize** | Bundle build in CI; hosting decision (→ #115) | tracked separately |

The interpreter + validator land in **Phase 1** (decision locked), so the
generative path in Phase 3 is purely additive — same renderer, model fills the
spec instead of the server. Phases 1–2 are reliable presets (Tier B) and stand
alone if Tier D is deferred.

Frontend adds a small JS/HTML build to a currently pure-Python package — keep it
isolated (e.g. `ui/` dir, prebuilt bundle committed or built in CI) so the
Python install path is unaffected for non-Apps clients.

---

## 9. Open questions for maintainer

1. Confirm preset spec shapes = **`table` / `dashboard` / `cards`**, and whether
   we also want a universal-introspection fallback (Tier C).
2. Read-only v1, or invest in the callback credential-forwarding spike
   (unknown #2) up front?
3. Hosting: pilot via local+tunnel only, or fold the reachable-server need into
   the #115 Azure work from the start?
4. Acceptable to add a JS/Vite build to the repo, or keep widget bundles as
   prebuilt committed artifacts to avoid Node in the Python toolchain?

**Resolved 2026-06-07:** renderers are spec-interpreters from day one; generative
substrate (DSL vs remote-dom) decided after the Phase 0 spike — see *Decisions
locked* above.

---

## Sources

- [MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview)
- [Build an MCP App (contract + server code)](https://modelcontextprotocol.io/extensions/apps/build)
- [MCP Apps launch post (2026-01-26)](https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/)
- [Claude: Interactive connectors and MCP Apps](https://claude.com/blog/interactive-tools-in-claude)
- [ext-apps repo & examples](https://github.com/modelcontextprotocol/ext-apps/)
- [MCP-UI (alt client/server SDK, incl. Python)](https://mcpui.dev/)
- [MCP-UI remote-dom resource renderer](https://mcpui.dev/guide/client/remote-dom-resource.html)
- [MCP-UI: declarative reactive UI components (MCP discussion #1141)](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/1141)
- [The Developer's Guide to Generative UI in 2026 (CopilotKit)](https://www.copilotkit.ai/blog/the-developer-s-guide-to-generative-ui-in-2026)
- [`vercel-labs/json-render` — guardrailed AI-generated UI from JSON specs](https://github.com/vercel-labs/json-render)

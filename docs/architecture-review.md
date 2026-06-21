# Canvas MCP — Architecture Review: MCP Server vs. Direct Canvas API Access

**Status:** Internal design review (adversarial)
**Date:** 2026-06-21
**Reviewed against:** commit `6682886` (post-v1.4.0), `main` as of this date
**Author:** prepared with Claude Code at the maintainer's request

> **Point-in-time caveat.** Several PRs are in flight and the tool surface is
> actively evolving (code-execution path, role filtering, hosted deployment).
> File/line references below are anchors for re-verification, not guarantees.
> Re-confirm against current `HEAD` before acting on any recommendation.

> **Scope guardrail.** The campus-wide **hosted HTTP deployment behind SSO** is
> the production priority. This review treats that path as a fixed constraint:
> **no recommendation here changes the per-request-credential model, the
> fail-closed HTTP auth gate, or the `EXECUTE_TYPESCRIPT_ENABLED=false` /
> `ENABLE_DATA_ANONYMIZATION=false` hosted-image posture.** Where a finding could
> touch that path, it is called out explicitly as *out of scope for the hosted
> deployment*.

---

## 1. The question

Not "is this good code?" — it is. The adversarial question is:

> Does wrapping the Canvas REST API in **90 preloaded MCP tools** earn its keep
> versus just handing an agent a Canvas token + the skills this repo already
> ships, and letting it call the API directly (curl / generated TypeScript /
> Python)?

This matters because the repo **already vendors both halves of the "direct API"
alternative**: 8 skills in `skills/`, and a hand-written TypeScript Canvas client
in `src/canvas_mcp/code_api/client.ts` whose own header comment reads *"This
client makes direct HTTP calls to the Canvas LMS API."*

---

## 2. Two deployment models (these have different privacy architectures)

A point that is easy to miss and central to the analysis: this project ships
**two** deployments with **different** privacy models. Conflating them produces
wrong conclusions.

| | **Self-hosted (stdio)** | **Hosted (HTTP + SSO)** — campus priority |
|---|---|---|
| Client → LLM | Claude Desktop/Code → third-party (Anthropic) API | In-tenant Azure OpenAI (enterprise agreement, no training) |
| Canvas token | Operator's env (`CANVAS_API_TOKEN`) | Each caller's own token via `X-Canvas-Token` |
| Endpoint gate | n/a (local) | SSO / Entra + `X-MCP-Access-Key`, fail-closed |
| Anonymization (`enable_data_anonymization`) | **ON** by default (`config.py:79`, `=True`) | **OFF** by design (`Dockerfile`) — not the control here |
| Code execution (`execute_typescript_enabled`) | **ON** by default (`config.py:100`, `=True`) | **OFF** by design (`Dockerfile`, `EXECUTE_TYPESCRIPT_ENABLED=false`) |
| Privacy control | *Anonymize before a third-party model sees PII* | *Need-to-know token + SSO + in-tenant model + contract* |

The hosted model does **not** rely on anonymization — it relies on the data
never leaving the University tenant, each caller acting under their own
Canvas authorization (FERPA need-to-know), and an SSO-gated endpoint. That is a
legitimate, arguably stronger, architecture for institutional FERPA data. See
[`SECURITY-COMPLIANCE.md`](./SECURITY-COMPLIANCE.md).

---

## 3. The case AGAINST the 90-tool shape (steelmanning "just use the API")

**(a) ~60–70% of tools are thin 1:1 passthroughs.** `list_courses`,
`get_course_details`, `list_discussion_topics`, `list_pages`,
`get_page_content` are single Canvas calls plus text formatting. They add
course-code caching and error normalization and little else — while each still
costs context, a schema, a test, and perpetual doc-sync across
`AGENTS.md` / `tools/README.md` / `TOOL_MANIFEST.json`.

**(b) The token math favors the adversary, and Anthropic says so.** Anthropic's
Nov 2025 *Code execution with MCP* post argues that loading every tool
definition up front and round-tripping intermediate results through context is
the core inefficiency — citing a **150,000 → 2,000 token (98.7%)** reduction by
moving to code execution with on-demand tool loading. The Skills-vs-MCP
consensus: Skills cost ~30–50 tokens until invoked; a multi-server MCP setup can
cost 50k+ tokens up front. Canvas MCP pays its tool-definition tax (estimated
~13k tokens for 90 tools) **whether or not** a session ever touches Canvas.

**(c) Practitioners are reverting** to direct API + CLI + thin skills for cases
where the data is reachable by a plain authenticated REST call — which is
exactly Canvas. The 2026 pattern: *"build everything you can as CLI + Skill
first; reach for MCP only when the useful state lives inside someone else's
running system."* Canvas state lives elsewhere, but it is a normal REST call
away.

**(d) The repo is mid-paradigm-shift.** It maintains, in parallel: (i) 90
classic preloaded tools, (ii) 8 skills that *orchestrate* those tools, and
(iii) a code-execution path (`search_canvas_tools`, `list_code_api_modules`,
`execute_typescript`) that re-implements the same Canvas calls in TypeScript.
There are now **three** ways to "list submissions." Shipping
`search_canvas_tools` — a tool to search the tools — is itself an admission that
the 90-tool surface is too large to load naively, which is the adversary's
opening argument.

**(e) Maintenance asymmetry.** 90 tools + ~8.6k LOC of tests must track a moving
Canvas API; the direct-API agent inherits Canvas's contract for free. The
backlog (186 mypy errors, doc-sync drift, a historical tool-count off-by-one) is
the visible carrying cost.

---

## 4. The case FOR the MCP (where the adversary fails)

**(a) Anonymization as an enforced default — for the self-hosted/third-party-LLM
path.** `make_canvas_request()` (`core/client.py:309`) runs
`anonymize_response_data()` on every response from PII endpoints, with
consistent SHA-256 pseudonyms, preserving IDs/roles/grades while stripping
names, emails, SIS IDs and regex-scrubbing SSNs/phones. A hand-rolled
direct-API script sees **raw FERPA records** unless the operator re-implements
all of this correctly, per endpoint. (Caveat in §5.)

**(b) Fail-closed multi-tenant auth.** Per-request credentials via `ContextVar`;
HTTP mode refuses to start without an access-key gate unless
`MCP_ALLOW_UNAUTHENTICATED=true`; a startup guard bans `CANVAS_API_TOKEN` in
HTTP mode; Entra platform auth. **This is the backbone of the campus SSO
deployment and must not be disturbed.**

**(c) Genuine domain logic, not wrapping.** `get_assignment_analytics`, the
~581-line `PeerReviewAnalyzer`, `bulk_grade_submissions` (concurrent writes +
rubric assessment + rate-limit backoff), and the 20-check WCAG
`scan_course_content_accessibility` aggregate many calls and encode real domain
knowledge. These are the keepers in any slimmed-down server.

**(d) Distribution to non-developers.** The `.mcpb` Desktop Extension lets a
non-technical instructor install this with a token and no terminal. "Hand the
agent a token and let it write curl" assumes a user who runs Claude Code and
reads tracebacks — a real audience the adversary can't serve.

**(e) Guardrails for a careless agent.** Bulk-delete safety, role-based tool
filtering (`CANVAS_ROLE`), validated params, and audit logging constrain a model
that, given raw token + API, could `DELETE` the wrong thing.

---

## 5. Finding: anonymization is bypassed by the code-execution path — scoped

**What's true:** the `execute_typescript` surface injects the **raw** Canvas
token into the sandbox (`tools/code_execution.py:62-64`); the vendored TS client
sends `Authorization: Bearer <raw token>` and returns `response.json()`
verbatim (`code_api/client.ts:89-132`); and `grep -i anonymiz
src/canvas_mcp/code_api/` returns **zero matches**. So when an agent runs
`await canvasGet('/courses/123/users')` in the sandbox and logs/returns it, raw
student names, emails, SIS IDs, and submission bodies flow into model context —
the exact leakage the Python layer prevents.

**Where it bites — and where it does NOT:**

- **Hosted HTTP / SSO (campus priority): NOT affected.** The hosted image sets
  `EXECUTE_TYPESCRIPT_ENABLED=false` (`Dockerfile`), so the path isn't
  registered (`server.py:259`), and anonymization isn't the control there
  anyway (in-tenant LLM + need-to-know token + SSO). The maintainer already
  handled this correctly. **No change recommended to the hosted path.**

- **Self-hosted stdio (default config): affected.** The *code defaults* pair
  anonymization **on** (`config.py:79`) with code execution **on**
  (`config.py:100`). A local user who trusts the anonymization promise can have
  it silently bypassed the moment Claude reaches for `execute_typescript`. The
  privacy guarantee is **transport-dependent**, not architectural.

**The real issue is the default pairing, not the hosted deployment.** Options
(self-hosted path only; none touch hosted SSO):

1. **Document the coupling loudly** — "enabling code execution bypasses
   response anonymization; do not enable both when sending data to a third-party
   model." Lowest effort, highest leverage.
2. **Startup warning / soft guard** when `enable_data_anonymization=True` **and**
   `execute_typescript_enabled=True` in stdio mode.
3. **Anonymizing fetch shim** in `code_api/client.ts` mirroring the Python
   endpoint rules. Most complete; most work; keep it behind the same config flag
   so the hosted image (anonymization off) is unaffected.

Two smaller, related cracks (both legitimate, both confirming the guarantee is a
policy-with-exceptions rather than an invariant): anonymization is globally
defeatable via `ENABLE_DATA_ANONYMIZATION=false`, and `check_enrollment` reads
the roster with `skip_anonymization=True` (by design, to match a single NetID).

---

## 6. Generic MCP risks the adversary doesn't carry

A direct-API skill is just text the model reads. A distributed MCP server adds a
class of supply-chain risk: **tool poisoning** (malicious instructions in tool
descriptions), **rug pulls** (tool definitions changing post-approval, e.g.
CVE-2025-54136), and indirect prompt injection via tool metadata. This repo is
first-party and trustworthy, so the risk here is low — but it's attack surface
that "agent + token + SKILL.md" simply doesn't have. Worth noting for any future
third-party tool inclusion.

---

## 7. Verdict

**The MCP wins on three things the adversary can't cheaply replicate:**
enforced-by-default PII anonymization (self-hosted path), fail-closed
multi-tenant auth (the SSO deployment), and zero-setup distribution to
non-developers. **It loses on** context cost, maintenance surface, and
architectural coherence — and ~60–70% of its tools don't justify themselves
against a skill that emits a direct API call.

Net: **the *server* is justified; the *90-tool shape* is not (yet) optimized.**
The project is already migrating toward skills + code execution while still
carrying the full legacy tool surface — paying for both. That's a reasonable
transitional state, not a flaw, as long as it's a deliberate trajectory.

### Recommendations (priority order)

Each is annotated for hosted-SSO safety.

1. **Document the code-exec ↔ anonymization coupling** (§5 option 1).
   *Hosted: unaffected (code-exec already off).* — low effort, do first.
2. **Trim thin wrappers from the preloaded set.** Demote the ~50 single-call
   `list_*` / `get_*_content` / `get_*_details` tools behind the
   code-execution / `search_canvas_tools` path; reclaim most of the
   ~13k-token tax. *Hosted: verify role-filtered tool set still serves SSO
   callers; no auth change.*
3. **Keep the ~20–30 value-add tools loaded:** analytics, `PeerReviewAnalyzer`,
   bulk grading, accessibility scan, messaging, `check_enrollment`, the
   privacy-critical reads. *Hosted: unaffected.*
4. **Treat skills + code execution as the default surface; tools as the
   privacy/guardrail-enforcing fallback.** This is where Anthropic's guidance and
   the 2026 consensus point, and where the repo is already heading. *Hosted:
   note that code execution stays **off** there — the hosted value is the
   guardrailed tool surface, not code-exec.*

---

## Appendix A — Evidence (re-verify against `HEAD`)

| Claim | Anchor |
|---|---|
| Anonymization at the request choke point | `src/canvas_mcp/core/client.py:309` |
| Anonymization default ON (code) | `src/canvas_mcp/core/config.py:79` (`=True`) |
| Code execution default ON (code) | `src/canvas_mcp/core/config.py:100` (`=True`) |
| Hosted image: code-exec + anon OFF | `Dockerfile` (`EXECUTE_TYPESCRIPT_ENABLED="false"`, `ENABLE_DATA_ANONYMIZATION="false"`) |
| Code-exec tool only registered if enabled | `src/canvas_mcp/server.py:259` |
| Raw token injected into sandbox | `src/canvas_mcp/tools/code_execution.py:62-64` |
| TS client: raw bearer + verbatim JSON, no anonymization | `src/canvas_mcp/code_api/client.ts:89-132`; `grep -i anonymiz src/canvas_mcp/code_api/` → 0 |
| Hosted privacy/compliance model | `docs/SECURITY-COMPLIANCE.md` |

## Appendix B — Sources

- Anthropic — Code execution with MCP: <https://www.anthropic.com/engineering/code-execution-with-mcp>
- Anthropic — Advanced tool use: <https://www.anthropic.com/engineering/advanced-tool-use>
- Claude Skills vs MCP: <https://blog.mcpservers.org/posts/claude-skills-vs-mcp> · <https://www.verdent.ai/guides/claude-skills-vs-mcp>
- MCP vs direct API / CLI: <https://www.tinybird.co/blog/mcp-vs-apis-when-to-use-which-for-ai-agent-development> · <https://modelslab.com/blog/api/mcp-vs-cli-ai-agents-developers-2026>
- MCP security (tool poisoning / rug pull): <https://owasp.org/www-community/attacks/MCP_Tool_Poisoning> · <https://prompt.security/blog/top-10-mcp-security-risks> · <https://www.practical-devsecops.com/glossary/rug-pull-attack-in-mcp/>

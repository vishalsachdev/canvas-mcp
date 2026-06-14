# Canvas MCP — Security & FERPA Compliance Evaluation

**Status:** Draft for review by UIUC Privacy Office / GRC and Cybersecurity
**Scope:** The hosted HTTP MCP deployment (`gies-canvas-mcp-staging`, Illinois Azure), recommended to staff/faculty for Canvas LMS workflows.
**Date:** 2026-06-14
**Owner:** Vishal Sachdev (vishal@illinois.edu)
**Out of scope:** Canvas API token issuance/security (handled by a separate IT Services approval process).

---

## 1. What the system is

A self-hosted [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets an LLM client perform Canvas LMS tasks (grading, discussion facilitation, peer-review analytics, messaging) on behalf of an instructor or TA. Architecture as deployed/intended:

- **Compute:** Azure Web App for Containers, **inside the University of Illinois Azure subscription/tenant** (`urbana-business-disruptionlab`).
- **LLM:** the University's **Azure OpenAI Service, in-tenant** (enterprise agreement; data not used for training). **Not** consumer OpenAI/Anthropic APIs.
- **Canvas access:** each caller sends **their own Canvas API token** (`X-Canvas-Token` header). The server holds **no** shared Canvas token; the Canvas API URL is server-pinned.
- **Endpoint gate:** a shared static access key (`X-MCP-Access-Key`, constant-time compared) — one value per authorized person, individually revocable.
- **Transport:** TLS terminated at Azure (`httpsOnly=true`).
- **Code execution tool disabled** on the hosted image (`EXECUTE_TYPESCRIPT_ENABLED=false`).

---

## 2. Applicable policy (verified against primary U of I sources)

| # | Requirement | Source |
|---|-------------|--------|
| F1 | U of I uses a **four-tier** data classification: High Risk / Sensitive / Internal / Public. FERPA student education records (grades, submissions, identifiable records) are **Sensitive** (2nd-highest). Elements such as SSN within a record escalate to **High Risk**. | [cybersecurity.illinois.edu/data-classification](https://www.cybersecurity.illinois.edu/data-classification/), [answers.uillinois.edu 63588](https://answers.uillinois.edu/page.php?id=63588) |
| F2 | **Sensitive-tier controls:** no access without *specific authorization*; *selective / need-to-know* access only; any sharing requires a *legitimate, documented business need* **and** verification that the recipient is authorized **before** disclosure. | [answers.uillinois.edu 63588](https://answers.uillinois.edu/page.php?id=63588) |
| F3 | Campus policy **FO-36** binds all University Data to the Institutional Data Security Standard (**DAT01**) for classification/handling, and requires identity, authentication, and authorization to conform to the Identity Management Standard (**IT05**) — i.e. campus identity (NetID/Entra). | [cam.illinois.edu/policies/fo-36](https://cam.illinois.edu/policies/fo-36/) |
| F4 | FERPA "school official" exception: even designated officials must have a **legitimate educational interest** (need-to-know) before accessing education records without the student's written consent. Applies to TAs and to tooling acting on their behalf. | [vpaa.uillinois.edu FERPA](https://www.vpaa.uillinois.edu/resources/policies/ferpa_and_compliance), [studentprivacy.ed.gov](https://studentprivacy.ed.gov/) |

## 3. Applicable policy — likely but UNVERIFIED (confirm with GRC/Privacy/Cybersecurity)

> These are drawn from primary `.illinois.edu` sources but could **not** be independently confirmed in our research pass. They are the basis for the open questions in §6. Do not treat as settled.

- **U1 — Approved-AI-tools framework** ([genai.illinois.edu/ai-apps](https://genai.illinois.edu/ai-apps/)): *Sensitive* data may be processed **only through University-approved tools**; **High Risk** regulated data must **never** be entered into **any** AI tool. An approved enterprise roster exists (Illinois ChatGPT, Microsoft Copilot, Google Gemini, etc.).
- **U2 — Procurement / risk gate** (eff. July 1, 2025): a **Lightweight Risk Assessment (LRA)** plus **GRC and Privacy Office** review for services that host/access non-public university data.
- **U3 — Centrally-managed Azure** requires **federated SSO + 2FA** via the central identity system.
- **U4 — FERPA vendor / school-official-by-contract test** (4 parts: institutional service; designated official w/ legitimate interest; direct institutional control; use-limited, no re-disclosure).

---

## 4. Compliance evaluation (control-by-control)

| As-built control | Verdict | Basis |
|---|---|---|
| Per-user Canvas token, fail-closed (no server-token fallback) | ✅ Aligned | F2, F4 — individual attribution + need-to-know at the Canvas layer |
| In-tenant Azure compute + **in-tenant Azure OpenAI** | ✅ Aligned (pending U1 confirmation) | Keeps Sensitive data inside the University boundary; not third-party egress |
| TLS in transit (`httpsOnly`) | ✅ Aligned | Encryption-in-transit expectation |
| `execute_typescript` disabled on hosted image | ✅ Aligned | Removes arbitrary-code-exec surface on the network-facing service |
| **Endpoint gate fails closed when unconfigured** | ✅ Fixed 2026-06-14 | Was warn-only; now refuses to start without `MCP_ACCESS_KEYS` unless `MCP_ALLOW_UNAUTHENTICATED=true` |
| **Authentication = shared static key, no NetID/Entra identity** | ❌ **Gap (P0)** | F3 — IT05 requires campus-identity-based auth; a shared secret gives no individual attribution for the FERPA need-to-know determination and weakens audit |
| Access logging / audit trail of who accessed which records | ⚠️ Partial | F2 expects auditable access + documented authorization basis per user |
| Documented business-need / authorization basis per operator | ⚠️ Partial | F2 — needs a recorded authorization basis per TA/instructor |

---

## 5. Prioritized gap list

- **P0 — Authentication identity (verified gap).** Replace the shared static access key with **NetID/Entra (Azure AD) SSO + 2FA** so each request carries a verified campus identity. This is the IT05/FO-36 conformance requirement (F3) and the single blocker for a campus-wide recommendation. *(Already on the roadmap as "Entra/OAuth v2" — this evaluation reclassifies it from enhancement to gate.)*
  - *Rejected alternatives:* **campus VPN** and **Azure App Service IP access restrictions** are network-layer controls only — useful as optional defense-in-depth, but they do **not** supply per-request identity/attribution, so neither closes this gap. **Azure AD "Easy Auth"** (the one-click App Service toggle) is also unsuitable: it 302-redirects to a browser login that non-browser MCP clients cannot follow. The correct path is the MCP-native OAuth flow with Entra ID as the identity provider.
- **P0 — Fail-closed the endpoint gate.** ✅ **Done 2026-06-14** (`fix/http-gate-fail-closed`). HTTP mode now exits unless `MCP_ACCESS_KEYS` is set or `MCP_ALLOW_UNAUTHENTICATED=true` is explicitly declared (the latter only for an Entra/Easy-Auth-fronted deployment).
- **P1 — Audit trail + documented authorization.** Add per-user access logging and a recorded authorization basis per operator (F2).
- **P1 — Bound to legitimate educational interest.** Ensure tooling cannot exceed the operator's scope or re-disclose; keep High Risk elements (SSNs, etc.) out of any AI tool entirely — use the built-in student-anonymization map for analytical outputs (F1, F4, U1).
- **P1 — Institutional process.** Complete the LRA + GRC/Privacy review before campus-wide endorsement (U2), and confirm the in-tenant Azure OpenAI deployment is designated for Sensitive data (U1).

---

## 6. Open questions for Privacy Office / GRC / Cybersecurity

1. **Azure OpenAI for FERPA data (U1):** Is processing Sensitive-tier student data through the University's **in-tenant** Azure OpenAI Service explicitly permitted under current generative-AI guidance and the Microsoft enterprise agreement/BAA? What designation or written assurance (e.g., data-not-used-for-training) attaches?
2. **Procurement / review gate (U2):** Does a **self-hosted, in-tenant** build (vs. a third-party vendor purchase) trigger the **LRA** and GRC/Privacy review? If so, what is the intake path?
3. **Authentication standard (F3/U3):** What does **IT05** concretely require for a service touching Sensitive data — NetID/Entra SSO + 2FA — and is a non-identity access key ever acceptable as a secondary gate?
4. **Audit retention (F2/DAT01):** What access-logging and retention does DAT01/FO-36 mandate for Sensitive-tier access?
5. **FERPA delegated access (U4):** With each operator using their own Canvas credentials and their own legitimate educational interest, is a separate school-official-by-contract designation required for the tooling, or is per-user delegation sufficient?

---

## 7. Methodology note

Verified findings (§2) passed multi-source adversarial verification against official institutional primary sources. Items in §3 come from primary `.illinois.edu` sources but were not independently confirmed in this pass (verifier rate-limiting), so they are surfaced as questions rather than conclusions. The roster of approved GenAI tools and the LRA workflow change over time — **re-confirm at decision time.**

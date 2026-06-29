# Canvas MCP — Security & FERPA Compliance Evaluation

**Status:** For review by UIUC Privacy Office / GRC and Cybersecurity. **Updated 2026-06-30** to reflect the now-live Entra platform authentication (the prior P0 identity gap is resolved).
**Scope:** The hosted HTTP MCP deployment (`canvas-mcp`, Illinois Azure App Service), recommended to staff/faculty for Canvas LMS workflows.
**Date:** 2026-06-30 (supersedes 2026-06-14 draft)
**Owner:** Vishal Sachdev (vishal@illinois.edu)
**Out of scope:** Canvas API token issuance/security (handled by a separate IT Services approval process).

---

## 1. What the system is

A self-hosted [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that lets an LLM client perform Canvas LMS tasks (grading, discussion facilitation, peer-review analytics, messaging) on behalf of an instructor or TA. Architecture as deployed/intended:

- **Compute:** Azure Web App for Containers, **inside the University of Illinois Azure subscription/tenant** (`urbana-business-disruptionlab`).
- **LLM (model layer — pluggable; see §1a):** the server is a **tool provider**, not a model host — the LLM that reasons over returned Canvas data lives in the **client**. The FERPA data boundary therefore depends on *which model the client uses*, governed by the tiered model in §1a. The hosted instance is deliberately **model-portable**: it can target whichever in-tenant or institutionally-licensed model campus approves (in-tenant Azure OpenAI, or the **Google Gemini-for-Education** path now under campus evaluation), and is **not** tied to consumer OpenAI/Anthropic APIs in its endorsed configurations.
- **Canvas access:** each caller sends **their own Canvas API token** (`X-Canvas-Token` header). The server holds **no** shared Canvas token; the Canvas API URL is server-pinned.
- **Endpoint gate (identity):** **Entra ID (Azure AD) platform authentication** via App Service Easy Auth in API/bearer mode (RFC 9728 Protected Resource Metadata + `401` challenge; MCP-native OAuth, **not** a browser redirect). Each caller authenticates with their **campus NetID + Duo 2FA**; the app trusts the `X-MS-CLIENT-PRINCIPAL-ID` claim Easy Auth injects. Access is further scoped to an explicit allowlist of authorized campus identity OIDs (`MCP_ENTRA_ALLOWED_OIDS`) as an interim defense-in-depth control. The prior shared static access key is **retired**.
- **Server-token guard:** `CANVAS_API_TOKEN` must never be set in HTTP mode — a startup guard fails closed if it is, ensuring there is no shared Canvas credential.
- **Transport:** TLS terminated at Azure (`httpsOnly=true`).
- **Code execution tool disabled** on the hosted image (`EXECUTE_TYPESCRIPT_ENABLED=false`).

---

## 1a. Deployment tiers (risk-graded model boundary)

The same codebase supports three deployment tiers that differ in **who owns the data-egress risk** and **what kind of FERPA boundary applies**. This lets IT/GRC map data sensitivity to a *minimum tier* rather than make one all-or-nothing decision.

| Tier | Deployment | Model layer | Boundary type | Risk owner | Suitable for |
|---|---|---|---|---|---|
| **1 — Local / BYO** | Local stdio MCP, user's own client | Whatever the user's client uses (may be consumer) | *None institutional* | **Individual** instructor/TA | Non-identifiable / anonymized work; individual responsibility — do **not** feed identifiable records to an unapproved model |
| **2 — Hosted + licensed model** | Hosted HTTP (Entra / NetID + Duo) | Institutionally-**licensed** SaaS model: ChatGPT EDU, Google Gemini for Education, (Claude Enterprise later) | **Contractual** — data egresses but under a FERPA-covering DPA/BAA | **Institution** (via vendor contract) | Identifiable student data, where contractual coverage is accepted |
| **3 — Hosted + in-tenant model** | Hosted HTTP (Entra / NetID + Duo) | **In-tenant** model via API key (Azure OpenAI in the UIUC subscription; campus-hosted Gemini) | **Technical** — student data never leaves the institutional cloud | **Institution** (fully in-boundary) | Identifiable student data; strongest posture |

**Boundary distinction:** Tier 2's boundary is a *signed contract* (data reaches the vendor but is contractually use-limited); Tier 3's is *technical* (data never leaves the tenant). Both are defensible; institutions that require a technical boundary should mandate Tier 3.

**Cross-cutting control:** the built-in **student-anonymization map** de-identifies analytical outputs, *lowering the tier required* for many tasks (e.g., grade-distribution analytics can run at Tier 1 because no identifiable record reaches the model).

**Client requirement (Tiers 2–3):** requires a client that supports remote MCP connectors — Claude.ai / ChatGPT connectors, or **model-agnostic desktop agents** (e.g., Cline, Continue) pointed at the approved model. The latter preserves desktop local-context and automation capability while keeping inference on the approved model.

**Determinations still owed by GRC / Privacy (see §6):** (a) confirm Tier 3's in-tenant Azure OpenAI deployment is designated for Sensitive data; (b) confirm which Tier 2 licenses (ChatGPT EDU / Gemini for Education / Claude Enterprise) carry FERPA coverage acceptable to the institution; (c) ratify the data-sensitivity → minimum-tier mapping. **"Safe" in this document means *compliant per these determinations*, not an independent assertion.** Note: the campus Gemini-LTI evaluation already establishes a precedent for an AI vendor processing Canvas data under an institutional agreement — its outcome may directly inform (a)/(b).

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
| Endpoint fails closed when auth unconfigured | ✅ Fixed 2026-06-14 | Startup guard refuses HTTP mode unless authentication is configured; `CANVAS_API_TOKEN` in HTTP mode is rejected |
| **Authentication = Entra ID (NetID + Duo 2FA) campus identity** | ✅ **Aligned (was P0 gap; resolved 2026-06-17)** | F3 — **IT05/FO-36 conformance.** Easy Auth bearer mode supplies a verified campus identity (`X-MS-CLIENT-PRINCIPAL-ID`) per request, giving individual attribution for the FERPA need-to-know determination. Replaces the retired shared static key. |
| Access logging / audit trail of who accessed which records | ⚠️ Partial | F2 expects auditable access + documented authorization basis per user |
| Documented business-need / authorization basis per operator | ⚠️ Partial | F2 — needs a recorded authorization basis per TA/instructor |

---

## 5. Prioritized gap list

- **P0 — Authentication identity.** ✅ **Resolved 2026-06-17.** The shared static access key was replaced with **NetID/Entra (Azure AD) SSO + Duo 2FA**, so each request now carries a verified campus identity — the IT05/FO-36 conformance requirement (F3) is met. Implemented as the **MCP-native OAuth flow with Entra ID** fronted by App Service Easy Auth in **API/bearer mode** (RFC 9728 PRM + `401` challenge, not a 302 browser redirect); the `AADSTS9010010` blocker was cleared by registering the custom-domain endpoint as an Entra App ID URI so the PRM `resource` matches.
  - *Rejected alternatives (for the record):* **campus VPN** and **Azure App Service IP restrictions** are network-layer only — no per-request identity/attribution. The one-click Easy Auth **browser-redirect** mode was unsuitable for non-browser MCP clients (302 to a login they can't follow); the shipped solution uses Easy Auth's **bearer/API mode** instead.
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

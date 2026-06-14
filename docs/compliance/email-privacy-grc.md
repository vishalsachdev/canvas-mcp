# Email — UIUC Privacy Office / GRC

**To:** privacy@illinois.edu (Privacy Office); GRC intake (confirm address)
**Cc:** —
**Subject:** FERPA/GenAI review request — in-tenant Canvas MCP tool (Azure OpenAI) for staff/faculty

Hello,

I'm a faculty member in Gies College of Business. I've built an internal tool that helps instructors and TAs do routine Canvas work (grading with rubrics, discussion facilitation, peer-review analytics, reminders) through an AI assistant, and before recommending it more broadly to staff and faculty I want to confirm it clears FERPA and our generative-AI data-handling requirements.

Architecture (kept deliberately inside the University boundary):

• Hosted on Azure **inside the University of Illinois subscription/tenant** (Disruption Lab subscription) — not a third-party SaaS.
• The AI model is the University's **in-tenant Azure OpenAI Service** (enterprise agreement, data not used for training) — not consumer ChatGPT/Claude.
• Each user authenticates to Canvas with **their own Canvas API token**; the server holds no shared instructor token, so every action runs under that person's own Canvas role and audit trail.
• TLS in transit; the code-execution feature is disabled on the hosted instance.

I understand Canvas student education records are classified as Sensitive data, requiring specific authorization and a documented need-to-know. My questions:

1. Is processing Sensitive-tier (FERPA) student data through the University's in-tenant Azure OpenAI Service permitted under current generative-AI guidance and the Microsoft enterprise agreement? Does it need a specific approved-tool designation or written data-handling assurance?

2. Does a self-hosted, in-tenant build like this (as opposed to purchasing a third-party product) trigger the Lightweight Risk Assessment and a GRC/Privacy review? If so, what's the right intake path and what should I submit?

3. With each operator using their own Canvas credentials under their own legitimate educational interest, is a separate FERPA "school official by contract" designation needed for the tooling itself, or is per-user delegation sufficient?

4. What access-logging and retention do you expect for a service that touches Sensitive-tier records?

I've written a short internal compliance evaluation that documents the controls and the open questions above, and I'm happy to send it or meet. I want to get this right before any wider rollout.

Thank you,
Vishal Sachdev
Clinical Professor / Director, Disruption Lab — Gies College of Business
vishal@illinois.edu

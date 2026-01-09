# Tier Compatibility Matrix (Template)

Use this matrix to map security requirements and tests to each tier. Update it with every release and reference it from release notes.

| Control / Requirement | Baseline | Public | Enterprise | Notes / Evidence |
| --- | --- | --- | --- | --- |
| Code execution sandbox | ✅ (best-effort limits + local fallback) | ✅ (best-effort + outbound allowlist guard) | ✅ (best-effort + allowlist guard; container recommended) | Guard enforced inside Node; container mode used when Docker/Podman available |
| MCP client authentication | ⚪ optional | ⚪ optional | ✅ required | Placeholder until auth feature lands; stdio transport does not enforce it |
| Token storage/validation | ⚪ optional | ✅ keyring/envelope + startup validation | ✅ external vault + startup validation | Ensure secrets backend configured per overlay |
| PII redaction/log rotation | ✅ redacted logs | ✅ redacted + rotation | ✅ redacted + rotation + retention | Verify log destinations align with policy |
| Access/audit logging | ⚪ advisory | ⚪ advisory | ✅ required | Enterprise artifact should emit to syslog/SIEM |
| Outbound network controls | ⚪ advisory | ✅ allowlist guard | ✅ allowlist guard | Allowlist guard is Node-level; external binaries are not blocked |
| Required CI gates | Lint + unit tests | Smoke bundle | Full suite + SAST + secrets + checklist | Map to GitHub Actions jobs per tier |

Legend: ✅ required, ⚪ optional/advisory.

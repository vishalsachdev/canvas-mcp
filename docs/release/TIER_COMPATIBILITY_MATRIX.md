# Tier Compatibility Matrix (Template)

Use this matrix to map security requirements and tests to each tier. Update it with every release and reference it from release notes.

| Control / Requirement | Baseline | Public | Enterprise | Notes / Evidence |
| --- | --- | --- | --- | --- |
| Code execution sandbox | ✅ (strict defaults) | ✅ (strict + no egress) | ✅ (strict + allowlist + audit) | Overlay vars: `ENABLE_TS_SANDBOX`, `TS_SANDBOX_BLOCK_OUTBOUND_NETWORK`, `TS_SANDBOX_ALLOWLIST_HOSTS` |
| MCP client authentication | ⚪ optional | ⚪ optional | ✅ required | Placeholder until auth feature lands; artifact must document mode |
| Token storage/validation | ⚪ optional | ✅ keyring/envelope + startup validation | ✅ external vault + startup validation | Ensure secrets backend configured per overlay |
| PII redaction/log rotation | ✅ redacted logs | ✅ redacted + rotation | ✅ redacted + rotation + retention | Verify log destinations align with policy |
| Access/audit logging | ⚪ advisory | ⚪ advisory | ✅ required | Enterprise artifact should emit to syslog/SIEM |
| Outbound network controls | ⚪ advisory | ✅ block all | ✅ allowlist only | Test via sandbox smoke/full suite |
| Required CI gates | Lint + unit tests | Smoke bundle | Full suite + SAST + secrets + checklist | Map to GitHub Actions jobs per tier |

Legend: ✅ required, ⚪ optional/advisory.

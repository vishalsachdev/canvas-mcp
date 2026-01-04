# Configuration Overlays (Baseline, Public, Enterprise)

These overlay files layer on top of the base `.env` to produce tiered builds without code forks. Apply one overlay per artifact or deployment.

## How to use
1. Copy `env.template` to `.env` (or your environment manager).
2. Append or override values from the overlay that matches your target tier.
3. Document the overlay hash and policy version in release notes to prevent drift.

Example:
```bash
cp env.template .env
cat config/overlays/public.env >> .env
```

## Tiers and defaults
- **Baseline (`config/overlays/baseline.env`)**: strict sandbox enabled, binds MCP to localhost, anonymization toggle preserved, logging redacted by default.
- **Public (`config/overlays/public.env`)**: baseline + no outbound network from code execution, token storage via keyring/envelope encryption, log redaction + rotation hints, optional localhost-only firewall note.
- **Enterprise (`config/overlays/enterprise.env`)**: baseline + authenticated MCP clients (API key/mTLS placeholders), centralized secret store hooks, outbound allowlist, audit/access logging destinations with retention periods, SIEM/syslog forwarding hints.

## Release gating pointers
- **Baseline**: lint + unit tests required; security scans advisory.
- **Public**: run smoke bundle (dependency scan, sandbox smoke test, token validation, log redaction check) before publishing.
- **Enterprise**: require full security suite, SAST, dependency + secret scanning, and checklist sign-off.

> NOTE: Some placeholders assume forthcoming implementations (e.g., sandbox flags, keyring support, client authentication). Keep the overlay files in sync with the features as they land.

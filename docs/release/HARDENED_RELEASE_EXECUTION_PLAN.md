# Hardened Release Execution Plan

This document operationalizes the baseline/public/enterprise tiering in `UIUC_SECURITY_EXECUTIVE_SUMMARY.md` into concrete work items, packaging steps, and release gates.

## Objectives
- Ship a single codebase with configuration overlays for **baseline**, **public**, and **enterprise** tiers.
- Gate each tier with the minimum viable security checks that match its risk profile.
- Produce repeatable artifacts and runbooks so releases do not drift from policy.

## Work Breakdown

### 1) Configuration overlays
Create tier-specific env overlays tracked in git and referenced by release automation.
- `config/overlays/baseline.env` — defaults for contributors/early adopters (strict sandbox on, localhost bind, anonymization toggle, redacted logging enabled).
- `config/overlays/public.env` — workstation-focused defaults (sandbox with no outbound egress, keyring/envelope token storage, log redaction + rotation hints, optional localhost-only firewall note in banner).
- `config/overlays/enterprise.env` — hardened defaults (MCP client auth token/mTLS placeholders, centralized secrets hooks, outbound allowlist, audit/access logging destinations with retention periods).
- Add `config/overlays/README.md` describing how to compose overlays with the base `.env` and what controls are enforced per tier.

### 2) Release gating
Implement minimal-but-strict gates per tier in CI (GitHub Actions):
- **Baseline**: lint + unit tests required; security scans advisory only.
- **Public**: must run "smoke" bundle: dependency scan, sandbox smoke test, token validation on startup, and log redaction check.
- **Enterprise**: must run full security suite (pytest `tests/security`), SAST (Bandit + Semgrep), dependency scanning, secret scanning, and checklist sign-off via required status check.

### 3) Artifacts and packaging
- Publish two artifacts per tag: `public` (baseline + public overlay) and `enterprise` (baseline + enterprise overlay).
- Include an **overlay hash** and **policy version** in release notes to detect drift.
- Document default profile baked into each artifact (sandbox mode, auth mode, logging destinations, retention period, egress policy).

### 4) Runbooks
Document operator actions by tier:
- **Baseline**: weekly dependency scan, manual sandbox bypass review, quarterly token rotation.
- **Public**: monthly smoke bundle, verify keyring/encryption at install, ship a generated "quick hardening" checklist (sandbox on, localhost bind, redacted logs, offline token storage).
- **Enterprise**: per-PR enforced security suite, quarterly IR exercise, biannual pen-test, SIEM/syslog shipping verification, automated token expiry monitoring.

### 5) Drift control and compatibility matrix
- Maintain a compatibility matrix mapping requirements/tests to tiers (must/optional). Update alongside releases.
- Add a "tier drift" checklist to release notes: overlay hash, policy version, gating jobs executed, manual sign-offs captured.

## Immediate next steps (actionable)
1. Add the three overlay env files and README to `config/overlays/` (tracked in git).
2. Create a GitHub Actions workflow stub with the three gates and job matrices keyed by tier.
3. Add a compatibility matrix template to `docs/release/` and reference it from release notes.
4. Update the executive summary to link to this execution plan and to the matrix once populated.

## Done criteria
- Overlays exist with documented defaults and are referenced by CI jobs and release packaging instructions.
- Release notes include tier drift checklist and overlay/policy hashes.
- Public artifact build runs smoke bundle by default; enterprise artifact build blocks without full suite + checklist sign-off.
- Operators have short runbooks per tier to keep deployments aligned with policy.

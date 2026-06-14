# Plan: Entra ID per-request identity for the hosted Canvas MCP server (MCP-native OAuth)

> Synthesized from two independent drafts (Claude + Codex Architect), which converged on the
> same architecture — so no further model-council was needed. Closes the **P0 authentication-identity
> gap** (and the P1 audit gap) in `docs/SECURITY-COMPLIANCE.md`. This is the roadmap's "Entra/OAuth v2".

## Problem

The hosted server (FastMCP streamable-http, Azure Web App for Containers, Illinois Azure tenant) gates the
endpoint with a **shared static access key** (`X-MCP-Access-Key`) plus each caller's `X-Canvas-Token`. The
shared key carries **no campus identity** → no per-request FERPA attribution and no IT05/FO-36-conformant
auth. Azure "Easy Auth" is unusable: its 302 browser-login redirect breaks non-browser MCP clients.

## Goal

Every request carries a **verified Entra ID (Azure AD) identity** (`oid`/NetID), validated server-side and
authorized against an allowlist — **without** dropping the per-user Canvas token model and **without**
breaking the ~4 current users or the range of MCP clients the team uses.

## Core design

Separate the two concerns the access key conflates:
- **Identity / endpoint authorization** → Entra OAuth **access token** (`Authorization: Bearer <JWT>`). New gate.
- **Canvas API credentials** → unchanged: caller still sends their own `X-Canvas-Token`.

A migrated request carries **both**. Middleware validates the Entra token, records the identity for audit,
then proceeds with the existing per-user Canvas flow. The MCP server becomes an **OAuth 2.1 Resource Server**
(MCP Authorization spec); **Entra is the Authorization Server**.

### Cross-client compatibility (hard requirement)

The **server design is client-agnostic** — a spec-compliant Resource Server. Client variance is absorbed by
the **`mcp-remote` stdio bridge**, the universal lowest-common-denominator (every MCP client supports stdio;
the bridge does the OAuth/PKCE and presents a local stdio server). Native remote-OAuth is used where it's
solid (Claude Desktop, Claude Code); the bridge covers everything else.

| Client | Path | Notes |
|---|---|---|
| Claude Desktop | Native connector **or** `mcp-remote` | Native OAuth works; bridge as fallback |
| Claude Code | Native (`claude mcp add --transport http`) **or** bridge | Native browser OAuth |
| Cursor | `mcp-remote` bridge | Native remote improving; bridge guaranteed |
| VS Code (Copilot/MCP) | Native HTTP-auth **or** bridge | Both viable |
| Codex CLI | **`mcp-remote` bridge** | Remote-OAuth support most uncertain → bridge |
| Windsurf / Zed / Continue | `mcp-remote` bridge | Universal stdio fallback |

**Enabling rule:** implement Protected Resource Metadata (`/.well-known/oauth-protected-resource`) + a
`401 WWW-Authenticate: Bearer resource_metadata=...` challenge for discovery, **and** support static client/
metadata config (Entra is not an open dynamic-registration server, so clients/bridges must be pre-configured).

## UIUC-tenant prior art (lab learned this live — `agent-infra/azure-deployment.md`)

The Disruption Lab already ran Entra auth in this exact subscription (uniquick/illinihunt, 2026-06). Tenant
facts that **will** hit canvas-mcp and reshape the admin story:
- **App registration is self-serve** — the team already creates registrations (uniquick did). NOT gated on an admin.
- **Custom API scopes hit a "Need admin approval" wall.** Only Microsoft low-impact Graph scopes
  (openid/profile/email/User.Read) are user-consentable. **Escape hatch:** since we register *both* the API and
  the client app, **pre-authorize our client on the API scope** (`api.preAuthorizedApplications` via Graph
  PATCH) → no admin consent needed.
- **Clients must request the named GUID scope `<clientId>/access_as_user`.** The `api://<id>/…` form trips
  `AADSTS90009`; `/.default` *ignores* `preAuthorizedApplications` and re-triggers the consent wall. ← highest-risk detail.
- **`az ad app create` does not create the service principal** (`az ad sp create --id <appId>` needed); add the
  app's own scope to `requiredResourceAccess` (else `AADSTS650057`); set `spa`/`api` via `az rest` Graph PATCH,
  not `az ad app update` (fails "Couldn't find 'spa'").
- **Adam King = subscription Owner** → an *easy* ask for anything in **subscription RBAC** (managed-identity role
  grants, AcrPull). Note this is a *different* authority than Entra admin-consent — but the pre-auth escape hatch
  means we likely **don't need an Entra admin at all**. Adjacent win: this also unblocks retiring the ACR
  admin-user workaround (grant the MI `AcrPull`).

## Phases

### Phase 0 — De-risk before building (Short, 1–4h) — GATING
> The scope-config question (was the #1 risk) is **already answered**: `mcp-remote@0.1.38` emits the named GUID
> scope verbatim and supports a static client (see R1). Phase 0 now validates the *live* end-to-end + clients.
1. **Live end-to-end run.** Stand up a throwaway API + client app reg, pre-authorize the client, register the
   `http://localhost:3334/oauth/callback` redirect, set the client as public (PKCE + `none`), and run the real
   flow through `mcp-remote` with `--static-oauth-client-metadata '{"scope":"<clientId>/access_as_user"}'` →
   confirm a bearer reaches a test server (needs interactive `az login` + a browser Duo round-trip).
2. **Cross-client check.** Confirm each **target client** (Claude Desktop, Claude Code, Codex CLI, VS Code,
   Cursor) can drive `mcp-remote` against the staging endpoint. Document the supported path per client (default:
   the bridge with our pre-authorized client app).

### Phase 1 — Entra app registrations (Short, self-serve — NOT admin-gated)
- **`Canvas MCP API`** (resource server): expose scope `CanvasMcp.Access`, audience `api://<api-app-id>`,
  single-tenant, v2 access tokens. Define an **app role or security group** = the operator allowlist.
  Gotchas: `az ad sp create --id <appId>` after create; add own scope to `requiredResourceAccess`; set `api`/`spa`
  via `az rest` Graph PATCH on `/applications/<objectId>` (not `az ad app update`).
- **`Canvas MCP Desktop Client`** (public/native client for `mcp-remote`): **localhost loopback redirect URIs**
  (Entra permits localhost HTTP and ignores the port).
- **Pre-authorize the client on the API scope** (`api.preAuthorizedApplications` via Graph PATCH) → sidesteps the
  custom-scope admin-consent wall; no Entra admin needed.

### Phase 2 — OAuth Resource Server in FastMCP (Medium, 1–2d)
- Serve **Protected Resource Metadata** pointing to the Entra authorization server (issuer, JWKS, scopes).
- Return **401 `WWW-Authenticate: Bearer resource_metadata=...`** on unauthenticated requests (discovery).
- Add an **Entra token verifier** ahead of Canvas work — reject unless ALL pass:
  signature (Entra JWKS, cached + refresh-on-unknown-kid) · `iss` = Illinois issuer · `tid` = tenant ·
  `aud` = `api://<api-app-id>` · not expired/early · `scp` contains `CanvasMcp.Access` ·
  `azp`/client-app-id ∈ approved MCP clients · `oid` ∈ allowlist. **Validate access tokens, not ID tokens.**
- **Authorize by `oid`** (object ID — stable); use UPN/NetID for display only (UPNs change).
- Keep `X-Canvas-Token` extraction unchanged after the identity gate.

### Phase 3 — Dual-mode migration, then retire the key (Short, 1–4h)
- Add `MCP_AUTH_MODE = access_key | entra | dual` (+ `ENTRA_TENANT_ID`, `ENTRA_AUTHORITY`, `ENTRA_AUDIENCE`,
  `ENTRA_REQUIRED_SCOPE`, allowlist, `MCP_PUBLIC_BASE_URL`). Extend the **fail-closed startup guard**: HTTP mode
  exits unless valid Entra config **or** the legacy key gate is deliberately enabled for migration.
- Deploy in `dual` (accept key OR Entra). Onboard the 4 users to the new client config one at a time while
  their key still works. When all confirm, remove their keys and switch to `entra`.

### Phase 4 — Identity-attributed audit logging (Quick–Short)
- Record per request: `tid`, `oid`, NetID/UPN, display name, client app id, scope, auth method — alongside the
  existing sanitized Canvas endpoint + outcome. **Never log Entra or Canvas tokens.** Closes the P1 audit gap.

### Phase 5 — Tests + staging cutover (Medium)
- Tests: missing bearer · bad signature · wrong tenant · wrong audience · missing scope · non-allowlisted user ·
  valid Entra+Canvas · dual-mode key fallback · audit identity fields.
- Real staging run with `mcp-remote` + each target client before production cutover.

## Risks & mitigations
- **R1 — RESOLVED (was highest): named GUID scope.** Confirmed `mcp-remote@0.1.38` writes the scope **verbatim**
  to `/authorize` (no `.default` injection, no `api://` rewrite) — set it via `--static-oauth-client-metadata
  '{"scope":"<clientId>/access_as_user"}'`. It also supports a **static pre-registered client**
  (`--static-oauth-client-info '{"client_id":"<GUID>"}'`) so dynamic registration is never attempted. So the
  consent-free pre-authorization design is viable; no admin consent fallback needed. *(Source-verified against
  the bundled dist; corroborated by Microsoft's own MCP+Entra pre-authorized-client guidance — see References.)*
- **R1a (new, app-config): localhost redirect URI must be registered.** `mcp-remote`'s callback defaults to
  `http://localhost:3334/oauth/callback` (port = positional arg, host = `--host`). Register that exact URI as a
  public/native redirect on the client app. → Validate in the Phase 0 live run.
- **R1b (new, app-config): client must be a public client (PKCE + `none`).** `mcp-remote` always uses PKCE and
  `token_endpoint_auth_method: none`, so the Entra client app must be configured as public/native allowing those.
- **R2: a target client can't do the flow.** → Fall back to `mcp-remote` (covers all stdio-capable clients);
  keep the access key short-term if a client genuinely can't.
- **R3 (de-risked): app-registration / admin access.** The team **self-registers** apps in this tenant already
  (uniquick prior art); the only admin-flavored step (custom-scope consent) is sidestepped by pre-authorization,
  and Adam (subscription Owner) is an *easy* ask for any RBAC piece (incl. the AcrPull retirement). No long pole.
- **R4: wrong-audience token accepted.** → Strict `aud`/`tid`/`iss`/`scp`/`azp` checks; access tokens only.
- **R5: Canvas-token vs Entra-identity mismatch** (user presents someone else's Canvas token). → Audit both
  identities; consider enforcing a NetID/email match once Canvas self-identity format is confirmed reliable.
- **R6: allowlist drift (UPN changes).** → Authorize by `oid`, not UPN.
- **R7: JWKS rotation / metadata fetch failure.** → Cache keys, refresh on unknown kid, **fail closed**.

## Effort: **Medium** (~2–4 engineering days of code). App registration is self-serve (no admin lead time);
the only external dependency is the optional AcrPull grant from Adam, which is unrelated to the OAuth build.

## Reference client config (verified — `mcp-remote@0.1.38`)

```jsonc
// any MCP client config (Claude Desktop/Code, Codex, VS Code, Cursor) — universal bridge path
{
  "mcpServers": {
    "canvas": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://gies-canvas-mcp-staging.azurewebsites.net/mcp",
        "--static-oauth-client-info", "{\"client_id\":\"<CLIENT_GUID>\"}",
        "--static-oauth-client-metadata", "{\"scope\":\"<CLIENT_GUID>/access_as_user\"}"
      ]
    }
  }
}
```
Plus each user still supplies their own Canvas token (header passthrough, as today). Use `@/path.json` file form
to keep the GUID out of the config if preferred.

## References
- Microsoft — Building MCP servers with Entra ID and pre-authorized clients:
  https://techcommunity.microsoft.com/blog/azuredevcommunityblog/building-mcp-servers-with-entra-id-and-pre-authorized-clients/4508453
- Microsoft Learn — Secure MCP servers with Microsoft Entra authentication (Azure App Service):
  https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-mcp-server-vscode
- `mcp-remote` flags: https://www.npmjs.com/package/mcp-remote (`--static-oauth-client-info`,
  `--static-oauth-client-metadata`, `--header`, `--host`)

## Non-goals
- Not replacing the per-user Canvas token (Entra ≠ Canvas creds).
- Not Easy Auth (302 breaks MCP clients). Not VPN / IP restrictions as the identity solution (network-layer
  only; optional defense-in-depth at most).

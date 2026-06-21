# Research spec (handoff): Does Azure App Service native Entra auth validate the MCP bearer token for us?

**Type:** Focused technical decision to unblock building — **NOT a project plan.** Return build-ready guidance.
**Owner asking:** canvas-mcp / Entra-OAuth work (see `.claude/plans/entra-oauth-mcp-auth.md`).

## The decision this must resolve (one thing)

We are implementing Entra ID per-request identity for a hosted Python MCP server. Our default is to build the
OAuth **Resource Server** (JWT-validation middleware) ourselves in FastMCP. Microsoft recently published guidance
on securing MCP servers with Entra on **Azure App Service**. **Decide:** can App Service's *platform* auth
validate the incoming Entra access token for us (so our app only reads a verified-identity header), **or** must we
validate the JWT in-app? This determines whether we write the full token-validation middleware or a thin
header-reader. Answer it; don't re-plan around it.

## Context (self-contained — assume no prior knowledge)

- **App:** `canvas-mcp`, Python **FastMCP** server, transport `streamable-http` (ASGI/Starlette), containerized on
  **Azure Web App for Containers**, inside the University of Illinois Azure tenant. Touches FERPA student data.
- **Current auth:** an ASGI middleware (`CanvasCredentialMiddleware` in `src/canvas_mcp/server.py`) reads
  `X-MCP-Access-Key` (a shared static key) + `X-Canvas-Token` (each caller's own Canvas token). Goal: replace the
  shared key with a **verified Entra identity per request**; **keep the `X-Canvas-Token` per-user model unchanged.**
- **Clients** connect via the `mcp-remote` stdio bridge (some native), configured as a **pre-registered public
  Entra client** requesting the **named GUID scope `<clientId>/access_as_user`** (already verified working with
  `mcp-remote@0.1.38` via `--static-oauth-client-metadata`). The MCP server is the **Resource Server**; Entra is
  the IdP. Pre-authorization (`api.preAuthorizedApplications`) is used to avoid the custom-scope admin-consent wall.
- **HARD CONSTRAINT from prior failure:** the classic App Service **"Easy Auth" that 302-redirects** unauthenticated
  requests to a browser login **BREAKS non-browser MCP clients.** Any solution MUST return a **401 + bearer
  challenge** (RFC 9728 `WWW-Authenticate`), never a 302 redirect.

## Questions to answer

1. In Microsoft's "Secure MCP servers with Microsoft Entra authentication (Azure App Service)" configuration, does
   App Service **validate the Entra bearer token at the platform layer** and pass identity to the app (e.g. via
   `X-MS-CLIENT-PRINCIPAL` / `X-MS-TOKEN-*` headers), or does the app still validate the JWT itself?
2. Can App Service built-in auth be set to a **bearer/API mode that returns 401, not 302**, for missing/invalid
   tokens? Identify the exact setting (`unauthenticatedClientAction = Return401` vs `RedirectToLoginPage`; token
   validation config; whether it emits/permits the RFC 9728 protected-resource-metadata + `WWW-Authenticate`
   challenge MCP clients expect).
3. **If yes (platform validates + 401):** what exactly does the app receive — which headers, and are `oid`, `scp`,
   `azp` available for our allowlist + audit logging? What is the **minimal app-side code** (read header →
   authorize against allowlist → log identity → fail closed)?
4. **If no:** say so plainly; then the app validates the JWT itself (signature via Entra JWKS, `iss`, `aud`, `tid`,
   `scp`, `azp`, exp). Confirm there's no platform shortcut and we proceed with in-app middleware.
5. Either way: does enabling App Service auth **interfere** with (a) the MCP `streamable-http` transport, (b) the
   `/.well-known/oauth-protected-resource` discovery doc the app would serve, or (c) the validated `mcp-remote`
   pre-authorized-client + named-GUID-scope flow? Flag any conflict.

## Required output (build-ready)

- **DECISION (one line):** "Use App Service platform validation (thin header-reader)" OR "Validate in-app (build
  the middleware)".
- **Concrete config** to apply for the chosen path: `az` CLI / portal settings / auth config JSON / app settings.
- **Minimal app-side code delta** for the existing ASGI middleware: which header/claims to read, how to fail closed
  with 401 + `WWW-Authenticate` (pseudocode is fine, but specific).
- **Settings to AVOID** (e.g. the redirect mode that breaks MCP clients).
- **Verification checklist:** `curl` with no token → expect 401 (not 302); `curl` with valid bearer → 200; identity
  header/claim present.
- **Citations:** official Microsoft docs with URLs + dates/versions. Flag anything uncertain that needs a live
  spike, but keep proposed spikes minimal.

## MUST NOT
- Do not propose browser-redirect (Easy Auth `RedirectToLoginPage`) as the solution.
- Do not propose replacing the per-user `X-Canvas-Token`.
- Do not write a phased project plan — this is a single technical decision to unblock building.

## Starting sources
- https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-mcp-server-vscode
- https://techcommunity.microsoft.com/blog/azuredevcommunityblog/building-mcp-servers-with-entra-id-and-pre-authorized-clients/4508453
- App Service auth concepts (search Microsoft Learn): `unauthenticatedClientAction`, token store,
  `X-MS-CLIENT-PRINCIPAL` headers, "API/SPA" vs "web app" auth mode.
- Repo (read for the integration point): `src/canvas_mcp/server.py` (`CanvasCredentialMiddleware`),
  `src/canvas_mcp/core/config.py`, `src/canvas_mcp/core/credentials.py`.

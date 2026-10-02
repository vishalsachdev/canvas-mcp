# ChatGPT access through OAuth/OIDC

This deployment protects the public Streamable HTTP MCP endpoint with OAuth
2.1. It is separate from Canvas OAuth: the upstream OIDC provider determines
who may use the MCP server, while the Canvas refresh token lets the server call
Canvas after a user has been accepted.

## 1. Register the MCP server with an OIDC provider

Use an established OIDC provider (for example Auth0, Entra ID, Keycloak, or
Authentik). Register a confidential web client whose redirect URI is exactly:

```
https://canvas-lms-mcp-server.francoisdisubi.com/auth/callback
```

Restrict access at the provider to the intended people or group. Do not use a
Canvas API access token as the MCP client credential.

## 2. Configure the server

Set these values in the server's protected `.env` file:

```
MCP_AUTH_MODE=oidc
MCP_PUBLIC_URL=https://canvas-lms-mcp-server.francoisdisubi.com
MCP_OIDC_CONFIG_URL=https://YOUR-IDP/.well-known/openid-configuration
MCP_OIDC_CLIENT_ID=...
MCP_OIDC_CLIENT_SECRET=...
MCP_OIDC_JWT_SIGNING_KEY=... # independent, high-entropy secret
MCP_OIDC_ALLOWED_CLIENT_REDIRECT_URIS=https://chatgpt.com/connector_platform_oauth_redirect,https://chatgpt.com/connector/oauth/*,http://localhost:*,http://127.0.0.1:*
```

FastMCP publishes the protected-resource metadata, authorization endpoints,
token endpoint, and dynamic-client-registration endpoint. The two loopback
patterns allow an OAuth-capable local MCP client such as Claude Code to receive
its browser callback without permitting arbitrary public redirects. Do not
block those routes in Caddy.

## 3. Caddy

Remove the IP allowlist, static `Authorization` check, and the rule returning
404 for OAuth discovery. Let FastMCP receive the entire public endpoint:

```caddyfile
canvas-lms-mcp-server.francoisdisubi.com {
	reverse_proxy 127.0.0.1:8000 {
		header_up Host {upstream_hostport}
	}
}
```

The MCP URL to enter in ChatGPT is:

```
https://canvas-lms-mcp-server.francoisdisubi.com/mcp
```

## Canvas token refresh

`CANVAS_REFRESH_TOKEN`, `CANVAS_CLIENT_SECRET`, and the resulting Canvas
access token remain server-side. The server refreshes only its global Canvas
credential after a Canvas 401 challenge. It deliberately never refreshes a
token supplied through `X-Canvas-Token`, because doing so could make one HTTP
caller execute requests as the server's Canvas account.

This configuration is for a single server-side Canvas identity. A deployment
where every ChatGPT user needs their own Canvas identity requires an encrypted
per-user token store keyed by the OIDC subject; do not use the global refresh
token for that model.

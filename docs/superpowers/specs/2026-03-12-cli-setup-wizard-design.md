# Canvas MCP CLI Setup Wizard

**Date:** 2026-03-12
**Status:** Approved
**Target:** Workshop on 2026-03-13, Codex CLI as primary client

## Problem

Installing Canvas MCP requires 5+ manual steps: install Python, pip install, find your MCP client's config file, paste JSON, set environment variables. This friction is especially painful for students in workshop settings.

## Solution

An npm package (`canvas-mcp`) providing `npx canvas-mcp setup` — an interactive wizard that configures any supported MCP client to use the hosted Canvas MCP server at `mcp.illinihunt.org`. No Python required for the default path.

## User Flow

```
$ npx canvas-mcp setup

Canvas MCP Setup

? Enter your Canvas API token: ********
? Enter your Canvas URL: https://canvas.illinois.edu
? Which client(s)? (space to select)
    Codex CLI
    Claude Desktop
    Cursor
    Windsurf
    VS Code (Copilot)
    Claude Code

Done! Configured Codex CLI (~/.codex/config.toml)
Server: https://mcp.illinihunt.org/mcp

Restart Codex to activate. Test with: "What courses am I enrolled in?"
```

## Supported Clients

### Codex CLI (primary target)
- **Config file:** `~/.codex/config.toml`
- **Format:** TOML
- **Server type:** Streamable HTTP with custom headers

```toml
[mcp_servers.canvas-mcp]
url = "https://mcp.illinihunt.org/mcp"

[mcp_servers.canvas-mcp.env_http_headers]
X-Canvas-Token = "CANVAS_API_TOKEN"

[mcp_servers.canvas-mcp.http_headers]
X-Canvas-URL = "https://canvas.illinois.edu"
```

The wizard writes the token to a `.env` file or shell profile (`export CANVAS_API_TOKEN=...`) and references it by variable name in `env_http_headers`. The Canvas URL is non-sensitive and stored as a literal header.

### Claude Desktop
- **Config file:** `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), `%APPDATA%\Claude\claude_desktop_config.json` (Windows)
- **Format:** JSON, `mcpServers` wrapper
- **Server type:** Streamable HTTP via url field

```json
{
  "mcpServers": {
    "canvas-mcp": {
      "url": "https://mcp.illinihunt.org/mcp",
      "headers": {
        "X-Canvas-Token": "<token>",
        "X-Canvas-URL": "https://canvas.illinois.edu"
      }
    }
  }
}
```

### Cursor
- **Config file:** `~/.cursor/mcp.json` (global)
- **Format:** JSON, `mcpServers` wrapper (same as Claude Desktop)

```json
{
  "mcpServers": {
    "canvas-mcp": {
      "url": "https://mcp.illinihunt.org/mcp",
      "headers": {
        "X-Canvas-Token": "<token>",
        "X-Canvas-URL": "https://canvas.illinois.edu"
      }
    }
  }
}
```

### Windsurf
- **Config file:** `~/.codeium/windsurf/mcp_config.json`
- **Format:** JSON, `mcpServers` wrapper (same structure as Claude Desktop)

### VS Code (Copilot)
- **Config file:** `~/Library/Application Support/Code/User/mcp.json` (macOS)
- **Format:** JSON, `servers` wrapper (not `mcpServers`)

```json
{
  "servers": {
    "canvas-mcp": {
      "url": "https://mcp.illinihunt.org/mcp",
      "headers": {
        "X-Canvas-Token": "<token>",
        "X-Canvas-URL": "https://canvas.illinois.edu"
      }
    }
  }
}
```

### Claude Code
- **Config file:** `~/.claude.json`
- **Format:** JSON, `mcpServers` wrapper
- **Server type:** Same wrapper as Claude Desktop

## Architecture

```
canvas-mcp/              (npm package)
├── bin/cli.js            # Entry point, arg parsing
├── lib/
│   ├── wizard.js         # Interactive prompts (token, URL, client selection)
│   ├── clients/
│   │   ├── codex.js      # TOML config writer
│   │   ├── claude-desktop.js
│   │   ├── cursor.js
│   │   ├── windsurf.js
│   │   ├── vscode.js
│   │   └── claude-code.js
│   └── utils.js          # Config file read/merge/write, path resolution
└── package.json
```

### Dependencies
- `prompts` — lightweight interactive CLI prompts (~5KB)
- `@iarna/toml` — TOML parser/serializer for Codex config

No other dependencies. Total package should be <50KB.

### Config File Strategy

For each client:
1. **Back up** existing config file to `<filename>.bak` before any modification
2. **Read** existing config file (if it exists)
3. **Merge** the canvas-mcp server entry (preserve other servers)
4. **Write** back the complete config (2-space indent, preserve key ordering)
5. **Never overwrite** existing canvas-mcp entries without confirmation

Special case: `~/.claude.json` (Claude Code) is large and complex. Parse/serialize carefully, preserve all existing data.

### Platform Detection
- macOS: `process.platform === 'darwin'`
- Windows: `process.platform === 'win32'`
- Linux: `process.platform === 'linux'`

Linux paths differ from macOS for some clients:
- Claude Desktop: `~/.config/Claude/claude_desktop_config.json`
- VS Code: `~/.config/Code/User/mcp.json`

Workshop target is macOS; Linux/Windows paths are best-effort for v1.

## npm Package Details

- **Name:** `canvas-mcp` (unclaimed on npm as of 2026-03-12)
- **Binary:** `canvas-mcp` (via `bin` field in package.json)
- **Usage:** `npx canvas-mcp setup`
- **Additional command:** `npx canvas-mcp auth` (design TBD for v2 — update token/URL across previously configured clients)
- **Version:** Start at 1.0.0

## Validation

After writing config, the wizard:
1. Confirms which file was written and its path
2. Tells the user to restart their client
3. Suggests a test prompt: "What courses am I enrolled in?"

No automated server health check on setup (keep it simple for v1).

## Security Considerations

- Canvas API tokens are written directly into config files (this is how all MCP clients work today)
- Tokens are sent over HTTPS to the hosted server via headers
- The wizard does NOT validate tokens against Canvas (would require network call and slow down setup)
- File permissions: config files inherit user's default umask

## Out of Scope (v1)

- Local server installation (`uvx canvas-mcp-server` option)
- Token validation during setup
- Automatic client restart
- Uninstall / remove config command
- CI/CD or non-interactive mode

## Success Criteria

1. `npx canvas-mcp setup` works on macOS with Codex CLI in under 30 seconds
2. After setup + Codex restart, "What courses am I enrolled in?" returns real course data
3. Workshop participants can self-serve without manual config file editing

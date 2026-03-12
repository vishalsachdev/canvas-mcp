# canvas-mcp

Setup wizard for [Canvas MCP](https://github.com/vishalsachdev/canvas-mcp) — configure any AI coding client to use Canvas LMS tools in one command.

## Quick Start

```bash
npx canvas-mcp setup
```

The wizard will:
1. Ask for your Canvas API token and URL
2. Let you pick which client(s) to configure
3. Write the correct config file for each client

No Python required — uses the hosted Canvas MCP server.

## Supported Clients

- **Codex CLI** — writes `~/.codex/config.toml`
- **Claude Desktop** — writes `claude_desktop_config.json`
- **Cursor** — writes `~/.cursor/mcp.json`
- **Windsurf** — writes `~/.codeium/windsurf/mcp_config.json`
- **VS Code (Copilot)** — writes VS Code `mcp.json`
- **Claude Code** — writes `~/.claude.json`

## What You Need

- A Canvas LMS account with an API token ([how to get one](https://community.canvaslms.com/t5/Admin-Guide/How-do-I-manage-API-access-tokens-as-an-admin/ta-p/89))
- Node.js 18+

## After Setup

Restart your client and try: **"What courses am I enrolled in?"**

## Learn More

- [Canvas MCP on GitHub](https://github.com/vishalsachdev/canvas-mcp) — 91 tools for students and educators
- [Canvas MCP on PyPI](https://pypi.org/project/canvas-mcp/) — for local installation

## License

MIT

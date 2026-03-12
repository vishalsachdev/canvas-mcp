import { homedir } from "node:os";
import { join } from "node:path";

const home = homedir();

const clients = [
  {
    id: "codex",
    name: "Codex CLI",
    format: "toml",
    configPath: () => join(home, ".codex", "config.toml"),
  },
  {
    id: "claude-desktop",
    name: "Claude Desktop",
    format: "json",
    wrapperKey: "mcpServers",
    configPath: () => {
      if (process.platform === "win32")
        return join(process.env.APPDATA || "", "Claude", "claude_desktop_config.json");
      if (process.platform === "linux")
        return join(home, ".config", "Claude", "claude_desktop_config.json");
      return join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json");
    },
  },
  {
    id: "cursor",
    name: "Cursor",
    format: "json",
    wrapperKey: "mcpServers",
    configPath: () => join(home, ".cursor", "mcp.json"),
  },
  {
    id: "windsurf",
    name: "Windsurf",
    format: "json",
    wrapperKey: "mcpServers",
    configPath: () => join(home, ".codeium", "windsurf", "mcp_config.json"),
  },
  {
    id: "vscode",
    name: "VS Code (Copilot)",
    format: "json",
    wrapperKey: "servers",
    configPath: () => {
      if (process.platform === "win32")
        return join(process.env.APPDATA || "", "Code", "User", "mcp.json");
      if (process.platform === "linux")
        return join(home, ".config", "Code", "User", "mcp.json");
      return join(home, "Library", "Application Support", "Code", "User", "mcp.json");
    },
  },
  {
    id: "claude-code",
    name: "Claude Code",
    format: "json",
    wrapperKey: "mcpServers",
    configPath: () => join(home, ".claude.json"),
  },
];

export { clients };

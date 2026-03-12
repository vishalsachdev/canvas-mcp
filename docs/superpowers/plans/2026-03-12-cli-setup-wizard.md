# Canvas MCP CLI Setup Wizard — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `npx canvas-mcp setup` — an interactive CLI that configures MCP clients to use the hosted Canvas MCP server. Primary target: Codex CLI for workshop on 2026-03-13.

**Architecture:** Thin npm package in `cli/` subdirectory. Interactive wizard prompts for token + URL + client selection, then writes the correct config file for each selected client. Codex uses TOML; all others use JSON with varying wrapper keys and paths.

**Tech Stack:** Node.js, `prompts` (interactive CLI), `@iarna/toml` (TOML read/write)

**Spec:** `docs/superpowers/specs/2026-03-12-cli-setup-wizard-design.md`

---

## File Structure

```
cli/                          # npm package root
├── package.json              # name: "canvas-mcp", bin: "canvas-mcp"
├── bin/cli.js                # Entry point — arg parsing, routes to setup command
├── lib/
│   ├── wizard.js             # Interactive prompts: token, URL, client multi-select
│   ├── config-writer.js      # Read/backup/merge/write logic for JSON and TOML configs
│   └── clients.js            # Client registry: name, config path, format, wrapper key
├── test/
│   ├── config-writer.test.js # Unit tests for merge/write logic
│   └── clients.test.js       # Unit tests for path resolution and client registry
├── .gitignore
└── README.md
```

**Design decisions:**
- Single `clients.js` registry instead of one file per client — the only difference between JSON clients is path + wrapper key. No need for 6 files.
- `config-writer.js` handles both JSON and TOML — the backup/read/merge/write flow is shared.
- Tests focus on config writing (the risky part), not interactive prompts.

---

## Chunk 1: Scaffold and Core Logic

### Task 1: Initialize npm package

**Files:**
- Create: `cli/package.json`
- Create: `cli/.gitignore`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "canvas-mcp",
  "version": "1.0.0",
  "description": "Setup wizard for Canvas MCP — configure any AI coding client in one command",
  "bin": {
    "canvas-mcp": "./bin/cli.js"
  },
  "files": ["bin/", "lib/"],
  "keywords": ["canvas", "lms", "mcp", "education", "claude", "codex", "cursor"],
  "author": "Vishal Sachdev <vsachde2@illinois.edu>",
  "license": "MIT",
  "repository": {
    "type": "git",
    "url": "https://github.com/vishalsachdev/canvas-mcp",
    "directory": "cli"
  },
  "dependencies": {
    "prompts": "^2.4.2",
    "@iarna/toml": "^2.2.5"
  },
  "devDependencies": {
    "node:test": "*"
  },
  "engines": {
    "node": ">=18"
  }
}
```

- [ ] **Step 2: Create .gitignore**

```
node_modules/
```

- [ ] **Step 3: Install dependencies**

Run: `cd cli && npm install`
Expected: `node_modules/` created, `package-lock.json` generated

- [ ] **Step 4: Commit**

```bash
git add cli/package.json cli/package-lock.json cli/.gitignore
git commit -m "feat(cli): scaffold npm package for canvas-mcp setup wizard"
```

---

### Task 2: Client registry

**Files:**
- Create: `cli/lib/clients.js`

This is the data layer — maps each MCP client to its config file path, format, and wrapper key.

- [ ] **Step 1: Write client registry**

```javascript
import { homedir } from "node:os";
import { join } from "node:path";

const home = homedir();

const clients = [
  {
    id: "codex",
    name: "Codex CLI",
    format: "toml",
    configPath: () => {
      if (process.platform === "win32") return join(home, ".codex", "config.toml");
      return join(home, ".codex", "config.toml");
    },
  },
  {
    id: "claude-desktop",
    name: "Claude Desktop",
    format: "json",
    wrapperKey: "mcpServers",
    configPath: () => {
      if (process.platform === "win32") return join(process.env.APPDATA || "", "Claude", "claude_desktop_config.json");
      if (process.platform === "linux") return join(home, ".config", "Claude", "claude_desktop_config.json");
      return join(home, "Library", "Application Support", "Claude", "claude_desktop_config.json");
    },
  },
  {
    id: "cursor",
    name: "Cursor",
    format: "json",
    wrapperKey: "mcpServers",
    configPath: () => {
      if (process.platform === "win32") return join(home, ".cursor", "mcp.json");
      return join(home, ".cursor", "mcp.json");
    },
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
      if (process.platform === "win32") return join(process.env.APPDATA || "", "Code", "User", "mcp.json");
      if (process.platform === "linux") return join(home, ".config", "Code", "User", "mcp.json");
      return join(home, "Library", "Application Support", "Code", "User", "mcp.json");
    },
  },
  {
    id: "claude-code",
    name: "Claude Code",
    format: "json",
    wrapperKey: "mcpServers",
    configPath: () => {
      if (process.platform === "win32") return join(home, ".claude.json");
      return join(home, ".claude.json");
    },
  },
];

export { clients };
```

- [ ] **Step 2: Commit**

```bash
git add cli/lib/clients.js
git commit -m "feat(cli): add client registry with paths for 6 MCP clients"
```

---

### Task 3: Config writer (core logic)

**Files:**
- Create: `cli/lib/config-writer.js`

Handles read/backup/merge/write for both JSON and TOML. This is the riskiest code — must preserve existing config.

- [ ] **Step 1: Write config-writer.js**

```javascript
import { readFileSync, writeFileSync, copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import TOML from "@iarna/toml";

const HOSTED_URL = "https://mcp.illinihunt.org/mcp";

function backup(filePath) {
  if (existsSync(filePath)) {
    copyFileSync(filePath, filePath + ".bak");
  }
}

function ensureDir(filePath) {
  const dir = dirname(filePath);
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true });
  }
}

function readJson(filePath) {
  if (!existsSync(filePath)) return {};
  return JSON.parse(readFileSync(filePath, "utf-8"));
}

function readToml(filePath) {
  if (!existsSync(filePath)) return {};
  return TOML.parse(readFileSync(filePath, "utf-8"));
}

function writeJson(filePath, data) {
  ensureDir(filePath);
  writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n", "utf-8");
}

function writeToml(filePath, data) {
  ensureDir(filePath);
  writeFileSync(filePath, TOML.stringify(data), "utf-8");
}

function configureJsonClient(client, token, canvasUrl) {
  const filePath = client.configPath();
  backup(filePath);

  const config = readJson(filePath);
  const wrapper = client.wrapperKey;

  if (!config[wrapper]) config[wrapper] = {};

  config[wrapper]["canvas-mcp"] = {
    url: HOSTED_URL,
    headers: {
      "X-Canvas-Token": token,
      "X-Canvas-URL": canvasUrl,
    },
  };

  writeJson(filePath, config);
  return filePath;
}

function configureCodexClient(client, token, canvasUrl) {
  const filePath = client.configPath();
  backup(filePath);

  const config = readToml(filePath);

  if (!config.mcp_servers) config.mcp_servers = {};

  config.mcp_servers["canvas-mcp"] = {
    url: HOSTED_URL,
    env_http_headers: { "X-Canvas-Token": "CANVAS_API_TOKEN" },
    http_headers: { "X-Canvas-URL": canvasUrl },
  };

  writeToml(filePath, config);
  return { filePath, envVar: "CANVAS_API_TOKEN", token };
}

function configureClient(client, token, canvasUrl) {
  if (client.format === "toml") {
    return configureCodexClient(client, token, canvasUrl);
  }
  return configureJsonClient(client, token, canvasUrl);
}

export { configureClient, readJson, readToml, HOSTED_URL };
```

- [ ] **Step 2: Commit**

```bash
git add cli/lib/config-writer.js
git commit -m "feat(cli): add config writer with JSON/TOML merge and backup"
```

---

### Task 4: Write tests for config writer

**Files:**
- Create: `cli/test/config-writer.test.js`

Uses Node.js built-in test runner (no extra deps). Tests write to temp directories.

- [ ] **Step 1: Write tests**

```javascript
import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import TOML from "@iarna/toml";
import { configureClient, readJson, readToml } from "../lib/config-writer.js";

describe("configureClient", () => {
  let tempDir;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), "canvas-mcp-test-"));
  });

  afterEach(() => {
    rmSync(tempDir, { recursive: true, force: true });
  });

  function makeClient(overrides) {
    return {
      id: "test",
      name: "Test Client",
      format: "json",
      wrapperKey: "mcpServers",
      configPath: () => join(tempDir, "config.json"),
      ...overrides,
    };
  }

  it("creates new JSON config for mcpServers client", () => {
    const client = makeClient({});
    configureClient(client, "test-token", "https://canvas.example.com");

    const config = readJson(client.configPath());
    assert.equal(config.mcpServers["canvas-mcp"].url, "https://mcp.illinihunt.org/mcp");
    assert.equal(config.mcpServers["canvas-mcp"].headers["X-Canvas-Token"], "test-token");
    assert.equal(config.mcpServers["canvas-mcp"].headers["X-Canvas-URL"], "https://canvas.example.com");
  });

  it("creates new JSON config with servers wrapper (VS Code)", () => {
    const client = makeClient({ wrapperKey: "servers" });
    configureClient(client, "test-token", "https://canvas.example.com");

    const config = readJson(client.configPath());
    assert.ok(config.servers["canvas-mcp"]);
    assert.equal(config.servers["canvas-mcp"].url, "https://mcp.illinihunt.org/mcp");
  });

  it("preserves existing servers in JSON config", () => {
    const client = makeClient({});
    const existing = { mcpServers: { "other-server": { command: "node", args: ["other.js"] } } };
    writeFileSync(client.configPath(), JSON.stringify(existing));

    configureClient(client, "test-token", "https://canvas.example.com");

    const config = readJson(client.configPath());
    assert.ok(config.mcpServers["other-server"]);
    assert.ok(config.mcpServers["canvas-mcp"]);
  });

  it("backs up existing JSON config before writing", () => {
    const client = makeClient({});
    writeFileSync(client.configPath(), '{"existing": true}');

    configureClient(client, "test-token", "https://canvas.example.com");

    assert.ok(existsSync(client.configPath() + ".bak"));
    const backup = JSON.parse(readFileSync(client.configPath() + ".bak", "utf-8"));
    assert.equal(backup.existing, true);
  });

  it("creates new TOML config for Codex", () => {
    const client = makeClient({
      format: "toml",
      configPath: () => join(tempDir, "config.toml"),
    });

    const result = configureClient(client, "test-token", "https://canvas.example.com");

    const config = readToml(client.configPath());
    assert.equal(config.mcp_servers["canvas-mcp"].url, "https://mcp.illinihunt.org/mcp");
    assert.equal(config.mcp_servers["canvas-mcp"].env_http_headers["X-Canvas-Token"], "CANVAS_API_TOKEN");
    assert.equal(config.mcp_servers["canvas-mcp"].http_headers["X-Canvas-URL"], "https://canvas.example.com");
    assert.equal(result.envVar, "CANVAS_API_TOKEN");
    assert.equal(result.token, "test-token");
  });

  it("preserves existing TOML config for Codex", () => {
    const client = makeClient({
      format: "toml",
      configPath: () => join(tempDir, "config.toml"),
    });
    const existing = { model: "o3-pro", mcp_servers: { other: { url: "http://other" } } };
    writeFileSync(client.configPath(), TOML.stringify(existing));

    configureClient(client, "test-token", "https://canvas.example.com");

    const config = readToml(client.configPath());
    assert.equal(config.model, "o3-pro");
    assert.ok(config.mcp_servers.other);
    assert.ok(config.mcp_servers["canvas-mcp"]);
  });

  it("creates parent directories if config path does not exist", () => {
    const client = makeClient({
      configPath: () => join(tempDir, "deep", "nested", "config.json"),
    });

    configureClient(client, "test-token", "https://canvas.example.com");

    assert.ok(existsSync(join(tempDir, "deep", "nested", "config.json")));
  });
});
```

- [ ] **Step 2: Run tests**

Run: `cd cli && node --test test/config-writer.test.js`
Expected: 7 tests pass

- [ ] **Step 3: Commit**

```bash
git add cli/test/config-writer.test.js
git commit -m "test(cli): add config writer tests (JSON, TOML, merge, backup)"
```

---

## Chunk 2: Wizard and Entry Point

### Task 5: Interactive wizard

**Files:**
- Create: `cli/lib/wizard.js`

Prompts for token, Canvas URL, and client selection. Returns structured data for the config writer.

- [ ] **Step 1: Write wizard.js**

```javascript
import prompts from "prompts";
import { clients } from "./clients.js";

async function runWizard() {
  console.log("\n  Canvas MCP Setup\n");

  const response = await prompts(
    [
      {
        type: "password",
        name: "token",
        message: "Enter your Canvas API token:",
        validate: (v) => (v.length > 0 ? true : "Token is required"),
      },
      {
        type: "text",
        name: "canvasUrl",
        message: "Enter your Canvas URL (e.g., https://canvas.illinois.edu):",
        validate: (v) => {
          try {
            const url = new URL(v);
            return url.protocol === "https:" ? true : "URL must start with https://";
          } catch {
            return "Enter a valid URL";
          }
        },
      },
      {
        type: "multiselect",
        name: "selectedClients",
        message: "Which client(s) to configure?",
        choices: clients.map((c) => ({ title: c.name, value: c.id })),
        min: 1,
        hint: "- Space to select, Enter to confirm",
      },
    ],
    {
      onCancel: () => {
        console.log("\nSetup cancelled.");
        process.exit(0);
      },
    }
  );

  return {
    token: response.token,
    canvasUrl: response.canvasUrl.replace(/\/+$/, ""),
    selectedClients: response.selectedClients,
  };
}

export { runWizard };
```

- [ ] **Step 2: Commit**

```bash
git add cli/lib/wizard.js
git commit -m "feat(cli): add interactive setup wizard with token/URL/client prompts"
```

---

### Task 6: CLI entry point

**Files:**
- Create: `cli/bin/cli.js`

Routes subcommands. For v1, only `setup` is implemented.

- [ ] **Step 1: Write cli.js**

```javascript
#!/usr/bin/env node

import { runWizard } from "../lib/wizard.js";
import { clients } from "../lib/clients.js";
import { configureClient } from "../lib/config-writer.js";

const command = process.argv[2];

if (!command || command === "setup") {
  const { token, canvasUrl, selectedClients } = await runWizard();

  const results = [];

  for (const clientId of selectedClients) {
    const client = clients.find((c) => c.id === clientId);
    try {
      const result = configureClient(client, token, canvasUrl);
      results.push({ client, result, success: true });
    } catch (err) {
      results.push({ client, error: err.message, success: false });
    }
  }

  // Print results
  console.log("");
  for (const { client, result, success, error } of results) {
    if (success) {
      const filePath = typeof result === "object" ? result.filePath : result;
      console.log(`  Done! Configured ${client.name} (${filePath})`);
    } else {
      console.log(`  Failed: ${client.name} — ${error}`);
    }
  }

  // Codex-specific: remind about env var
  const codexResult = results.find((r) => r.client.id === "codex" && r.success && typeof r.result === "object");
  if (codexResult) {
    console.log(`\n  For Codex, set your token as an environment variable:`);
    console.log(`  export CANVAS_API_TOKEN="${codexResult.result.token}"`);
    console.log(`  (Add this to your ~/.zshrc or ~/.bashrc to persist it)\n`);
  }

  console.log(`  Server: https://mcp.illinihunt.org/mcp`);
  console.log(`  Restart your client to activate.`);
  console.log(`  Test with: "What courses am I enrolled in?"\n`);
} else if (command === "--help" || command === "-h") {
  console.log(`
  canvas-mcp — Setup wizard for Canvas LMS MCP server

  Usage:
    npx canvas-mcp setup    Configure your MCP client(s)
    npx canvas-mcp --help   Show this help

  Learn more: https://github.com/vishalsachdev/canvas-mcp
`);
} else {
  console.error(`Unknown command: ${command}\nRun: npx canvas-mcp --help`);
  process.exit(1);
}
```

- [ ] **Step 2: Make executable**

Run: `chmod +x cli/bin/cli.js`

- [ ] **Step 3: Test locally**

Run: `cd cli && node bin/cli.js --help`
Expected: Shows help text

- [ ] **Step 4: Commit**

```bash
git add cli/bin/cli.js
git commit -m "feat(cli): add CLI entry point with setup command and help"
```

---

## Chunk 3: Test, Publish, Verify

### Task 7: End-to-end local test

- [ ] **Step 1: Run unit tests**

Run: `cd cli && node --test test/config-writer.test.js`
Expected: All 7 tests pass

- [ ] **Step 2: Test interactive wizard locally**

Run: `cd cli && node bin/cli.js setup`
Walk through the prompts, select Codex CLI, verify:
- `~/.codex/config.toml` has `[mcp_servers.canvas-mcp]` entry
- Existing config preserved
- `.bak` file created

- [ ] **Step 3: Test with npx locally**

Run: `cd cli && npm link && canvas-mcp setup`
Verify it works as a global command.

- [ ] **Step 4: Commit any fixes from testing**

---

### Task 8: Publish to npm

- [ ] **Step 1: Verify npm login**

Run: `npm whoami`
If not logged in: `npm login`

- [ ] **Step 2: Dry run publish**

Run: `cd cli && npm publish --dry-run`
Expected: Shows files that would be published (bin/, lib/, package.json, README.md)

- [ ] **Step 3: Publish**

Run: `cd cli && npm publish`
Expected: `canvas-mcp@1.0.0` published

- [ ] **Step 4: Verify with npx**

Run: `npx canvas-mcp --help` (from a different directory)
Expected: Shows help text

- [ ] **Step 5: Full verification**

Run: `npx canvas-mcp setup`
Select Codex CLI, enter real Canvas credentials.
Open Codex, ask: "What courses am I enrolled in?"
Expected: Returns real course data.

---

### Task 9: Add CLI README

**Files:**
- Create: `cli/README.md`

- [ ] **Step 1: Write README**

Brief README covering: what it does, `npx canvas-mcp setup`, supported clients, link to main repo.

- [ ] **Step 2: Commit and push**

```bash
git add cli/
git commit -m "feat(cli): add README for npm package"
git push origin main
```

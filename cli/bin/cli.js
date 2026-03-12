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

  console.log("");
  for (const { client, result, success, error } of results) {
    if (success) {
      const filePath = typeof result === "object" ? result.filePath : result;
      console.log(`  Configured ${client.name} (${filePath})`);
    } else {
      console.log(`  Failed: ${client.name} — ${error}`);
    }
  }

  const codexResult = results.find(
    (r) => r.client.id === "codex" && r.success && typeof r.result === "object"
  );
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

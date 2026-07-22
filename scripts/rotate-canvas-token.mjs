#!/usr/bin/env node
// Rotate the Canvas API token in both places it lives:
//   1) ./.env                -> CANVAS_API_TOKEN=<token>   (stdio dev path)
//   2) ~/.claude.json        -> mcpServers.canvas args, "--header" "X-Canvas-Token: <token>"  (hosted Entra client path)
//
// Usage (run from repo root so ./.env resolves):
//   NEW_CANVAS_TOKEN='paste-token-here' node scripts/rotate-canvas-token.mjs
//
// The token is read ONLY from the env var, never echoed. Both files are backed up first.

import { readFileSync, writeFileSync, copyFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const token = process.env.NEW_CANVAS_TOKEN;
if (!token || token.trim().length < 20) {
  console.error('ERROR: set NEW_CANVAS_TOKEN to the new token (>=20 chars) before running.');
  process.exit(1);
}
const t = token.trim();
const mask = (s) => `${s.slice(0, 6)}…(${s.length} chars)`;
const stamp = new Date().toISOString().replace(/[:.]/g, '-');

// ---- 1) .env ----
const envPath = join(process.cwd(), '.env');
if (!existsSync(envPath)) {
  console.error(`ERROR: no .env at ${envPath} — run from the canvas-mcp repo root.`);
  process.exit(1);
}
copyFileSync(envPath, `${envPath}.bak-${stamp}`);
let env = readFileSync(envPath, 'utf8');
if (/^CANVAS_API_TOKEN=.*$/m.test(env)) {
  env = env.replace(/^CANVAS_API_TOKEN=.*$/m, `CANVAS_API_TOKEN=${t}`);
} else {
  env += `\nCANVAS_API_TOKEN=${t}\n`;
}
writeFileSync(envPath, env);
console.log(`✓ .env CANVAS_API_TOKEN updated -> ${mask(t)} (backup: .env.bak-${stamp})`);

// ---- 2) ~/.claude.json hosted canvas header ----
const claudePath = join(homedir(), '.claude.json');
const cfg = JSON.parse(readFileSync(claudePath, 'utf8'));
const canvas = cfg?.mcpServers?.canvas;
if (!canvas || !Array.isArray(canvas.args)) {
  console.error('WARN: no mcpServers.canvas.args in ~/.claude.json — skipped hosted header. Update it manually.');
} else {
  const i = canvas.args.findIndex((a) => typeof a === 'string' && a.startsWith('X-Canvas-Token:'));
  if (i === -1) {
    console.error('WARN: no "X-Canvas-Token:" arg found in canvas server — skipped. Inspect the args manually.');
  } else {
    copyFileSync(claudePath, `${claudePath}.bak-${stamp}`);
    canvas.args[i] = `X-Canvas-Token: ${t}`;
    writeFileSync(claudePath, JSON.stringify(cfg, null, 2));
    console.log(`✓ ~/.claude.json canvas X-Canvas-Token header updated -> ${mask(t)} (backup: ~/.claude.json.bak-${stamp})`);
  }
}

console.log('\nDone. Restart Claude Code to reload the hosted canvas MCP server.');
console.log('Then verify with: curl -sS -H "X-Canvas-Token: <tok>" "$CANVAS_API_URL/users/self"  (or list_courses in a fresh session).');

import { describe, it, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, statSync, writeFileSync, chmodSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { configureClient } from "../lib/config-writer.js";

// These configs store a Canvas API token in cleartext. Written under the usual
// umask they land as 0644 — readable by every other account on a shared machine
// — so the mode is asserted here rather than left to the environment.
const OWNER_ONLY = 0o600;

function mode(path) {
  return statSync(path).mode & 0o777;
}

describe("config file permissions", () => {
  let tempDir;

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), "canvas-mcp-perm-"));
  });

  afterEach(() => {
    rmSync(tempDir, { recursive: true, force: true });
  });

  function makeClient(overrides = {}) {
    return {
      id: "test",
      name: "Test Client",
      format: "json",
      wrapperKey: "mcpServers",
      configPath: () => join(tempDir, "config.json"),
      ...overrides,
    };
  }

  it("creates a new JSON config owner-only", () => {
    const client = makeClient();
    configureClient(client, "secret-token", "https://canvas.example.com");

    assert.equal(mode(client.configPath()), OWNER_ONLY);
  });

  it("creates a new TOML config owner-only", () => {
    const client = makeClient({
      format: "toml",
      configPath: () => join(tempDir, "config.toml"),
    });
    configureClient(client, "secret-token", "https://canvas.example.com");

    assert.equal(mode(client.configPath()), OWNER_ONLY);
  });

  it("tightens an existing world-readable config", () => {
    // writeFileSync's `mode` only applies when it creates the file, so an
    // existing 0644 config would otherwise keep its permissions forever.
    const client = makeClient();
    writeFileSync(client.configPath(), "{}\n", "utf-8");
    chmodSync(client.configPath(), 0o644);

    configureClient(client, "secret-token", "https://canvas.example.com");

    assert.equal(mode(client.configPath()), OWNER_ONLY);
  });

  it("protects the backup, which carries an older token", () => {
    const client = makeClient();
    writeFileSync(
      client.configPath(),
      JSON.stringify({ mcpServers: { "canvas-mcp": { headers: { "X-Canvas-Token": "old-token" } } } }),
      "utf-8"
    );
    chmodSync(client.configPath(), 0o644);

    configureClient(client, "new-token", "https://canvas.example.com");

    const backupPath = client.configPath() + ".bak";
    assert.equal(mode(backupPath), OWNER_ONLY, "backup left world-readable");
  });
});

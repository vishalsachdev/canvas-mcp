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

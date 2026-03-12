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

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

function updateConfigFile(client, mutate) {
  const filePath = client.configPath();
  const isToml = client.format === "toml";

  backup(filePath);
  const config = isToml ? readToml(filePath) : readJson(filePath);
  mutate(config);
  (isToml ? writeToml : writeJson)(filePath, config);

  return filePath;
}

function configureClient(client, token, canvasUrl) {
  if (client.format === "toml") {
    const filePath = updateConfigFile(client, (config) => {
      if (!config.mcp_servers) config.mcp_servers = {};
      config.mcp_servers["canvas-mcp"] = {
        url: HOSTED_URL,
        env_http_headers: { "X-Canvas-Token": "CANVAS_API_TOKEN" },
        http_headers: { "X-Canvas-URL": canvasUrl },
      };
    });
    return { filePath, envVar: "CANVAS_API_TOKEN", token };
  }

  return updateConfigFile(client, (config) => {
    const wrapper = client.wrapperKey;
    if (!config[wrapper]) config[wrapper] = {};
    config[wrapper]["canvas-mcp"] = {
      url: HOSTED_URL,
      headers: {
        "X-Canvas-Token": token,
        "X-Canvas-URL": canvasUrl,
      },
    };
  });
}

export { configureClient, readJson, readToml, HOSTED_URL };

import {
  readFileSync,
  writeFileSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  chmodSync,
} from "node:fs";
import { dirname } from "node:path";
import TOML from "@iarna/toml";

const HOSTED_URL = "https://mcp.illinihunt.org/mcp";

// These files hold a Canvas API token in cleartext. Written with the default
// umask they land as 0644, readable by every other account on the machine, so
// the mode is set explicitly. writeFileSync's `mode` only applies when it
// creates the file, so an existing config is chmod'ed too.
const SECRET_FILE_MODE = 0o600;

function restrictPermissions(filePath) {
  try {
    chmodSync(filePath, SECRET_FILE_MODE);
  } catch {
    // Non-POSIX filesystems may not support this; the write itself still stands.
  }
}

function backup(filePath) {
  if (existsSync(filePath)) {
    const backupPath = filePath + ".bak";
    copyFileSync(filePath, backupPath);
    // The backup carries the same (or an older) token, so it needs the same
    // protection — copyFileSync preserves nothing useful here.
    restrictPermissions(backupPath);
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
  writeFileSync(filePath, JSON.stringify(data, null, 2) + "\n", {
    encoding: "utf-8",
    mode: SECRET_FILE_MODE,
  });
  restrictPermissions(filePath);
}

function writeToml(filePath, data) {
  ensureDir(filePath);
  writeFileSync(filePath, TOML.stringify(data), {
    encoding: "utf-8",
    mode: SECRET_FILE_MODE,
  });
  restrictPermissions(filePath);
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

export {
  configureClient,
  readJson,
  readToml,
  HOSTED_URL,
  SECRET_FILE_MODE,
};

#!/usr/bin/env bash
# Build the Claude Desktop Extension (.mcpb) bundle for canvas-mcp.
#
# Prereqs:
#   - Node.js (for the mcpb CLI; npx fetches it on demand)
#   - The repo's manifest.json + .mcpbignore at the repo root
#
# Usage:  ./scripts/build-mcpb.sh
# Output: canvas-mcp.mcpb in the repo root.
#
# The runtime path uses uv (server.type=python + `uv run canvas-mcp-server`), so
# the END USER needs `uv` available; Claude Desktop's uv-managed runtime provides
# it. No Python deps are vendored — they resolve from pyproject.toml on first run.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Validating manifest.json"
npx -y @anthropic-ai/mcpb@latest validate manifest.json

echo "==> Packing .mcpb"
npx -y @anthropic-ai/mcpb@latest pack . canvas-mcp.mcpb

echo "==> Done: $(ls -lh canvas-mcp.mcpb | awk '{print $5, $9}')"
echo
echo "Next: double-click canvas-mcp.mcpb to install in Claude Desktop, then test."
echo "MUST test on BOTH macOS and Windows (pydantic is a compiled dep)."

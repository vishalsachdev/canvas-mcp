#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Load environment variables from .env file
ENV_FILE="$SCRIPT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: .env file not found at $ENV_FILE. Please create one with CANVAS_API_TOKEN and CANVAS_API_URL" >&2
    exit 1
fi
# Keep the legacy launcher's existing dotenv parsing semantics. The application
# itself uses python-dotenv; sourcing this file as shell code is not equivalent.
# shellcheck disable=SC2046
export $(grep -v '^#' "$ENV_FILE" | xargs)

# Verify required environment variables are set
if [[ -z "${CANVAS_API_TOKEN:-}" || -z "${CANVAS_API_URL:-}" ]]; then
    echo "Error: CANVAS_API_TOKEN and CANVAS_API_URL must be set in .env file" >&2
    exit 1
fi

cd "$SCRIPT_DIR"

# Run the server using the repo-local venv if present (preferred)
VENV_SERVER="$SCRIPT_DIR/.venv/bin/canvas-mcp-server"
if [[ -x "$VENV_SERVER" ]]; then
    exec "$VENV_SERVER"
fi
exec canvas-mcp-server

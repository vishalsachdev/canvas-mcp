#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "Script directory: $SCRIPT_DIR" >&2

# Print startup message (directed to stderr so it doesn't interfere with JSON)
echo "Starting Canvas MCP Server..." >&2

# Load environment variables from .env file
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    echo "Loading environment variables from .env file: $ENV_FILE" >&2
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
else
    echo "Error: .env file not found at $ENV_FILE. Please create one with CANVAS_API_TOKEN and CANVAS_API_URL" >&2
    exit 1
fi

# Verify required environment variables are set
if [ -z "$CANVAS_API_TOKEN" ] || [ -z "$CANVAS_API_URL" ]; then
    echo "Error: CANVAS_API_TOKEN and CANVAS_API_URL must be set in .env file" >&2
    exit 1
fi

# Go to the script directory
cd $SCRIPT_DIR
echo "Changed directory to: $(pwd)" >&2

# Run the server using the installed CLI command
echo "Starting server with canvas-mcp-server command..." >&2
canvas-mcp-server

# Exit message
echo "Server stopped" >&2
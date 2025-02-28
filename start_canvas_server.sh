#!/bin/bash

# Print startup message (directed to stderr so it doesn't interfere with JSON)
echo "Starting Canvas MCP Server..." >&2

# Path to your virtual environment
VENV_PATH="/Users/vishalsachdev/Desktop/canvas-mcp/fresh_venv"
echo "Using virtual environment at: $VENV_PATH" >&2

# Activate the virtual environment
echo "Activating virtual environment..." >&2
source "$VENV_PATH/bin/activate"

# Set environment variables
export CANVAS_API_TOKEN="14559~uZMKmDLWH62e98YzPDmYHcyWt8vV347NRUr4ZTUch6Eay874GBfmVEZe79r2tKDr"
export CANVAS_API_URL="https://canvas.illinois.edu/api/v1"

# Go to the script directory
cd "/Users/vishalsachdev/Desktop/canvas-mcp"
echo "Changed directory to: $(pwd)" >&2

# Run the Python script with the specific python from the virtualenv
echo "Starting server with Python at: $VENV_PATH/bin/python" >&2
"$VENV_PATH/bin/python" "canvas_server_cached.py"

# Exit message
echo "Server stopped" >&2
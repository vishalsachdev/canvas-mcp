# Canvas MCP Server

This repository contains a Message Control Protocol (MCP) server implementation for interacting with the Canvas Learning Management System API. The server is designed to work with Claude Desktop and potentially other MCP clients.

## Overview

The Canvas MCP Server provides a local interface to Canvas LMS API, allowing you to:
- List and manage courses
- Access assignments and submissions
- View announcements
- Retrieve course syllabi and modules
- Manage users and enrollments

## Prerequisites

- Python 3.x
- Virtual environment (venv)
- Canvas API Token
- Canvas API URL (e.g., https://canvas.illinois.edu/api/v1)

## Installation

1. Clone this repository:
```bash
git clone https://github.com/vishalsachdev/canvas-mcp.git
cd canvas-mcp
```

2. Create and activate a virtual environment:
```bash
python -m venv fresh_venv
source fresh_venv/bin/activate  # On Unix/macOS
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

### 1. Server Configuration

1. Edit the `start_canvas_server.sh` script to set your:
   - Canvas API Token ([How to get your Canvas API token](https://community.canvaslms.com/t5/Canvas-Basics-Guide/How-do-I-manage-API-access-tokens-in-my-user-account/ta-p/615312))
   - Canvas API URL (change the domain to match your university)
     ```bash
     # Example for University of Illinois:
     export CANVAS_API_URL="https://canvas.illinois.edu/api/v1"
     # Change to your university's Canvas domain, e.g.:
     export CANVAS_API_URL="https://canvas.university.edu/api/v1"
     ```
   - Virtual environment path (default: `fresh_venv` in the project directory)
   - Working directory

2. Make the start script executable:
```bash
chmod +x start_canvas_server.sh
```

### 2. Claude Desktop Configuration

1. Install [Claude Desktop](https://claude.ai/download) if you haven't already.

2. Create or edit the Claude Desktop configuration file:
```bash
vim ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

3. Add the Canvas MCP server configuration:
```json
{
  "mcpServers": [
    {
      "name": "canvas-api",
      "command": "/Users/YOUR_USERNAME/path/to/canvas-mcp/start_canvas_server.sh"
    }
  ]
}
```

Replace `/Users/YOUR_USERNAME/path/to/canvas-mcp` with the absolute path to where you cloned this repository.

4. Restart Claude Desktop to load the new configuration.

5. Verify the server is working by looking for the hammer icon 🔨 in Claude Desktop - it should show the available Canvas API tools.

## Usage with Claude Desktop

This MCP server is designed to work seamlessly with Claude Desktop. When using with Claude Desktop:

1. You don't need to manually start the server - Claude Desktop will automatically initiate the `start_canvas_server.sh` script when needed.

2. Claude Desktop will handle:
   - Starting the server process
   - Managing the server lifecycle
   - Connecting to the server for Canvas LMS operations

3. The server will run locally and communicate with Claude Desktop through the MCP protocol.

Note: If you're using a different MCP client, you may need to start the server manually using:
```bash
./start_canvas_server.sh
```

## Server Implementations

The repository includes multiple server implementations:
- `canvas_server_cached.py` (recommended): Implements caching for better performance
- `canvas_mcp_server.py`: Basic implementation
- `canvas_mcp_server_new.py`: Alternative implementation

The start script is configured to use `canvas_server_cached.py` by default.

## Features

The server provides various endpoints for Canvas LMS interaction:
- Course management
- Assignment handling
- Submission access
- User management
- Announcement retrieval
- Resource access (syllabi, modules)

## Security Note

Keep your Canvas API token secure and never commit it to version control. The token in the start script should be replaced with your own token.

## Client Compatibility

This MCP server is primarily designed for use with Claude Desktop. While it may work with other MCP clients, compatibility is not guaranteed.

## Troubleshooting

If you encounter issues:
1. Ensure your virtual environment is properly activated
2. Verify your Canvas API token is valid
3. Check the API URL is correct
4. Make sure all dependencies are installed
5. Check the server logs for error messages

## Contributing

Feel free to submit issues and pull requests to improve the server functionality.

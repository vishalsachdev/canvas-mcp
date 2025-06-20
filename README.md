# Canvas MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains a Message Control Protocol (MCP) server implementation for interacting with the Canvas Learning Management System API. The server is designed to work with Claude Desktop and potentially other MCP clients.

> **Note**: Recently refactored to a modular architecture for better maintainability. The legacy monolithic implementation has been archived.

## Overview

The Canvas MCP Server bridges the gap between Claude Desktop and Canvas Learning Management System, providing educators with an intelligent interface to their Canvas environment. Built on the Message Control Protocol (MCP), it enables natural language interactions with Canvas data while maintaining security through local API access.

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
python -m venv canvas-mcp
source canvas-mcp/bin/activate  # On Unix/macOS
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

### 1. Create Environment File

Create a `.env` file in the root directory with the following variables:

```
CANVAS_API_TOKEN=your_canvas_api_token_here
CANVAS_API_URL=https://canvas.youruniversity.edu/api/v1
```

Replace the values with:
- Your Canvas API Token ([How to get your Canvas API token](https://community.canvaslms.com/t5/Canvas-Basics-Guide/How-do-I-manage-API-access-tokens-in-my-user-account/ta-p/615312))
- Your university's Canvas API URL

### 2. Configure Start Script

The `start_canvas_server.sh` script is already configured to:
- Load environment variables from the `.env` file
- Activate the virtual environment
- Run the cached server implementation

Make the start script executable:
```bash
chmod +x start_canvas_server.sh
```

### 3. Claude Desktop Configuration

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

## Available Tools

The Canvas MCP Server provides a comprehensive set of tools for interacting with the Canvas LMS API. These tools are organized into logical categories for better discoverability and maintainability.

### Tool Categories

1. **Course Tools** - List and manage courses, get detailed information, generate summaries
2. **Assignment Tools** - Handle assignments, submissions, and peer reviews with analytics
3. **Rubric Tools** - Create, manage, and grade with rubrics
4. **Discussion & Announcement Tools** - Manage discussions, announcements, and replies
5. **Page & Content Tools** - Access pages, modules, and course content
6. **User & Enrollment Tools** - Manage enrollments, users, and groups
7. **Analytics Tools** - View student analytics, assignment statistics, and progress tracking

📖 [View Full Tool Documentation](tools/README.md) for detailed information about all available tools.

## Usage with Claude Desktop

This MCP server is designed to work seamlessly with Claude Desktop:

1. Claude Desktop will automatically start the server when needed
2. You'll see the Canvas API tools in the Claude Desktop interface (hammer icon 🔨)
3. You can ask Claude to perform Canvas operations like "Show me my courses" or "Get the syllabus for my Biology course"

For manual testing, you can start the server directly:
```bash
./start_canvas_server.sh
```

## Project Structure

```
.
├── core/                      # Core functionality modules
│   ├── cache.py              # Caching utilities
│   ├── client.py             # HTTP client for Canvas API
│   ├── dates.py              # Date handling utilities
│   ├── types.py              # Type definitions
│   └── validation.py         # Input validation
├── tools/                    # MCP tool implementations
│   ├── assignments.py        # Assignment-related tools
│   ├── courses.py            # Course-related tools
│   ├── other_tools.py        # Miscellaneous tools
│   └── rubrics.py            # Rubric-related tools
├── utils/                    # Utility scripts
├── resources/                # Resource files
├── docs/                     # Additional documentation
└── canvas_server_refactored.py # Main server entry point
```

## Documentation

- **[Tool Documentation](./tools/README.md)** - Complete reference for all available tools
- **[Pages Implementation Guide](./PAGES_IMPLEMENTATION.md)** - Comprehensive Pages feature guide
- **[Rubric Features Guide](./RUBRIC_FEATURES.md)** - Advanced rubric functionality and workflows
- **[Development Guide](./CLAUDE.md)** - Architecture details and contribution guidelines
## Technical Details

### Architecture

The server uses a modular architecture built on FastMCP for robust MCP server implementation:

- **Core Components** (`core/`): Shared functionality including caching, HTTP client, validation, and type definitions
- **Tool Modules** (`tools/`): Domain-organized tools with self-contained responsibilities and consistent error handling patterns
- **Asynchronous Design**: Built with `asyncio` and `httpx` for non-blocking I/O and efficient concurrent request handling

### Key Features

- **Unified Interface**: All Canvas API interactions through a single client with intelligent caching
- **Type Safety**: Full type hints with comprehensive error handling and recovery options
- **Performance Optimized**: Caching layer, batch processing, lazy loading, and connection pooling
- **Educational Focus**: Student analytics, performance tracking, and discussion workflow tools

### Dependencies

Core packages (see `requirements.txt` for versions):
- `fastmcp`: MCP server implementation
- `httpx`: Asynchronous HTTP requests  
- `python-dotenv`: Environment management
- `python-dateutil`: Date parsing
- `pydantic`: Data validation

### Utility Scripts

- `extract_canvas_api_docs.py`: Generate API documentation from Canvas
- `get_course_grades.py`: Export course grades to CSV

For developers, see the [Development Guide](CLAUDE.md) for architecture details and contribution guidelines.

## Troubleshooting

If you encounter issues:

1. **Server Won't Start** - Verify your [Configuration](#configuration) setup: `.env` file, virtual environment path, and dependencies
2. **Authentication Errors** - Check your Canvas API token validity and permissions
3. **Connection Issues** - Verify Canvas API URL correctness and network access
4. **Debugging** - Check Claude Desktop console logs or run server manually for error output

## Security Considerations

- Your Canvas API token grants access to your Canvas account
- Never commit your `.env` file to version control
- Consider using a token with limited permissions if possible
- The server runs locally on your machine and doesn't expose your credentials externally

## Contributing

Contributions are welcome! Feel free to:
- Submit issues for bugs or feature requests
- Create pull requests with improvements
- Share your use cases and feedback

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Created by [Vishal Sachdev](https://github.com/vishalsachdev)

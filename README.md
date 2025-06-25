# Canvas MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains a Message Control Protocol (MCP) server implementation for interacting with the Canvas Learning Management System API. The server is designed to work with Claude Desktop and potentially other MCP clients.

> **Note**: Recently refactored to a modular architecture for better maintainability. The legacy monolithic implementation has been archived.

## Overview

The Canvas MCP Server bridges the gap between Claude Desktop and Canvas Learning Management System, providing educators with an intelligent interface to their Canvas environment. Built on the Message Control Protocol (MCP), it enables natural language interactions with Canvas data while maintaining **FERPA compliance** through advanced privacy protection features.

## 🔒 Privacy-First Student Data Protection

**Recently Implemented**: Complete FERPA compliance through systematic data anonymization across all tools.

**The Problem**: Using AI tools with student data creates FERPA compliance risks and privacy violations.

**What We Built**:
- **Source-level data anonymization** that converts real names to consistent anonymous IDs (Student_xxxxxxxx)
- **Automatic email masking** and PII filtering from discussion posts and submissions  
- **Local-only processing** with configurable privacy controls (`ENABLE_DATA_ANONYMIZATION=true`)
- **FERPA-compliant analytics**: Ask "Which students need support?" without exposing real identities
- **De-anonymization mapping tool** for faculty to correlate anonymous IDs with real students locally
- **Robust error handling** ensures tools continue working even if anonymization fails

All student data is anonymized **before** it reaches AI systems, ensuring complete privacy protection while maintaining full educational functionality. **8 core tools** now include comprehensive privacy protection with production-ready error handling.

## Prerequisites

- **Python 3.10+** - Required for modern features and type hints
- **Canvas API Access** - API token and institution URL
- **Claude Desktop** - For MCP integration

## Quick Start (Automated Installation)

The fastest way to get started is with our automated installer:

```bash
# Clone the repository
git clone https://github.com/vishalsachdev/canvas-mcp.git
cd canvas-mcp

# Run the automated installer
python scripts/install.py
```

The installer will:
- ✅ Set up Python environment with `uv` package manager
- ✅ Install all dependencies automatically  
- ✅ Create environment configuration template
- ✅ Configure Claude Desktop integration
- ✅ Test the installation

## Manual Installation

If you prefer manual setup:

### 1. Install Dependencies

```bash
# Install uv package manager (faster than pip)
pip install uv

# Install the package
uv pip install -e .
```

### 2. Configure Environment

```bash
# Copy environment template
cp env.template .env

# Edit with your Canvas credentials
# Required: CANVAS_API_TOKEN, CANVAS_API_URL
```

Get your Canvas API token from: **Canvas → Account → Settings → New Access Token**

### 3. Claude Desktop Setup

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "canvas-mcp-server"
    }
  }
}
```

## Verification

Test your setup:

```bash
# Test Canvas API connection
canvas-mcp-server --test

# View configuration
canvas-mcp-server --config

# Start server (for manual testing)
canvas-mcp-server
```

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

This MCP server works seamlessly with Claude Desktop:

1. **Automatic Startup**: Claude Desktop starts the server when needed
2. **Tool Integration**: Canvas tools appear in Claude's interface (🔨 hammer icon)
3. **Natural Language**: Ask Claude things like:
   - *"Show me my courses"*
   - *"Which students haven't submitted the latest assignment?"*
   - *"Create an announcement about tomorrow's exam"*

## Project Structure

Modern Python package structure following 2025 best practices:

```
canvas-mcp/
├── pyproject.toml             # Modern Python project config
├── env.template              # Environment configuration template
├── src/
│   └── canvas_mcp/            # Main package
│       ├── __init__.py        # Package initialization
│       ├── server.py          # Main server entry point
│       ├── core/              # Core utilities
│       │   ├── config.py      # Configuration management
│       │   ├── client.py      # HTTP client
│       │   ├── cache.py       # Caching system
│       │   └── validation.py  # Input validation
│       ├── tools/             # MCP tool implementations
│       │   ├── courses.py     # Course management
│       │   ├── assignments.py # Assignment tools
│       │   ├── discussions.py # Discussion tools
│       │   ├── rubrics.py     # Rubric tools
│       │   └── other_tools.py # Misc tools
│       └── resources/         # MCP resources
├── scripts/
│   └── install.py            # Automated installation
└── docs/                     # Documentation
```

## Documentation

- **[Tool Documentation](./tools/README.md)** - Complete reference for all available tools
- **[Pages Implementation Guide](./docs/PAGES_IMPLEMENTATION.md)** - Comprehensive Pages feature guide
- **[Development Guide](./docs/CLAUDE.md)** - Architecture details and contribution guidelines
## Technical Details

### Modern Architecture (2025)

Built with current Python ecosystem best practices:

- **Package Structure**: Modern `src/` layout with `pyproject.toml`
- **Dependency Management**: Fast `uv` package manager with locked dependencies
- **Configuration**: Environment-based config with validation and templates
- **Entry Points**: Proper CLI commands via `pyproject.toml` scripts
- **Type Safety**: Full type hints and runtime validation

### Core Components

- **FastMCP Framework**: Robust MCP server implementation with tool registration
- **Async Architecture**: `httpx` client with connection pooling and rate limiting
- **Smart Caching**: Intelligent request caching with configurable TTL
- **Configuration System**: Environment-based config with validation and defaults
- **Educational Focus**: Tools designed for real teaching workflows

### Dependencies

Modern Python packages (see `pyproject.toml`):
- **`fastmcp`**: MCP server framework
- **`httpx`**: Async HTTP client
- **`python-dotenv`**: Environment configuration
- **`pydantic`**: Data validation and settings
- **`python-dateutil`**: Date/time handling

### Performance Features

- **Connection Pooling**: Reuse HTTP connections for efficiency
- **Request Caching**: Minimize redundant Canvas API calls
- **Async Operations**: Non-blocking I/O for concurrent requests
- **Smart Pagination**: Automatic handling of Canvas API pagination
- **Rate Limiting**: Respect Canvas API limits with backoff

### Development Tools

- **Automated Setup**: One-command installation script
- **Configuration Testing**: Built-in connection and config testing
- **Type Checking**: `mypy` support for type safety
- **Code Quality**: `ruff` and `black` for formatting and linting

For contributors, see the [Development Guide](CLAUDE.md) for detailed architecture and contribution guidelines.

## Troubleshooting

If you encounter issues:

1. **Server Won't Start** - Verify your [Configuration](#configuration) setup: `.env` file, virtual environment path, and dependencies
2. **Authentication Errors** - Check your Canvas API token validity and permissions
3. **Connection Issues** - Verify Canvas API URL correctness and network access
4. **Debugging** - Check Claude Desktop console logs or run server manually for error output

## Security & Privacy Features

### FERPA-Compliant Data Protection
- **Automatic anonymization** of all student data (names, emails, IDs) before AI processing across 8 core tools
- **PII filtering** removes phone numbers, emails, and SSNs from discussion content
- **Consistent anonymous IDs** maintain educational relationships while protecting identity
- **Local de-anonymization mapping** creates secure CSV files for faculty correlation
- **Production-ready error handling** with graceful fallbacks if anonymization fails
- **Local-only processing** - no data leaves your machine except anonymous analytics

### API Security
- Your Canvas API token grants access to your Canvas account
- Never commit your `.env` file to version control  
- Consider using a token with limited permissions if possible
- The server runs locally on your machine and doesn't expose your credentials externally

### Privacy Controls
Configure privacy settings in your `.env` file:
```bash
# Enable automatic student data anonymization (recommended)
ENABLE_DATA_ANONYMIZATION=true

# Debug anonymization process (for testing)
ANONYMIZATION_DEBUG=true
```

## Contributing

Contributions are welcome! Feel free to:
- Submit issues for bugs or feature requests
- Create pull requests with improvements
- Share your use cases and feedback

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Created by [Vishal Sachdev](https://github.com/vishalsachdev)

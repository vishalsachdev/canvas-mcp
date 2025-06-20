# Canvas MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains a Message Control Protocol (MCP) server implementation for interacting with the Canvas Learning Management System API. The server is designed to work with Claude Desktop and potentially other MCP clients.

> **Note**: Recently refactored to a modular architecture for better maintainability. The legacy monolithic implementation has been archived.

## Overview

The Canvas MCP Server provides a local interface to Canvas LMS API, allowing you to:
- List and manage courses
- Access assignments and submissions
- View announcements
- Retrieve course syllabi and modules
- Manage users and enrollments
- Generate course summaries

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

1. **Course Tools**
   - List and manage courses
   - Get detailed course information
   - Generate course summaries
   
   📚 [View Course Tools Documentation](tools/courses.md)

2. **Assignment Tools**
   - List and manage assignments
   - Handle submissions and peer reviews
   - Get assignment details and analytics
   
   📝 [View Assignment Tools Documentation](tools/assignments.md)

3. **Rubric Tools**
   - Create and manage rubrics
   - Attach rubrics to assignments
   - Grade submissions using rubrics
   
   📊 [View Rubric Tools Documentation](tools/rubrics.md)

4. **Discussion & Announcement Tools**
   - Manage discussion topics and entries
   - Create and list announcements
   - Handle discussion replies and threads
   
5. **Page & Content Tools**
   - List and view pages
   - Access module content
   - Get course front page
   - View page revision history
   
6. **User & Enrollment Tools**
   - List course enrollments
   - Get user details
   - Manage user groups

7. **Analytics Tools**
   - View student analytics
   - Get assignment statistics
   - Track course progress

📖 [View Full Documentation](tools/README.md) for detailed information about all available tools, including parameters, return values, and examples.

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

The project follows a modular architecture for better maintainability and organization:

```
.
├── core/                      # Core functionality modules
│   ├── __init__.py
│   ├── cache.py              # Caching utilities
│   ├── client.py             # HTTP client for Canvas API
│   ├── dates.py              # Date handling utilities
│   ├── types.py              # Type definitions
│   └── validation.py         # Input validation
├── tools/                    # MCP tool implementations
│   ├── __init__.py
│   ├── assignments.py        # Assignment-related tools
│   ├── courses.py            # Course-related tools
│   ├── other_tools.py        # Miscellaneous tools
│   ├── rubrics.py            # Rubric-related tools
│   └── README.md             # Tools documentation index
├── utils/                    # Utility scripts
│   ├── extract_canvas_api_docs.py  # API documentation extractor
│   └── get_course_grades.py        # Course grade exporter
├── resources/                # Resource files
├── docs/                     # Additional documentation (generated)
├── .env.template             # Environment template
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── CLAUDE.md                 # Development guide for Claude Code
├── PAGES_IMPLEMENTATION.md   # Pages feature documentation
├── REFACTORING_TEST_RESULTS.md # Refactoring test results
├── RUBRIC_FEATURES.md        # Rubric features documentation
└── canvas_server_refactored.py # Main server entry point
```

## Documentation

### Core Documentation

Comprehensive documentation is available in the `tools/` directory:

- [Tools Documentation](tools/README.md) - Main index of all available tools
- [Course Tools](tools/courses.md) - Documentation for course-related tools
- [Assignment Tools](tools/assignments.md) - Documentation for assignment management
- [Rubric Tools](tools/rubrics.md) - Documentation for rubric functionality
- [Other Tools](tools/other_tools.md) - Documentation for miscellaneous tools

### Implementation Guides

For developers and advanced users, these guides provide in-depth implementation details:

- [Pages Implementation Guide](PAGES_IMPLEMENTATION.md) - Comprehensive guide to the Pages feature, including:
  - Core page tools and their usage
  - Integration with course modules
  - Advanced features and examples
  - Best practices for page management

- [Rubric Features Guide](RUBRIC_FEATURES.md) - Detailed documentation on rubric functionality, including:
  - Creating and managing rubrics
  - Advanced assessment workflows
  - Integration with assignments
  - Real-world examples and use cases

### Development Resources

- [Development Guide](CLAUDE.md) - For contributors working on the codebase
- [Refactoring Results](REFACTORING_TEST_RESULTS.md) - Test results and validation from the refactoring process
## Technical Details

### Architecture

The server is built with a modular architecture for better maintainability and extensibility:

- **Core Components**: Found in `core/` for shared functionality
  - Caching, HTTP client, validation, and type definitions
  - Common utilities used across all tools

- **Tool Modules**: Organized by domain in `tools/`
  - Each tool is self-contained with clear responsibilities
  - Consistent patterns for error handling and API interaction
  - Comprehensive documentation for each tool

- **Asynchronous Design**: Built with `asyncio` and `httpx` for high performance
  - Non-blocking I/O operations
  - Efficient handling of concurrent requests
  - Automatic rate limiting and retry logic

### Key Features

- **Unified Interface**: All Canvas API interactions go through a single client
- **Intelligent Caching**: Reduces API calls and improves performance
- **Comprehensive Error Handling**: Clear error messages and recovery options
- **Type Safety**: Full type hints for better code quality and IDE support
- **Documentation**: Extensive inline documentation and examples

### Performance Considerations

- **Caching Layer**: Redundant API calls are minimized
- **Batch Processing**: Where possible, operations are batched for efficiency
- **Lazy Loading**: Resources are loaded only when needed
- **Connection Pooling**: HTTP connections are reused for better performance

For developers, see the [Development Guide](CLAUDE.md) for more information on the architecture and contribution guidelines.

### Dependencies

The server requires the following Python packages (see `requirements.txt` for specific versions):
- `httpx`: For asynchronous HTTP requests
- `fastmcp`: For MCP server implementation
- `python-dotenv`: For environment variable management
- `python-dateutil`: For date parsing and manipulation
- `pydantic`: For data validation and settings management
- `typing-extensions`: For type hints support

### Utility Scripts

- `utils/extract_canvas_api_docs.py`: Script to extract and generate API documentation from Canvas
- `utils/get_course_grades.py`: Script to export course grades to a CSV file

## Troubleshooting

If you encounter issues:

1. **Server Won't Start**
   - Check that your `.env` file exists and contains valid credentials
   - Verify the virtual environment path in `start_canvas_server.sh`
   - Ensure all dependencies are installed

2. **Authentication Errors**
   - Verify your Canvas API token is valid and not expired
   - Check that you have the necessary permissions in Canvas

3. **Connection Issues**
   - Ensure your Canvas API URL is correct
   - Check your internet connection
   - Verify your institution hasn't restricted API access

4. **Debugging**
   - Check the server logs in the Claude Desktop console
   - Try running the server manually to see error output

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

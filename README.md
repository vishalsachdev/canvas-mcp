# Canvas MCP Server



This repository contains a Message Control Protocol (MCP) server implementation for interacting with the Canvas Learning Management System API. The server is designed to work with Claude Desktop and potentially other MCP clients.

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

The server provides the following tools for Canvas LMS interaction:

### Course Management
- `list_courses`: List all courses for the authenticated user
- `get_course_details`: Get detailed information about a specific course
- `summarize_course`: Generate a comprehensive summary of a course

### Assignments
- `list_assignments`: List all assignments for a course
- `get_assignment_details`: Get detailed information about a specific assignment
- `get_assignment_description`: Get the full description of an assignment

### Submissions
- `list_submissions`: List all submissions for a specific assignment

### Users
- `list_users`: List all users enrolled in a course

### Pages
- `list_pages`: List all pages in a course with filtering and sorting options
- `get_page_details`: Get detailed information about a specific page
- `get_page_content`: Get the full content body of a specific page
- `get_front_page`: Get the front page content for a course
- `get_page_revisions`: Get the revision history for a specific page

### Modules
- `list_module_items`: List items within a specific module (including pages, assignments, etc.)

### Content Overview
- `get_course_content_overview`: Get a comprehensive overview of course content including pages and modules

### Announcements
- `list_announcements`: List all announcements for a course with scheduling status
- `create_announcement`: Create new announcements (immediate posting only)
- `create_scheduled_discussion`: Create scheduled discussion topics (workaround for announcement scheduling)

### Resources
- `get_course_syllabus`: Get the syllabus for a course
- `get_course_modules`: Get all modules for a course
- `page-content`: Direct access to page content via URI
- `course-front-page`: Direct access to course front page content

## Usage with Claude Desktop

This MCP server is designed to work seamlessly with Claude Desktop:

1. Claude Desktop will automatically start the server when needed
2. You'll see the Canvas API tools in the Claude Desktop interface (hammer icon 🔨)
3. You can ask Claude to perform Canvas operations like "Show me my courses" or "Get the syllabus for my Biology course"

For manual testing, you can start the server directly:
```bash
./start_canvas_server.sh
```

## Technical Details

### Server Implementation

The server uses:
- `fastmcp`: A Python library for building MCP servers
- `httpx`: For asynchronous HTTP requests to the Canvas API
- Caching mechanisms to improve performance for course lookups

The main implementation file is `canvas_server_cached.py`, which provides:
- Efficient caching of course information
- Pagination handling for Canvas API requests
- Error handling and reporting
- Support for both course IDs and course codes


### Dependencies

The server requires the following Python packages:
- `httpx`: For HTTP requests
- `fastmcp`: For MCP server implementation
- `requests`: For some HTTP operations
- Other standard libraries for encoding and networking

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

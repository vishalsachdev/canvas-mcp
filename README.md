# Canvas MCP Server

<!--mcp-name: io.github.vishalsachdev/canvas-mcp-->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains a Model Context Protocol (MCP) server implementation for interacting with the Canvas Learning Management System API. The server is designed to work with Claude Desktop and other MCP-compatible clients.

> **Note**: Recently refactored to a modular architecture for better maintainability. The legacy monolithic implementation has been archived.

## Overview

The Canvas MCP Server bridges the gap between Claude Desktop and Canvas Learning Management System, providing **both students and educators** with an intelligent interface to their Canvas environment. Built on the Model Context Protocol (MCP), it enables natural language interactions with Canvas data.

### For Students 👨‍🎓
Get AI-powered assistance with:
- Tracking upcoming assignments and deadlines
- Monitoring your grades across all courses
- Managing peer review assignments
- Accessing course content and discussions
- Organizing your TODO list

**[→ Get Started as a Student](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/STUDENT_GUIDE.md)**

### For Educators 👨‍🏫
Enhance your teaching with:
- Assignment and grading management
- Student analytics and performance tracking
- Discussion and peer review facilitation
- **FERPA-compliant** student data handling
- Bulk messaging and communication tools

**[→ Get Started as an Educator](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/EDUCATOR_GUIDE.md)**

## 🔒 Privacy & Data Protection

### For Educators: FERPA Compliance

Complete FERPA compliance through systematic data anonymization when working with student data:

- **Source-level data anonymization** converts real names to consistent anonymous IDs (Student_xxxxxxxx)
- **Automatic email masking** and PII filtering from discussion posts and submissions
- **Local-only processing** with configurable privacy controls (`ENABLE_DATA_ANONYMIZATION=true`)
- **FERPA-compliant analytics**: Ask "Which students need support?" without exposing real identities
- **De-anonymization mapping tool** for faculty to correlate anonymous IDs with real students locally

All student data is anonymized **before** it reaches AI systems. See [Educator Guide](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/EDUCATOR_GUIDE.md) for configuration details.

### For Students: Your Data Stays Private

- **Your data only**: Student tools access only your own Canvas data via Canvas API's "self" endpoints
- **Local processing**: Everything runs on your machine - no data sent to external servers
- **No tracking**: Your Canvas usage and AI interactions remain private
- **No anonymization needed**: Since you're only accessing your own data, there are no privacy concerns

## Prerequisites

- **Python 3.10+** - Required for modern features and type hints
- **Canvas API Access** - API token and institution URL
- **MCP Client** - Claude Desktop (recommended) or other MCP-compatible client

### Supported MCP Clients

Canvas MCP works with any application that supports the Model Context Protocol. Popular options include:

**Recommended:**
- **[Claude Desktop](https://claude.ai/download)** - Official Anthropic desktop app with full MCP support

**AI Coding Assistants:**
- **[Zed](https://zed.dev)** - High-performance code editor with built-in MCP support
- **[Cursor](https://cursor.sh)** - AI-first code editor
- **[Windsurf IDE](https://codeium.com/windsurf)** (by Codeium) - AI-powered development environment
- **[Continue](https://continue.dev)** - Open-source AI code assistant

**Development Platforms:**
- **[Replit](https://replit.com)** - Cloud-based coding platform with MCP integration
- **[Sourcegraph Cody](https://sourcegraph.com/cody)** - AI coding assistant with MCP support

**Enterprise:**
- **[Microsoft Copilot Studio](https://www.microsoft.com/microsoft-copilot/microsoft-copilot-studio)** - MCP support in enterprise environments

See the [official MCP clients list](https://modelcontextprotocol.io/clients) for more options.

> **Note**: While Canvas MCP is designed to work with any MCP client, setup instructions in this guide focus on Claude Desktop. Configuration for other clients may vary.

## Installation

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

> **Note for Students**: Some educational institutions restrict API token creation for students. If you see an error like "There is a limit to the number of access tokens you can create" or cannot find the token creation option, contact your institution's Canvas administrator or IT support department to request API access or assistance in creating a token.

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

**Student Tools** (New!)
- Personal assignment tracking and deadline management
- Grade monitoring across all courses
- TODO list and peer review management
- Submission status tracking

**Shared Tools** (Both Students & Educators)
1. **Course Tools** - List and manage courses, get detailed information, generate summaries with syllabus content
2. **Discussion & Announcement Tools** - Manage discussions, announcements, and replies
3. **Page & Content Tools** - Access pages, modules, and course content

**Educator Tools**
4. **Assignment Tools** - Handle assignments, submissions, and peer reviews with analytics
5. **Rubric Tools** - Full CRUD operations for rubrics with validation, association management, and grading
6. **User & Enrollment Tools** - Manage enrollments, users, and groups
7. **Analytics Tools** - View student analytics, assignment statistics, and progress tracking
8. **Messaging Tools** - Send messages and announcements to students

📖 [View Full Tool Documentation](tools/README.md) for detailed information about all available tools.

## 🚀 Code Execution API (New!)

The Canvas MCP now supports **code execution patterns** for maximum token efficiency when performing bulk operations.

### When to Use Each Approach

**Traditional Tool Calling** (for simple queries):
```
Ask Claude: "Show me my courses"
Ask Claude: "Get assignment details for assignment 123"
```
✅ Best for: Single queries, small datasets, quick lookups

**Code Execution** (for bulk operations):
```
Ask Claude: "Grade all 90 Jupyter notebook submissions"
Ask Claude: "Send reminders to all students who haven't submitted"
```
✅ Best for: Bulk processing, large datasets, complex analysis

### Token Savings Example

**Scenario**: Grading 90 Jupyter notebook submissions

| Approach | Token Usage | Efficiency |
|----------|-------------|-----------|
| **Traditional** | 1.35M tokens | Loads all submissions into context |
| **Code Execution** | 3.5K tokens | **99.7% reduction!** 🎉 |

### Example: Bulk Grading

```typescript
import { bulkGrade } from './canvas/grading/bulkGrade';

await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    // Analysis happens locally, not in Claude's context!
    const notebook = submission.attachments?.find(f =>
      f.filename.endsWith('.ipynb')
    );

    if (!notebook) return null; // Skip

    const hasErrors = analyzeNotebook(notebook.url);

    return hasErrors ? null : {
      points: 100,
      rubricAssessment: { "_8027": { points: 100 } },
      comment: "Great work! No errors."
    };
  }
});
```

### Discovering Available Tools

Use the `search_canvas_tools` MCP tool to discover what's available:

```typescript
// Search for grading tools
search_canvas_tools("grading", "signatures")

// List all tools
search_canvas_tools("", "names")

// Get full details
search_canvas_tools("bulk", "full")
```

### Code API File Structure

```
src/canvas_mcp/code_api/
├── client.ts              # Base MCP client bridge
├── index.ts               # Main entry point
└── canvas/
    ├── assignments/       # Assignment operations
    │   └── listSubmissions.ts
    ├── grading/          # Grading operations
    │   ├── gradeWithRubric.ts
    │   └── bulkGrade.ts  # ⭐ Bulk grading (99.7% token savings!)
    ├── discussions/      # Discussion operations
    ├── courses/          # Course operations
    └── communications/   # Messaging operations
```

### How It Works

1. **Discovery**: Use `search_canvas_tools` to find available operations
2. **Execution**: Claude reads TypeScript code API files and executes them locally
3. **Processing**: Data stays in execution environment (no context cost!)
4. **Results**: Only summaries flow back to Claude's context

📖 [View Bulk Grading Example](examples/bulk_grading_example.md) for a detailed walkthrough.

## Usage with MCP Clients

This MCP server works seamlessly with any MCP-compatible client:

1. **Automatic Startup**: MCP clients start the server when needed
2. **Tool Integration**: Canvas tools appear in your AI assistant's interface
3. **Natural Language**: Interact naturally with prompts like:

**Students:**
- *"What assignments do I have due this week?"*
- *"Show me my current grades"*
- *"What peer reviews do I need to complete?"*
- *"Have I submitted everything for BADM 350?"*

**Educators:**
- *"Which students haven't submitted the latest assignment?"*
- *"Create an announcement about tomorrow's exam"*
- *"Show me peer review completion analytics"*

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
│       │   ├── discovery.py   # Code API tool discovery (NEW!)
│       │   └── other_tools.py # Misc tools
│       ├── code_api/          # Code execution API (NEW!)
│       │   ├── client.ts      # MCP client bridge
│       │   └── canvas/        # Canvas operations
│       │       ├── grading/   # Bulk grading (99.7% token savings!)
│       │       ├── courses/   # Course operations
│       │       └── ...        # Other modules
│       └── resources/         # MCP resources
├── examples/                 # Usage examples (NEW!)
└── docs/                     # Documentation
```

## Documentation

- **[Tool Documentation](https://github.com/vishalsachdev/canvas-mcp/blob/main/tools/README.md)** - Complete reference for all available tools
- **[Pages Implementation Guide](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/PAGES_IMPLEMENTATION.md)** - Comprehensive Pages feature guide
- **[Course Documentation Template](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/course_documentation_prompt_template.md)** - Hybrid approach for efficient course documentation
- **[Development Guide](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/CLAUDE.md)** - Architecture details and development reference
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

For contributors, see the [Development Guide](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/CLAUDE.md) for detailed architecture and development reference.

## Troubleshooting

If you encounter issues:

1. **Server Won't Start** - Verify your [Configuration](#configuration) setup: `.env` file, virtual environment path, and dependencies
2. **Authentication Errors** - Check your Canvas API token validity and permissions
3. **Connection Issues** - Verify Canvas API URL correctness and network access
4. **Debugging** - Check Claude Desktop console logs or run server manually for error output

## Security & Privacy Features

### API Security
- Your Canvas API token grants access to your Canvas account
- Never commit your `.env` file to version control
- The server runs locally on your machine - no external data transmission
- Consider using a token with limited permissions if possible

### Privacy Controls (Educators Only)

Educators working with student data can enable FERPA-compliant anonymization:

```bash
# In your .env file
ENABLE_DATA_ANONYMIZATION=true  # Anonymizes student names/emails before AI processing
ANONYMIZATION_DEBUG=true        # Debug anonymization (optional)
```

Students don't need anonymization since they only access their own data.

For detailed privacy configuration, see:
- **[Educator Guide](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/EDUCATOR_GUIDE.md)** - FERPA compliance and anonymization
- **[Student Guide](https://github.com/vishalsachdev/canvas-mcp/blob/main/docs/STUDENT_GUIDE.md)** - Privacy information for students

## Publishing to MCP Registry

This server is published to the [Model Context Protocol Registry](https://registry.modelcontextprotocol.io/) for easy installation.

### Automated Publishing (Recommended)

Publishing is automated via GitHub Actions:

1. **Prepare a release**:
   ```bash
   # Update version in pyproject.toml
   # Update CHANGELOG if applicable
   git commit -am "chore: bump version to X.Y.Z"
   git push
   ```

2. **Create and push a version tag**:
   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. **Automated workflow**:
   - Runs tests
   - Builds Python package
   - Publishes to PyPI
   - Publishes to MCP Registry using GitHub OIDC

### Prerequisites for Publishing

- **PyPI Account**: Create account at [pypi.org](https://pypi.org)
- **Trusted Publisher Setup** (recommended, no tokens needed):
  1. Visit [PyPI Trusted Publishers](https://pypi.org/manage/account/publishing/)
  2. Add a "pending publisher" for your repository:
     - **Owner**: `vishalsachdev`
     - **Repository**: `canvas-mcp`
     - **Workflow**: `publish-mcp.yml`
     - **Environment**: (leave blank)
  3. This reserves the package name and enables tokenless publishing

**Alternative**: Use API token (legacy method - not recommended):
- Generate token at PyPI → Account Settings → API tokens
- Add as `PYPI_API_TOKEN` secret in repository settings
- Update workflow to use `password: ${{ secrets.PYPI_API_TOKEN }}`

### Manual Publishing (Alternative)

For manual publishing:

```bash
# Install MCP Publisher
curl -fsSL https://modelcontextprotocol.io/install.sh | sh

# Login using GitHub
mcp-publisher login github

# Publish server
mcp-publisher publish
```

### Registry Validation

The `server.json` configuration is automatically validated against the MCP schema during CI/CD. To validate locally:

```bash
# Download schema
curl -s https://registry.modelcontextprotocol.io/v0/server.schema.json -o /tmp/mcp-schema.json

# Validate (requires jsonschema CLI)
pip install jsonschema
jsonschema -i server.json /tmp/mcp-schema.json
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

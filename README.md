# Canvas MCP Server

<!--mcp-name: io.github.vishalsachdev/canvas-mcp-->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://img.shields.io/badge/pypi-v1.0.3-blue)](https://pypi.org/project/canvas-mcp/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)
[![Canvas API](https://img.shields.io/badge/Canvas-API%20v1-orange.svg)](https://canvas.instructure.com/doc/api/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

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

## Quick Start

Get up and running in 5 minutes:

```bash
# 1. Install dependencies
pip install uv
uv pip install -e .

# 2. Configure environment
cp env.template .env
# Edit .env with your Canvas API token and URL

# 3. Test connection
canvas-mcp-server --test

# 4. Add to Claude Desktop config
# See detailed setup below
```

> **Visual Walkthrough**: See screenshots and GIFs in our [Visual Setup Guide](#visual-setup-guide) for step-by-step instructions.

## Feature Comparison

| Feature | Students | Educators | Notes |
|---------|----------|-----------|-------|
| Assignment Tracking | ✓ | ✓ | Students: personal view; Educators: class-wide |
| Grade Monitoring | ✓ | ✓ | Students: own grades; Educators: class analytics |
| Peer Review Management | ✓ | ✓ | Students: track TODO; Educators: analytics & reminders |
| Discussion Forums | ✓ | ✓ | Students: read & post; Educators: moderate & analyze |
| Course Content Access | ✓ | ✓ | Pages, announcements, syllabus |
| Rubric Management | - | ✓ | Create, edit, associate with assignments |
| Student Analytics | - | ✓ | Performance tracking, at-risk identification |
| Bulk Grading | - | ✓ | Token-efficient bulk operations (99.7% savings) |
| Messaging & Reminders | - | ✓ | Automated student communications |
| Data Anonymization | - | ✓ | FERPA-compliant student data handling |
| Code Execution API | ✓ | ✓ | For advanced bulk operations |

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

## Visual Setup Guide

> **Note for Maintainers**: Add screenshots/GIFs in this section to enhance documentation:
> - Screenshot: Canvas API token creation page
> - Screenshot: Claude Desktop configuration file location (macOS/Windows/Linux)
> - GIF: Complete installation process from start to finish
> - Screenshot: Successful test output from `canvas-mcp-server --test`
> - GIF: Example of using Canvas MCP in Claude Desktop
> - Screenshot: Example tool usage showing the 🔨 hammer icon

To contribute visual assets, place them in `docs/images/` and update this section with:
```markdown
![Token Creation](docs/images/token-creation.png)
![Claude Config](docs/images/claude-config.png)
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

**Developer Tools**
9. **Discovery Tools** - Search and explore available code execution API operations with `search_canvas_tools`

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

### Example: Bulk Discussion Grading

Grade discussion posts with initial post + peer review requirements:

```typescript
import { bulkGradeDiscussion } from './canvas/discussions/bulkGradeDiscussion';

// Preview grades first (dry run)
await bulkGradeDiscussion({
  courseIdentifier: "60365",
  topicId: "990001",
  criteria: {
    initialPostPoints: 10,      // Points for initial post
    peerReviewPointsEach: 5,    // Points per peer review
    requiredPeerReviews: 2,     // Must review 2 peers
    maxPeerReviewPoints: 10     // Cap at 10 pts for reviews
  },
  dryRun: true  // Preview first!
});

// Then apply grades
await bulkGradeDiscussion({
  courseIdentifier: "60365",
  topicId: "990001",
  assignmentId: "1234567",  // Required to write grades
  criteria: {
    initialPostPoints: 10,
    peerReviewPointsEach: 5,
    requiredPeerReviews: 2,
    maxPeerReviewPoints: 10
  },
  dryRun: false
});
```

**Features:**
- Automatically analyzes initial posts vs peer reviews
- Configurable grading criteria with point allocation
- Optional late penalties with customizable deadline
- Dry run mode to preview grades before applying
- Concurrent processing with rate limiting
- Returns comprehensive participation analytics

### Discovering Available Tools

The Canvas MCP Server includes a **`search_canvas_tools`** MCP tool that helps you discover and explore available code execution API operations. This tool searches through the TypeScript code API files and returns information about available Canvas operations.

**Tool Parameters:**
- `query` (string, optional): Search term to filter tools by keyword (e.g., "grading", "assignment", "discussion"). Empty string returns all available tools.
- `detail_level` (string, optional): Controls how much information to return. Options:
  - `"names"`: Just file paths (most efficient for quick lookups)
  - `"signatures"`: File paths + function signatures + descriptions (recommended, default)
  - `"full"`: Complete file contents (use sparingly for detailed inspection)

**Example Usage:**

Ask Claude in natural language:
- *"Search for grading tools in the code API"*
- *"What bulk operations are available?"*
- *"Show me all code API tools"*

Or use directly via MCP:
```typescript
// Search for grading-related tools with signatures
search_canvas_tools("grading", "signatures")

// List all available tools (names only)
search_canvas_tools("", "names")

// Get full implementation details for bulk operations
search_canvas_tools("bulk", "full")

// Find discussion-related operations
search_canvas_tools("discussion", "signatures")
```

**Returns:**
JSON response with:
- `query`: The search term used
- `detail_level`: The detail level requested
- `count`: Number of matching tools found
- `tools`: Array of matching tools with requested detail level

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
    │   ├── listDiscussions.ts
    │   ├── postEntry.ts
    │   └── bulkGradeDiscussion.ts  # ⭐ Bulk discussion grading
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
│       │   ├── student_tools.py # Student-specific tools
│       │   ├── messaging.py   # Communication tools
│       │   ├── discovery.py   # Code API tool discovery (NEW!)
│       │   └── ...            # Other tool modules
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

### Common Issues and Solutions

#### Installation & Setup

**Q: Server won't start or shows "command not found"**
- **Solution**: Ensure you ran `uv pip install -e .` in the canvas-mcp directory
- Verify your Python version: `python --version` (must be 3.10+)
- Try reinstalling: `uv pip uninstall canvas-mcp && uv pip install -e .`

**Q: "ModuleNotFoundError" or import errors**
- **Solution**: Make sure you're using the correct Python environment
- Reinstall dependencies: `uv pip install -e .`
- Check your virtual environment is activated if you're using one

**Q: Claude Desktop doesn't show Canvas tools**
- **Solution**:
  1. Verify your `claude_desktop_config.json` is in the correct location
  2. Restart Claude Desktop completely (Quit and reopen)
  3. Check the command path is correct: `"command": "canvas-mcp-server"`
  4. Look for errors in Claude Desktop logs (Developer → View Logs)

#### Authentication & Connection

**Q: "Authentication failed" or 401 errors**
- **Solution**:
  - Verify your Canvas API token is correct in `.env`
  - Check the token hasn't expired (some institutions have expiration policies)
  - Ensure the token has appropriate permissions
  - Generate a new token if needed: Canvas → Account → Settings → New Access Token

**Q: "Connection refused" or timeout errors**
- **Solution**:
  - Verify your `CANVAS_API_URL` is correct in `.env`
  - Should be: `https://canvas.youruniversity.edu/api/v1`
  - Check your network connection
  - Verify you can access Canvas in your browser
  - Some institutions require VPN - ensure you're connected if needed

**Q: Canvas API token creation restricted (students)**
- **Solution**: Some institutions limit API access for students
  - Contact your Canvas administrator or IT support
  - Request API access for educational purposes
  - Provide this project's GitHub URL as reference

#### Tool Usage

**Q: "No courses found" or empty results**
- **Solution**:
  - Verify you're enrolled in courses for the current term
  - For students: Check if your institution allows API access to course data
  - For educators: Ensure you have instructor/TA role in courses
  - Try `include_concluded=true` parameter for past courses

**Q: Tools returning "Permission denied" errors**
- **Solution**:
  - Student tools require student enrollment
  - Educator tools require instructor/TA permissions
  - Check your Canvas role in the affected course
  - Some features may be restricted by your institution

**Q: Slow response times or timeouts**
- **Solution**:
  - Canvas API may be slow during peak usage
  - Try requesting smaller date ranges
  - Use pagination for large result sets
  - Consider using code execution API for bulk operations

#### Privacy & Anonymization (Educators)

**Q: Student names not anonymized**
- **Solution**:
  - Set `ENABLE_DATA_ANONYMIZATION=true` in `.env`
  - Restart the Canvas MCP server
  - Check `local_maps/` folder is created
  - Set `ANONYMIZATION_DEBUG=true` to troubleshoot

**Q: Cannot find mapping file to de-anonymize**
- **Solution**:
  - Mapping files are in `local_maps/` directory
  - Named by course code: `course_XXXX_mapping.csv`
  - Generated when anonymization is first used
  - Keep this folder secure and never commit to git

#### Code Execution API

**Q: Code execution not working or showing errors**
- **Solution**:
  - Ensure TypeScript files are accessible
  - Check environment variables are passed to execution context
  - Try the traditional tool approach instead
  - Review error messages for specific issues

**Q: "search_canvas_tools" returns no results**
- **Solution**:
  - Check your search query is correct
  - Try empty string `""` to list all tools
  - Verify code_api directory structure is intact
  - Files may need to be TypeScript (.ts) not JavaScript

### Testing Your Setup

Run these commands to verify everything is working:

```bash
# Test Canvas API connection
canvas-mcp-server --test

# View your configuration
canvas-mcp-server --config

# Start server manually to see debug output
canvas-mcp-server
```

### Getting Help

Still having issues? Here's how to get support:

1. **Check Existing Issues**: [GitHub Issues](https://github.com/vishalsachdev/canvas-mcp/issues)
2. **Search Documentation**: Review [Student Guide](docs/STUDENT_GUIDE.md) or [Educator Guide](docs/EDUCATOR_GUIDE.md)
3. **Open an Issue**: Provide:
   - Your OS and Python version
   - Canvas MCP version (`pip show canvas-mcp`)
   - Error messages (with sensitive data removed)
   - Steps to reproduce the issue
4. **Check MCP Registry**: [Model Context Protocol Registry](https://registry.modelcontextprotocol.io/)

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
# In your .env file
MCP_DEBUG=true
ANONYMIZATION_DEBUG=true  # For privacy debugging (educators only)
```

## Security & Privacy Features

### API Security
- Your Canvas API token grants access to your Canvas account
- Automatic token validation on startup
- Never commit your `.env` file to version control
- The server runs locally on your machine - no external data transmission
- Consider using a token with limited permissions if possible
- Built-in rate limiting protects against API abuse

### Privacy Controls (Educators Only)

Educators working with student data can enable FERPA-compliant anonymization:

```bash
# In your .env file
ENABLE_DATA_ANONYMIZATION=true  # Anonymizes student names/emails before AI processing
ANONYMIZATION_DEBUG=true        # Debug anonymization (optional)
```

Students don't need anonymization since they only access their own data.

### Security Features

Canvas MCP includes comprehensive security controls:

- **Input Validation**: All user inputs are validated and sanitized
- **PII Protection**: Automatic filtering of sensitive data in logs
- **Rate Limiting**: Prevents API abuse and resource exhaustion
- **Error Safety**: Production errors don't expose internal details
- **Token Security**: Format validation and permission verification
- **Dependency Scanning**: Automated vulnerability detection in dependencies

### Security Documentation

For comprehensive security information:
- **[SECURITY.md](SECURITY.md)** - Vulnerability disclosure and security policy
- **[Security Guide](docs/SECURITY_GUIDE.md)** - Best practices and configuration
- **[Educator Guide](docs/EDUCATOR_GUIDE.md)** - FERPA compliance and anonymization
- **[Student Guide](docs/STUDENT_GUIDE.md)** - Privacy information for students

### Reporting Security Issues

If you discover a security vulnerability, please follow our responsible disclosure process outlined in [SECURITY.md](SECURITY.md). Do NOT open a public issue for security vulnerabilities.

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

# Canvas MCP Server

<!--mcp-name: io.github.vishalsachdev/canvas-mcp-->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

This repository contains a Model Context Protocol (MCP) server implementation for interacting with the Canvas Learning Management System API. The server is designed to work with Claude Desktop and other MCP-compatible clients.

> **Note**: Recently refactored to a modular architecture for better maintainability. The legacy monolithic implementation has been archived.

## For AI Agents

<!--
  INLINE AGENT GUIDE: Intentionally duplicates AGENTS.md content.
  WHY: Agents often can't fetch raw.githubusercontent.com or GitHub blob pages.
  MAINTENANCE: When updating tools, also update AGENTS.md (source of truth).
  See docs/CLAUDE.md "Documentation Maintenance" for full guidelines.
-->

Canvas MCP provides **40+ tools** for interacting with Canvas LMS. Tools are organized by user type:

<details>
<summary><strong>Student Tools</strong> (click to expand)</summary>

| Tool | Purpose | Example Prompt |
|------|---------|----------------|
| `get_my_upcoming_assignments` | Due dates for next N days | "What's due this week?" |
| `get_my_todo_items` | Canvas TODO list | "Show my TODO list" |
| `get_my_submission_status` | Submitted vs missing | "Have I submitted everything?" |
| `get_my_course_grades` | Current grades | "What are my grades?" |
| `get_my_peer_reviews_todo` | Pending peer reviews | "What peer reviews do I need to do?" |

</details>

<details>
<summary><strong>Educator Tools</strong> (click to expand)</summary>

| Tool | Purpose | Example Prompt |
|------|---------|----------------|
| `list_assignments` | All assignments in course | "Show assignments in BADM 350" |
| `list_submissions` | Student submissions | "Who submitted Assignment 3?" |
| `bulk_grade_submissions` | Grade multiple at once | "Grade these 10 students" |
| `get_assignment_analytics` | Performance stats | "Show analytics for Quiz 2" |
| `send_conversation` | Message students | "Message students who haven't submitted" |
| `create_announcement` | Post announcements | "Announce the exam date change" |

</details>

<details>
<summary><strong>Shared Tools</strong> (click to expand)</summary>

| Tool | Purpose |
|------|---------|
| `list_courses` | All enrolled courses |
| `get_course_details` | Course info + syllabus |
| `list_discussion_topics` | Discussion forums |
| `list_discussion_entries` | Posts in a discussion |
| `post_discussion_entry` | Add a post |

</details>

<details>
<summary><strong>Developer Tools</strong> (for bulk operations)</summary>

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `search_canvas_tools` | Discover code API operations | Finding available bulk ops |
| `execute_typescript` | Run TypeScript locally | 30+ items, custom logic, 99.7% token savings |

**Decision tree:** Simple query → MCP tools. Batch grading (10+) → `bulk_grade_submissions`. Complex bulk (30+) → `execute_typescript`.

</details>

### Quick Reference

**Course identifiers:** Canvas ID (`12345`), course code (`badm_350_120251_246794`), or SIS ID

**Cannot do:** Create/delete courses, modify course settings, access other users' data

**Rate limits:** ~700 requests/10 min. Use `max_concurrent=5` for bulk operations.

**Full documentation:** [AGENTS.md](AGENTS.md) | [tools/TOOL_MANIFEST.json](tools/TOOL_MANIFEST.json) | [tools/README.md](tools/README.md)

## Overview

The Canvas MCP Server bridges the gap between Claude Desktop and Canvas Learning Management System, providing **both students and educators** with an intelligent interface to their Canvas environment. Built on the Model Context Protocol (MCP), it enables natural language interactions with Canvas data.

## 🎉 Latest Release: v1.0.5

**Released:** December 25, 2025 | **[View Full Release Notes](https://github.com/vishalsachdev/canvas-mcp/releases/tag/v1.0.5)**

### What's New in v1.0.5
- **🎯 Claude Code Skills** - One-command workflows for common tasks
  - `/canvas-morning-check` - Educator course health check
  - `/canvas-week-plan` - Student weekly assignment planner
- **🌐 GitHub Pages Website** - Beautiful documentation site at [vishalsachdev.github.io/canvas-mcp](https://vishalsachdev.github.io/canvas-mcp/)
- **📖 HTML Documentation** - Full guides for students, educators, and developers

### Previous Release (v1.0.4)
- **🚀 Code Execution Environment** - Execute custom TypeScript code for token-efficient bulk operations (99.7% token savings)
- **📊 Bulk Operations** - `bulk_grade_submissions`, `bulk_grade_discussions`, `search_canvas_tools`
- **MCP 2.14 Compliance** - Production-ready features and structured logging

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

## 🎯 Claude Code Skills

Pre-built workflows that combine multiple tools into one-command actions. Skills work with [Claude Code](https://claude.ai/code) (CLI).

| Skill | For | What It Does |
|-------|-----|--------------|
| `/canvas-morning-check` | Educators | Course health check: submission rates, struggling students, grade distribution, upcoming deadlines |
| `/canvas-week-plan` | Students | Weekly planner: all due dates, submission status, grades, peer reviews across courses |

**Example usage:**
```
You: /canvas-morning-check CS 101
Claude: [Generates comprehensive course status report]

You: /canvas-week-plan
Claude: [Shows prioritized weekly assignment plan]
```

Skills are located in `.claude/skills/` and can be customized for your workflow.

**Want a custom skill?** [Submit a request](https://github.com/vishalsachdev/canvas-mcp/issues/new?labels=skill-request&title=[Skill%20Request]) describing your repetitive workflow!

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
# (Recommended) Use a dedicated virtualenv so the MCP binary is in a stable location
python3 -m venv .venv
. .venv/bin/activate

# Install the package editable
pip install -e .
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
      "command": "/Users/vishal/code/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

> Tip: Pointing Claude at the absolute path to your virtualenv binary avoids issues with shell-specific PATH entries (e.g., pyenv shims) that can cause `ModuleNotFoundError: No module named 'canvas_mcp'` when Claude launches the server.

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
5. **Rubric Tools** - Full CRUD operations for rubrics with validation, association management, and grading (including `bulk_grade_submissions` for efficient batch grading)
6. **User & Enrollment Tools** - Manage enrollments, users, and groups
7. **Analytics Tools** - View student analytics, assignment statistics, and progress tracking
8. **Messaging Tools** - Send messages and announcements to students

**Developer Tools**
9. **Discovery Tools** - Search and explore available code execution API operations with `search_canvas_tools` and `list_code_api_modules`
10. **Code Execution Tools** - Execute TypeScript code with `execute_typescript` for token-efficient bulk operations (99.7% token savings!)

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

**Bulk Grade Submissions Tool** (for batch grading with predefined grades):
```
Ask Claude: "Grade these 10 students with their specific rubric scores"
```
✅ Best for: Batch grading when you already have the grades/scores, concurrent processing

**Code Execution** (for bulk operations with custom logic):
```
Ask Claude: "Grade all 90 Jupyter notebook submissions by analyzing each notebook"
Ask Claude: "Send reminders to all students who haven't submitted"
```
✅ Best for: Bulk processing with custom analysis logic, large datasets, complex conditions

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

### Code Execution Security

The `execute_typescript` tool provides powerful capabilities but requires proper security considerations:

**Security Features:**
- **Temporary File Isolation**: Code executes in temporary files that are deleted after completion
- **Environment Isolation**: Inherits only Canvas API credentials from server environment
- **Timeout Protection**: Configurable timeout prevents runaway processes (default: 120 seconds)
- **Local Execution**: All code runs on your local machine with no external transmission

**Best Practices:**
- **Trusted Environment Required**: Only use code execution in environments you control
- **Review Generated Code**: Always review TypeScript code before execution, especially for bulk operations
- **Resource Monitoring**: Monitor system resources when processing large datasets
- **Timeout Configuration**: Adjust timeout values based on expected operation duration
- **Production Use**: Consider implementing additional resource limits (memory, CPU) in production environments

**What Code Execution Has Access To:**
- Canvas API credentials from your `.env` file
- All TypeScript modules in `src/canvas_mcp/code_api/`
- Standard Node.js modules and npm packages
- File system access within the execution context

**Limitations:**
- Cannot access files outside the repository directory
- Cannot make network requests beyond Canvas API (unless explicitly coded)
- Subject to Node.js and system resource constraints

For technical implementation details, see `src/canvas_mcp/tools/code_execution.py:67-70`.

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

### Quick Start Examples

New to Canvas MCP? Check out these practical guides:

- **[Student Quick Start](examples/student_quickstart.md)** - Common tasks for students
- **[Educator Quick Start](examples/educator_quickstart.md)** - Essential workflows for teachers
- **[Real-World Workflows](examples/real_world_workflows.md)** - Complete scenarios combining multiple features
- **[Common Issues & Solutions](examples/common_issues.md)** - Troubleshooting guide
- **[Bulk Grading Example](examples/bulk_grading_example.md)** - Token-efficient batch grading

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
│       │   ├── discovery.py   # Code API tool discovery
│       │   ├── code_execution.py # TypeScript code execution (NEW!)
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

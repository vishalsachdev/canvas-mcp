# Canvas MCP Server

<!--mcp-name: io.github.vishalsachdev/canvas-mcp-->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![skills.sh](https://img.shields.io/badge/skills.sh-canvas--mcp-blue)](https://skills.sh)

MCP server for Canvas LMS with **90+ tools** and **8 agent skills**. Works with Claude Desktop, Cursor, Codex, Windsurf, and [40+ other agents](https://skills.sh).

```bash
npx skills add vishalsachdev/canvas-mcp
```

> **Note**: Recently refactored to a modular architecture for better maintainability. The legacy monolithic implementation has been archived.

## For AI Agents

<!--
  INLINE AGENT GUIDE: Intentionally duplicates AGENTS.md content.
  WHY: Agents often can't fetch raw.githubusercontent.com or GitHub blob pages.
  MAINTENANCE: When updating tools, also update AGENTS.md (source of truth).
  See CLAUDE.md "Documentation Maintenance" for full guidelines.
-->

Canvas MCP provides **90+ tools** for interacting with Canvas LMS. Tools are organized by user type:

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
| `create_assignment` | Create new assignment | "Create an assignment due Jan 26 with online text submission" |
| `update_assignment` | Update existing assignment | "Change the due date for Assignment 3 to Feb 15" |
| `list_submissions` | Student submissions | "Who submitted Assignment 3?" |
| `bulk_grade_submissions` | Grade multiple at once | "Grade these 10 students" |
| `get_assignment_analytics` | Performance stats | "Show analytics for Quiz 2" |
| `send_conversation` | Message students | "Message students who haven't submitted" |
| `create_announcement` | Post announcements | "Announce the exam date change" |
| **Module Management** | | |
| `create_module` | Create course module | "Create a module for Week 5" |
| `update_module` | Update module settings | "Rename the midterm module" |
| `add_module_item` | Add content to module | "Add the syllabus page to Week 1" |
| `delete_module` | Remove a module | "Delete the empty test module" |
| **Page & Content** | | |
| `create_page` | Create course page | "Create a page for office hours" |
| `edit_page_content` | Update page content | "Update the syllabus page" |
| `update_page_settings` | Publish/unpublish pages | "Publish all Week 3 pages" |
| `bulk_update_pages` | Batch page operations | "Unpublish all draft pages" |
| **File Management** | | |
| `upload_course_file` | Upload local file to Canvas | "Upload syllabus.pdf to the course" |

</details>

<details>
<summary><strong>Shared Tools</strong> (click to expand)</summary>

| Tool | Purpose |
|------|---------|
| `list_courses` | All enrolled courses |
| `get_course_details` | Course info + syllabus |
| `list_pages` | Course pages |
| `get_page_content` | Read page content |
| `list_modules` | List course modules |
| `list_module_items` | Items within a module |
| `list_discussion_topics` | Discussion forums |
| `list_discussion_entries` | Posts in a discussion |
| `post_discussion_entry` | Add a discussion post |
| `reply_to_discussion_entry` | Reply to a post |

</details>

<details>
<summary><strong>Learning Designer Tools</strong> (course design & QC)</summary>

| Tool | Purpose | Example Prompt |
|------|---------|----------------|
| `get_course_structure` | Full module→items tree as JSON | "Show me the structure of CS 101" |
| `scan_course_content_accessibility` | WCAG violation scanner | "Audit accessibility for BADM 350" |
| `fetch_ufixit_report` | Institutional accessibility report | "Pull the UFIXIT report for this course" |
| `parse_ufixit_violations` | Extract structured violations | "Parse the UFIXIT violations" |
| `format_accessibility_summary` | Readable violation report | "Summarize the accessibility issues" |

**Skills:** `canvas-course-qc` (pre-semester audit), `canvas-accessibility-auditor` (WCAG compliance), `canvas-course-builder` (scaffold courses from specs/templates).

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

**Cannot do:** Create/delete courses, modify course settings, access other users' data, create/update rubrics (use Canvas UI)

**Rate limits:** ~700 requests/10 min. Use `max_concurrent=5` for bulk operations.

**Full documentation:** [AGENTS.md](AGENTS.md) | [tools/TOOL_MANIFEST.json](tools/TOOL_MANIFEST.json) | [tools/README.md](tools/README.md)

## Overview

The Canvas MCP Server bridges the gap between AI assistants and Canvas Learning Management System, providing **both students and educators** with an intelligent interface to their Canvas environment. Built on the Model Context Protocol (MCP), it enables natural language interactions with Canvas data through any MCP-compatible client.

## Latest Release: v1.1.0

**Released:** February 28, 2026 | **[View Full Release Notes](https://github.com/vishalsachdev/canvas-mcp/releases/tag/v1.1.0)**

- **Generic Distribution** — Removed institution-specific defaults for universal use
- **Agent Skills** — 8 workflow skills for 40+ coding agents via [skills.sh](https://skills.sh)
- **Learning Designer Tools** — New `get_course_structure` tool + 3 skills for course QC, accessibility auditing, and course scaffolding
- **File Management** — `download_course_file` and `list_course_files` tools (community PR #75)
- **`delete_page` tool** — Title-match safety check for page deletion
- **Codebase Refactor** — Type dispatch extraction, structured logging, reduced complexity
- **Python 3.14 Fix** — Resolved asyncio shutdown crash

<details>
<summary>Previous releases</summary>

**v1.0.8** — Security Hardening (PII sanitization, audit logging, sandbox-by-default), Ruff linting, 235+ tests

**v1.0.7** — Assignment Update Tool (`update_assignment`), complete CRUD, 9 tests

**v1.0.6** — Module Management (7 tools), Page Settings (2 tools), 235+ tests

**v1.0.5** — Claude Code Skills, GitHub Pages site

**v1.0.4** — Code Execution API (99.7% token savings), Bulk Operations, MCP 2.14 compliance

</details>

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

### For Learning Designers 🎨
AI-powered course design and quality assurance:
- **Course scaffolding** — Build entire course structures from specs, templates, or by cloning existing courses
- **Quality audits** — Pre-semester QC checks for structure, content, publishing, and completeness
- **Accessibility compliance** — WCAG scanning, prioritized reports, guided remediation, and verification
- **Course structure analysis** — Full module→items tree in a single call for rapid course review

3 dedicated skills (`canvas-course-qc`, `canvas-accessibility-auditor`, `canvas-course-builder`) plus the `get_course_structure` tool.

## 🤖 Agent Skills

Pre-built workflow recipes that teach AI agents how to use Canvas MCP tools effectively. Available for **40+ coding agents** via [skills.sh](https://skills.sh), or as Claude Code-specific slash commands.

### Install via skills.sh (Any Agent)

```bash
npx skills add vishalsachdev/canvas-mcp
```

This launches an interactive picker to install skills into your agent of choice (Claude Code, Cursor, Codex, OpenCode, Cline, Zed, and [many more](https://skills.sh)).

| Skill | For | What It Does |
|-------|-----|--------------|
| `canvas-week-plan` | Students | Weekly planner: due dates, submission status, grades, peer reviews |
| `canvas-morning-check` | Educators | Course health dashboard: submission rates, struggling students, deadlines |
| `canvas-bulk-grading` | Educators | Grading decision tree: single → bulk → code execution with safety checks |
| `canvas-peer-review-manager` | Educators | Full peer review pipeline: analytics, quality analysis, reminders, reports |
| `canvas-discussion-facilitator` | Both | Discussion browsing, participation monitoring, replying, facilitation |
| `canvas-course-qc` | Learning Designers | Pre-semester quality audit: structure, content, publishing, completeness |
| `canvas-accessibility-auditor` | Learning Designers | WCAG scan, prioritized report, guided remediation, verification |
| `canvas-course-builder` | Learning Designers | Scaffold courses from specs, templates, or existing courses |

Install a specific skill:

```bash
npx skills add vishalsachdev/canvas-mcp -s canvas-week-plan
```

### Claude Code Slash Commands

If you use [Claude Code](https://claude.ai/code), the same workflows are also available as slash commands:

```
You: /canvas-morning-check CS 101
Claude: [Generates comprehensive course status report]

You: /canvas-week-plan
Claude: [Shows prioritized weekly assignment plan]
```

Claude Code skills are located in `.claude/skills/` and can be customized for your workflow.

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
- **MCP Client** - Any MCP-compatible client (Claude Desktop, Cursor, Zed, Windsurf, Continue, etc.)

### Supported MCP Clients

Works with any MCP-compatible client: [Claude Desktop](https://claude.ai/download), [Cursor](https://cursor.sh), [Zed](https://zed.dev), [Windsurf](https://codeium.com/windsurf), [Continue](https://continue.dev), [Replit](https://replit.com), [Copilot Studio](https://www.microsoft.com/microsoft-copilot/microsoft-copilot-studio), and [more](https://modelcontextprotocol.io/clients).

Canvas MCP is compliant with Canvas LMS API 2024-2026 requirements (User-Agent header, `per_page` pagination). Works with Canvas Cloud and self-hosted instances.

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

### 3. MCP Client Configuration

Canvas MCP works with any MCP-compatible client. Below are configuration examples for popular clients:

<details open>
<summary><strong>Claude Desktop</strong> (Most Popular)</summary>

**Configuration file location:**
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

**Configuration:**
```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

**Note**: Use the absolute path to your virtualenv binary to avoid issues with shell-specific PATH entries (e.g., pyenv shims).

</details>

<details>
<summary><strong>Cursor</strong></summary>

**Configuration file location:**
- **macOS/Linux**: `~/.cursor/mcp_config.json`
- **Windows**: `%USERPROFILE%\.cursor\mcp_config.json`

**Configuration:**
```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

</details>

<details>
<summary><strong>Zed</strong></summary>

**Configuration:** Add to Zed's `settings.json` (accessible via Settings menu)

```json
{
  "context_servers": {
    "canvas-api": {
      "command": {
        "path": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server",
        "args": []
      }
    }
  }
}
```

</details>

<details>
<summary><strong>Windsurf IDE</strong></summary>

**Configuration file location:**
- **macOS**: `~/Library/Application Support/Windsurf/mcp_config.json`
- **Windows**: `%APPDATA%\Windsurf\mcp_config.json`

**Configuration:**
```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

</details>

<details>
<summary><strong>Continue</strong></summary>

**Configuration:** Add to Continue's `config.json` (accessible via Continue settings)

```json
{
  "mcpServers": {
    "canvas-api": {
      "command": "/absolute/path/to/canvas-mcp/.venv/bin/canvas-mcp-server"
    }
  }
}
```

</details>

<details>
<summary><strong>Other MCP Clients</strong></summary>

For other MCP-compatible clients, the general pattern is:

1. Locate your client's MCP configuration file
2. Add a server entry with:
   - **Server name**: `canvas-api` (or any name you prefer)
   - **Command**: Full path to `canvas-mcp-server` binary
   - **Optional args**: Additional arguments if needed

Consult your client's MCP documentation for specific configuration format and file locations.

</details>

> **Windows users**: Replace forward slashes with backslashes in paths (e.g., `C:\Users\YourName\canvas-mcp\.venv\Scripts\canvas-mcp-server.exe`)

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
5. **Rubric Tools** - List rubrics, associate with assignments, and grade submissions (including `bulk_grade_submissions` for efficient batch grading). Note: Create/update rubrics via Canvas web UI due to API limitations.
6. **User & Enrollment Tools** - Manage enrollments, users, and groups
7. **Analytics Tools** - View student analytics, assignment statistics, and progress tracking
8. **Messaging Tools** - Send messages and announcements to students

**Developer Tools**
9. **Discovery Tools** - Search and explore available code execution API operations with `search_canvas_tools` and `list_code_api_modules`
10. **Code Execution Tools** - Execute TypeScript code with `execute_typescript` for token-efficient bulk operations (99.7% token savings!)

📖 [View Full Tool Documentation](tools/README.md) for detailed information about all available tools.

## Code Execution API

For bulk operations (30+ items), Canvas MCP supports **TypeScript code execution** with 99.7% token savings compared to traditional tool calling.

| Approach | Best For | Token Cost |
|----------|----------|------------|
| MCP tools | Simple queries, small datasets | Normal |
| `bulk_grade_submissions` | Batch grading 10-29 items | Low |
| `execute_typescript` | 30+ items, custom logic | **99.7% less** |

Use `search_canvas_tools` to discover available operations, then `execute_typescript` to run them locally. Code runs in a **secure sandbox by default** (network blocked, env filtered, resource limits).

<details>
<summary>Code execution examples and security details</summary>

### Bulk Grading Example

```typescript
import { bulkGrade } from './canvas/grading/bulkGrade';

await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    const notebook = submission.attachments?.find(f =>
      f.filename.endsWith('.ipynb')
    );
    if (!notebook) return null;
    return { points: 100, comment: "Great work!" };
  }
});
```

### Security Modes

| Mode | Config | What It Does |
|------|--------|-------------|
| Local sandbox (default) | None needed | Timeout 120s, memory 512MB, network blocked, env filtered |
| Container sandbox | `TS_SANDBOX_MODE=container` | Full filesystem isolation via Docker/Podman |
| No sandbox | `ENABLE_TS_SANDBOX=false` | Full local access (not recommended) |

See [Bulk Grading Example](examples/bulk_grading_example.md) for a detailed walkthrough.

</details>

## Usage

MCP clients start the server automatically. Just ask naturally:

- *"What's due this week?"* / *"Show my grades"* / *"What peer reviews do I need?"*
- *"Who hasn't submitted Assignment 3?"* / *"Send reminders to missing students"*

Quick start guides: [Student](examples/student_quickstart.md) | [Educator](examples/educator_quickstart.md) | [Real-World Workflows](examples/real_world_workflows.md) | [Troubleshooting](examples/common_issues.md)

## Documentation

- **[Tool Documentation](tools/README.md)** — Complete reference for all 90+ tools
- **[Student Guide](docs/STUDENT_GUIDE.md)** — Getting started as a student
- **[Educator Guide](docs/EDUCATOR_GUIDE.md)** — FERPA compliance and educator workflows
- **[Bulk Grading Example](examples/bulk_grading_example.md)** — Token-efficient batch grading walkthrough
- **[Development Guide](CLAUDE.md)** — Architecture and contributing

<details>
<summary>Technical details</summary>

Built on **FastMCP** with async `httpx`, `pydantic` validation, and `python-dotenv` configuration. Modern `src/` layout with `pyproject.toml`. Full type hints, connection pooling, smart pagination, and rate limiting. 290+ tests. `ruff` + `black` for code quality.

</details>

## Troubleshooting

If you encounter issues:

1. **Server Won't Start** - Verify your [Configuration](#configuration) setup: `.env` file, virtual environment path, and dependencies
2. **Authentication Errors** - Check your Canvas API token validity and permissions
3. **Connection Issues** - Verify Canvas API URL correctness and network access
4. **Debugging** - Check your MCP client's console logs (e.g., Claude Desktop's developer console) or run server manually for error output

## Security

Four layers of runtime security, all enabled by default:

| Layer | Default |
|-------|---------|
| PII sanitization in logs | `LOG_REDACT_PII=true` |
| Token validation on startup | Always on |
| Structured audit logging | Opt-in: `LOG_ACCESS_EVENTS=true` |
| Sandboxed code execution | `ENABLE_TS_SANDBOX=true` |

FERPA-compliant anonymization for educators: `ENABLE_DATA_ANONYMIZATION=true`. See [Educator Guide](docs/EDUCATOR_GUIDE.md) for details.

## Publishing

Published to [PyPI](https://pypi.org/project/canvas-mcp/), [MCP Registry](https://registry.modelcontextprotocol.io/), and [skills.sh](https://skills.sh) (agent skills). Releases are automated via GitHub Actions — tag a version (`git tag vX.Y.Z && git push origin vX.Y.Z`) and CI handles the rest.

## Contributing

Contributions are welcome! Feel free to:
- Submit issues for bugs or feature requests
- Create pull requests with improvements
- Share your use cases and feedback

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Created by [Vishal Sachdev](https://github.com/vishalsachdev)

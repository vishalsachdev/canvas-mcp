<p align="center">
  <img src="docs/canvas-mcp-header.png" alt="Canvas MCP — AI tools for Canvas LMS" width="800">
</p>

# Canvas MCP Server

<!--mcp-name: io.github.vishalsachdev/canvas-mcp-->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![skills.sh](https://img.shields.io/badge/skills.sh-canvas--mcp-blue)](https://skills.sh)

MCP server for Canvas LMS with **up to 101 tools** and **8 agent skills**. Designed for Claude Desktop, Cursor, Codex, Windsurf, and [40+ other agents](https://skills.sh); setup and capabilities vary by client.

```bash
npx skills add vishalsachdev/canvas-mcp
```

## For AI Agents

<!--
  INLINE AGENT GUIDE: Intentionally duplicates AGENTS.md content.
  WHY: Agents often can't fetch raw.githubusercontent.com or GitHub blob pages.
  MAINTENANCE: When updating tools, also update AGENTS.md (source of truth).
  See CLAUDE.md "Documentation Maintenance" for full guidelines.
-->

Canvas MCP provides **up to 101 tools** for interacting with Canvas LMS; the default profile registers fewer, and optional feature-gated tools can raise the total to 101. Tools are organized by user type:

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
| `scan_course_content_accessibility` | WCAG violation scanner (20 checks: headings, tables, links, contrast, alt text, captions, DesignPLUS) | "Audit accessibility for BADM 350" |
| `fetch_ufixit_report` | Institutional accessibility report | "Pull the UFIXIT report for this course" |
| `parse_ufixit_violations` | Extract structured violations | "Parse the UFIXIT violations" |
| `format_accessibility_summary` | Readable violation report | "Summarize the accessibility issues" |

**Skills:** `canvas-course-qc` (pre-semester audit), `canvas-accessibility-auditor` (WCAG-oriented review), `canvas-course-builder` (scaffold courses from specs/templates).

</details>

<details>
<summary><strong>Developer Tools</strong> (for bulk operations)</summary>

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `search_canvas_tools` | Discover MCP tools and code API operations | Finding available tools and bulk ops |
| `execute_typescript` | Run TypeScript locally | 30+ items, custom logic, local per-item processing |

**Decision tree:** Simple query → MCP tools. Batch grading (10+) → `bulk_grade_submissions`. Complex bulk (30+) → `execute_typescript`.

</details>

### Quick Reference

**Course identifiers:** Canvas ID (`12345`), course code (`badm_350_120251_246794`), or SIS ID

**Cannot do:** Create/delete courses, modify course settings, access other users' data

**Rate limits:** ~700 requests/10 min. Use `max_concurrent=5` for bulk operations.

**Full documentation:** [AGENTS.md](AGENTS.md) | [tools/TOOL_MANIFEST.json](tools/TOOL_MANIFEST.json) | [tools/README.md](tools/README.md)

## Overview

The Canvas MCP Server bridges the gap between AI assistants and Canvas Learning Management System, providing role-specific workflows for students, educators, learning designers, and developers. Built on the Model Context Protocol (MCP), it is designed for MCP-compatible clients; setup and supported capabilities vary by client.

## Latest Release: v1.12.0

**Released:** August 2026 | **[Full Changelog](./CHANGELOG.md)** | **[All Releases](https://github.com/vishalsachdev/canvas-mcp/releases)**

A safety release: every delete tool now asks first. **Four changes are breaking.** Each one's migration is a line long:

- **`delete_announcement` removed** → call `delete_announcement_with_confirmation` with the same arguments; it previews first, then deletes on the second call with the token ([#318](https://github.com/vishalsachdev/canvas-mcp/issues/318))
- **`dry_run` removed** from the three announcement delete tools → drop the argument; a call without `confirmation_token` is the dry run and deletes nothing. `bulk_delete_announcements` used to delete on the first call; it previews now ([#318](https://github.com/vishalsachdev/canvas-mcp/issues/318))
- **`confirmation_token` required on all seven delete tools** (`delete_announcement_with_confirmation`, `bulk_delete_announcements`, `delete_announcements_by_criteria`, `delete_page`, `delete_module`, `delete_module_item`, `delete_assignment_with_confirmation`) → call once with your normal arguments, show the preview, then call again with identical arguments plus the token from the `Confirmation token:` line. Tokens are single-use, expire in 5 minutes, and stop matching if the target or the arguments changed ([#318](https://github.com/vishalsachdev/canvas-mcp/issues/318)). Thanks [@zqian](https://github.com/zqian) for the request
- **Python 3.10 dropped** → `requires-python >= 3.11`; upgrade the interpreter, or pin `canvas-mcp<1.12` until you can ([#315](https://github.com/vishalsachdev/canvas-mcp/issues/315))

Also new: **`delete_assignment_with_confirmation`** (preview shows due date, points and whether submissions exist); **`ACCESSIBILITY_CHECKERS`** so institutions without UDOIT/UFIXIT can set `none` and drop the three UFIXIT tools while keeping the built-in scanner ([#325](https://github.com/vishalsachdev/canvas-mcp/issues/325), thanks [@jonespm](https://github.com/jonespm)); the **content migration** tools ([#309](https://github.com/vishalsachdev/canvas-mcp/issues/309)); and a **Skill Request** issue template ([#302](https://github.com/vishalsachdev/canvas-mcp/issues/302))

<details>
<summary>Previous releases</summary>

**v1.11.0** — A protocol-correctness release. Breaking: `send_peer_review_reminders` is now `send_peer_review_inbox_messages` ([#303](https://github.com/vishalsachdev/canvas-mcp/issues/303)); tool failures set MCP `isError: true` ([#270](https://github.com/vishalsachdev/canvas-mcp/issues/270)); string-returning tools no longer duplicate their payload into `structuredContent.result` ([#271](https://github.com/vishalsachdev/canvas-mcp/issues/271)); FastMCP floor 3.4.7 ([#293](https://github.com/vishalsachdev/canvas-mcp/issues/293)). Thanks [@jonespm](https://github.com/jonespm)

**v1.10.0** — A community bug-fix release driven by live reporter testing — thanks [@khagyard](https://github.com/khagyard), [@zqian](https://github.com/zqian), [@jonespm](https://github.com/jonespm), [@bruchris](https://github.com/bruchris), and [@SHIL0018](https://github.com/SHIL0018) (our second outside code contribution). Included a breaking `search_canvas_tools` response-shape change.

- **Breaking: `search_canvas_tools` response shape v2** ([#281](https://github.com/vishalsachdev/canvas-mcp/issues/281)). The tool now actually searches the ~99 registered MCP tools alongside the TypeScript code-API files (it previously searched only the latter, so "peer review" found nothing despite ~10 peer-review tools existing). Responses carry `schema_version: 2` with labeled `mcp_tools` / `code_execution_api` sections; the old flat `tools` key is gone. Full-detail code-API content is now also capped at 2,000 characters ([#287](https://github.com/vishalsachdev/canvas-mcp/issues/287))
- **Students can find their peer reviews** ([#275](https://github.com/vishalsachdev/canvas-mcp/issues/275)): `get_my_peer_reviews_todo` gained a direct per-assignment lookup and a Planner-feed discovery path — the same data source Canvas's own student UI uses — validated against a real production payload from the reporter
- **`create_announcement` fails safely on student tokens** ([#283](https://github.com/vishalsachdev/canvas-mcp/issues/283)): Canvas silently downgrades the create to a regular discussion topic; the tool now pre-checks course permissions and refuses before creating anything, auto-deletes the unintended topic if a downgrade still slips through, and steers AI clients away from posting the content via discussion tools as a fallback
- **Security:** stricter URL validation (code-scanning fix), Docker base bumped to `python:3.14-slim`, CI actions updated

**v1.9.0** — Prompt-injection hardening ([#239](https://github.com/vishalsachdev/canvas-mcp/issues/239)): Canvas-authored text arrives provenance-fenced as data-not-instructions; multi-recipient sends became two-step preview→confirm (breaking); write tools refuse fence markers; OSSF Scorecard published, CI actions SHA-pinned, `.mcpb` ships SLSA provenance; npm wizard retired ([#249](https://github.com/vishalsachdev/canvas-mcp/issues/249)). Eleven adversarial review rounds pre-merge

**v1.8.0** — Security-scan remediation: 11 of 12 findings fixed, three breaking (HTTPS-only Canvas URLs, stdio-only file transfer tools, no-overwrite downloads), a measured submissions authorization bypass closed centrally, CSV formula-injection protection, code execution fails closed, dependency floors raised (PR #251, #255)

**v1.7.0** — Correctness release from instructor bug reports: writes no longer report success when Canvas quietly did less than asked ([#219](https://github.com/vishalsachdev/canvas-mcp/issues/219)–[#221](https://github.com/vishalsachdev/canvas-mcp/issues/221)), Planner-API upcoming assignments ([#222](https://github.com/vishalsachdev/canvas-mcp/issues/222)), `check_enrollment` AMBIGUOUS answers ([#199](https://github.com/vishalsachdev/canvas-mcp/issues/199)), wire-format fixes for pages/inbox ([#207](https://github.com/vishalsachdev/canvas-mcp/issues/207), [#208](https://github.com/vishalsachdev/canvas-mcp/issues/208)), MCP-spec tool annotations ([#204](https://github.com/vishalsachdev/canvas-mcp/issues/204)), CSV rubric format fix ([#190](https://github.com/vishalsachdev/canvas-mcp/issues/190)), anonymization consolidated to the client layer ([#179](https://github.com/vishalsachdev/canvas-mcp/issues/179)). Thanks [@khagyard](https://github.com/khagyard) and [@zqian](https://github.com/zqian)

**v1.6.0** — Tier 1 student write tools behind an explicit allowlist ([#170](https://github.com/vishalsachdev/canvas-mcp/issues/170)), `get_my_enrollments` / `get_my_profile` ([#171](https://github.com/vishalsachdev/canvas-mcp/issues/171)), three-tier anonymization ([#166](https://github.com/vishalsachdev/canvas-mcp/issues/166), [#179](https://github.com/vishalsachdev/canvas-mcp/issues/179)), rubric association fixes ([#180](https://github.com/vishalsachdev/canvas-mcp/issues/180), [#181](https://github.com/vishalsachdev/canvas-mcp/issues/181)), `execute_typescript` became opt-in ([#178](https://github.com/vishalsachdev/canvas-mcp/issues/178)), ruff gating CI ([@w3lld1](https://github.com/w3lld1), PR #186)

**v1.5.0** — `get_syllabus` ([#134](https://github.com/vishalsachdev/canvas-mcp/issues/134)), `create_rubric_from_csv` ([#119](https://github.com/vishalsachdev/canvas-mcp/issues/119)), `update_discussion_topic` ([#154](https://github.com/vishalsachdev/canvas-mcp/issues/154)), fastmcp 2.x migration ([#145](https://github.com/vishalsachdev/canvas-mcp/issues/145)), dependency advisories cleared 33 → 0 with a gating CI scan (PR #156)

**v1.4.0** — `check_enrollment` (PR #126), Claude Desktop Extension `.mcpb`, Entra ID authenticated institutional hosting ([#115](https://github.com/vishalsachdev/canvas-mcp/issues/115), PR #125), HTTP fails closed without auth gate (PR #123)

**v1.3.0** — `create_rubric` (PR #100), `read_course_file` ([@DomBarker99](https://github.com/DomBarker99), PR #90), event-loop fix for user-scoped tools (PR #99), bulk-delete safety cap (PR #96), dependency pruning (PR #93)

**v1.2.0** — Role-Based Tool Filtering ([@Promithius-DR](https://github.com/Promithius-DR), PR #84), Accessibility Remediation (`fix_accessibility_issues`, scanner expanded 4→20 checks), Security Hardening (path traversal/symlink protections), Windows Support for `execute_typescript` (PR #85), CI consolidation (11→8 checks)

**v1.1.0** — Hosted Server (`mcp.illinihunt.org`), Learning Designer tools + 3 skills, Agent Skills on skills.sh, File Management ([@Metzpapa](https://github.com/Metzpapa), PR #75), Token Optimization, Generic Distribution

**v1.0.8** — Security Hardening (PII sanitization, audit logging, sandbox-by-default), Ruff linting, 235+ tests

**v1.0.7** — Assignment Update Tool (`update_assignment`), complete CRUD, 9 tests

**v1.0.6** — Module Management (7 tools), Page Settings (2 tools), 235+ tests

**v1.0.5** — Claude Code Skills, GitHub Pages site

**v1.0.4** — Code Execution API for token-efficient bulk operations, MCP 2.14 compliance

</details>

### For Students 👨‍🎓
Get AI-powered assistance with:
- Tracking upcoming assignments and deadlines
- Monitoring your grades across all courses
- Managing peer review assignments
- Accessing course content and discussions
- Organizing your TODO list

**[→ Get Started as a Student](https://canvas-mcp.illinihunt.org/student-guide.html)**

### For Educators 👨‍🏫
Enhance your teaching with:
- Assignment and grading management
- Student analytics and performance tracking
- Discussion and peer review facilitation
- Privacy controls designed to support FERPA-conscious workflows
- Bulk messaging and communication tools

**[→ Get Started as an Educator](https://canvas-mcp.illinihunt.org/educator-guide.html)**

### For Learning Designers 🎨
AI-powered course design and quality assurance:
- **Course scaffolding** — Build entire course structures from specs, templates, or by cloning existing courses
- **Quality audits** — Pre-semester QC checks for structure, content, publishing, and completeness
- **Accessibility review** — 20-check WCAG-oriented scanner (headings, tables, scope, contrast, alt text, links, captions, DesignPLUS migration), prioritized reports, guided remediation, and verification
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

### For Educators: FERPA-Conscious Data Handling

Canvas MCP provides optional privacy controls that can support an institution's FERPA obligations. Compliance still depends on your deployment, configuration, institutional policy, and AI provider:

- **Response anonymization** converts supported identity fields to consistent anonymous IDs (Student_xxxxxxxx)
- **Email masking and supported PII-pattern filtering** in discussion posts and submissions
- **Local server deployment** with configurable privacy controls (`ENABLE_DATA_ANONYMIZATION=true`)
- **Privacy-conscious analytics**: Ask "Which students need support?" while reducing the identity data returned to the AI client
- **De-anonymization mapping tool** for faculty to correlate anonymous IDs with real students locally

When `ENABLE_DATA_ANONYMIZATION=true` is enabled, supported identity fields are anonymized before tool results reach the AI client. Review the [Educator Guide](https://canvas-mcp.illinihunt.org/educator-guide.html) and your institution's requirements before using student data.

### For Students: Data Scope & Privacy

- **Canvas-scoped access**: Student-specific tools use Canvas's "self" endpoints; shared course-content tools follow the permissions Canvas grants your account
- **No shared-server credential storage**: Local mode reads your Canvas token from your own `.env`. In authenticated institutional HTTP deployments, each request supplies the user's Canvas token and the server does not store it.
- **No built-in product analytics**: Canvas MCP does not add telemetry; Canvas and your AI client still apply their own logging and data policies
- **Optional anonymization**: Student tools are scoped to your own Canvas data, but your AI client's privacy policy still applies

## Hosted Server (Retired)

The public hosted server (`mcp.illinihunt.org`) has been **retired**. A public MCP endpoint without an access gate isn't safe to operate — it would expose the built-in code-execution tool — so the supported path is **[local installation](#local-installation)** below.

The HTTP/streamable transport itself remains fully supported for **self-hosting behind your own authentication** (`canvas-mcp-server --transport streamable-http`). Running a shared, authenticated instance for your institution? See **[deploy/azure/](deploy/azure/)** for a production-tested deployment specification (Azure App Service + Entra ID platform auth, per-user Canvas tokens) with sample workflow and config templates.

---

## Prerequisites (Local Installation)

- **Python 3.11+** - Required for modern features and type hints
- **Canvas API Access** - API token and institution URL
- **MCP Client** - An MCP-compatible client (Claude Desktop, Cursor, Zed, Windsurf, Continue, etc.); setup and capabilities vary by client

### Supported MCP Clients

Canvas MCP is designed for MCP-compatible clients, including [Claude Desktop](https://claude.ai/download), [Cursor](https://cursor.sh), [Zed](https://zed.dev), [Windsurf](https://codeium.com/windsurf), [Continue](https://continue.dev), [Replit](https://replit.com), and [Copilot Studio](https://www.microsoft.com/microsoft-copilot/microsoft-copilot-studio). Setup details and supported capabilities vary by client.

Canvas MCP uses documented Canvas API patterns such as a User-Agent header and `per_page` pagination. It is intended for Canvas Cloud and compatible self-hosted instances.

## Install as a Claude Desktop Extension (easiest)

If you use **Claude Desktop**, you can install Canvas MCP with one click — no terminal, no config-file editing:

1. Download `canvas-mcp.mcpb` from the [latest release](https://github.com/vishalsachdev/canvas-mcp/releases/latest).
2. Double-click the file (or drag it into Claude Desktop → Settings → Extensions).
3. When prompted, enter your **Canvas API URL** — this must include the `/api/v1` path (e.g. `https://canvas.youruniversity.edu/api/v1`) — and your **Canvas API token** (Canvas → Account → Settings → New Access Token — some institutions issue these by request form instead, see [below](#2-configure-environment)). The token is stored in your OS keychain.

The extension runs the server locally and calls Canvas with **your own** token, so requests use that token's Canvas permissions. Canvas and your AI client may retain their own activity records. Requires Python 3.11+ (the bundled runtime manages dependencies automatically). For other clients, or to run from source, use the manual setup below.

## Local Installation

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

> **Some institutions gate token creation.** Where self-service is disabled, the
> "New Access Token" button is missing or errors out, and tokens are issued through an
> IT request form instead. Check your institution's IT knowledge base before concluding
> that API access is unavailable to you.
>
> **University of Illinois Urbana-Champaign** works this way for *everyone* — students
> and instructors alike. Request a token with the
> [Canvas API Token Request form](https://help.uillinois.edu/TDClient/42/UIUC/Requests/TicketRequests/NewForm?ID=4AZBjiZfXWs_&RequestorType=Service)
> (NetID login required). Once it is approved:
>
> 1. Go to **Canvas → Account → Settings → Approved Integrations**, find the new token,
>    click **Activate**, and refresh the page.
> 2. Retrieve the token value from the U of I Box link Technology Services sends you.
>
> As of August 2026, all new Illinois tokens carry a **30-day expiration** (an upstream
> Instructure requirement). Expiry is not monitored or announced, and expired tokens are
> removed without notice — request the replacement before the current one lapses.
> Full details: [Answers KB 150325](https://answers.uillinois.edu/illinois/internal/150325).
>
> **Students elsewhere**: if you see "There is a limit to the number of access tokens you
> can create" or cannot find the token creation option, contact your institution's Canvas
> administrator or IT support department to request API access.

### 3. MCP Client Configuration

Canvas MCP is designed for MCP-compatible clients. Below are configuration examples for popular clients; exact setup and capabilities vary by client:

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

The Canvas MCP Server provides a set of tools for interacting with the Canvas LMS API. These tools are organized into logical categories for better discoverability and maintainability.

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
9. **Discovery Tools** - Search registered MCP tools and code execution API operations with `search_canvas_tools`; list code execution modules with `list_code_api_modules`
10. **Code Execution Tools** - Execute TypeScript code with `execute_typescript` so bulk item processing can stay out of the model's context

📖 [View Full Tool Documentation](tools/README.md) for detailed information about the available tools.

## Code Execution API

For bulk operations (30+ items), Canvas MCP supports **TypeScript code execution**. Process bulk operations locally without loading every item into the model’s context.

| Approach | Best For | Context Behavior |
|----------|----------|------------------|
| MCP tools | Simple queries, small datasets | Returns tool results to the model |
| `bulk_grade_submissions` | Batch grading 10-29 items | Handles a defined batch in one tool call |
| `execute_typescript` | 30+ items, custom logic | Processes items locally and returns selected output |

Use `search_canvas_tools` to discover available operations, then `execute_typescript` to run them locally. The default sandbox applies time, memory, environment, and best-effort network controls, but it is not a complete security boundary; use stronger external isolation when untrusted code or strict egress control is required (see [issue #157](https://github.com/vishalsachdev/canvas-mcp/issues/157)). Works on macOS, Linux, and Windows.

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
| Local sandbox (default) | None needed | Timeout 120s, memory 512MB, filtered environment, best-effort network controls |
| Container sandbox | `TS_SANDBOX_MODE=container` | Container filesystem isolation via Docker/Podman; egress guarantees depend on deployment configuration |
| No sandbox | `ENABLE_TS_SANDBOX=false` | Full local access (not recommended) |

See [Bulk Grading Example](examples/bulk_grading_example.md) for a detailed walkthrough.

</details>

## Usage

MCP clients start the server automatically. Just ask naturally:

- *"What's due this week?"* / *"Show my grades"* / *"What peer reviews do I need?"*
- *"Who hasn't submitted Assignment 3?"* / *"Send reminders to missing students"*

Quick start guides: [Student](examples/student_quickstart.md) | [Educator](examples/educator_quickstart.md) | [Real-World Workflows](examples/real_world_workflows.md) | [Troubleshooting](examples/common_issues.md)

## Documentation

- **[Tool Documentation](tools/README.md)** — Reference for the available tools, including optional feature-gated tools
- **[Student Guide](https://canvas-mcp.illinihunt.org/student-guide.html)** — Getting started as a student
- **[Educator Guide](https://canvas-mcp.illinihunt.org/educator-guide.html)** — FERPA considerations and educator workflows
- **[Bulk Grading Example](examples/bulk_grading_example.md)** — Batch grading walkthrough
- **[Development Guide](CLAUDE.md)** — Architecture and contributing

<details>
<summary>Technical details</summary>

Built on **FastMCP** with async `httpx`, `pydantic` validation, and `python-dotenv` configuration. Modern `src/` layout with `pyproject.toml`, type hints across core paths, connection pooling, pagination, and rate limiting. An automated test suite and `ruff` + `black` support code quality.

</details>

## Troubleshooting

If you encounter issues:

1. **Server Won't Start** - Verify your [Local Installation](#local-installation) setup: `.env` file, virtual environment path, and dependencies
2. **Authentication Errors** - Check your Canvas API token validity and permissions
3. **Connection Issues** - Verify Canvas API URL correctness and network access
4. **Debugging** - Check your MCP client's console logs (e.g., Claude Desktop's developer console) or run server manually for error output

## Security

Runtime security and privacy controls:

| Layer | Default |
|-------|---------|
| PII sanitization in logs | `LOG_REDACT_PII=true` |
| Token validation on startup | Always on |
| Structured audit logging | Opt-in: `LOG_ACCESS_EVENTS=true` |
| Code execution guardrails | `ENABLE_TS_SANDBOX=true` (best-effort in local mode) |

Optional anonymization for FERPA-conscious educator workflows: `ENABLE_DATA_ANONYMIZATION=true`. See [Educator Guide](https://canvas-mcp.illinihunt.org/educator-guide.html) for scope and configuration details.

## Publishing

Published to [PyPI](https://pypi.org/project/canvas-mcp/), [MCP Registry](https://registry.modelcontextprotocol.io/), and [skills.sh](https://skills.sh) (agent skills). Releases are automated via GitHub Actions — tag a version (`git tag vX.Y.Z && git push origin vX.Y.Z`) and CI handles the rest.

## Contributing

Contributions are welcome! Feel free to:
- Submit issues for bugs or feature requests
- Create pull requests with improvements
- Share your use cases and feedback

## Contributors

Thanks to everyone who has contributed to Canvas MCP:

- **[@DomBarker99](https://github.com/DomBarker99)** — `read_course_file` tool for remote MCP deployments (#90)
- **[@Promithius-DR](https://github.com/Promithius-DR)** — Role-based tool filtering and tool annotations (#84)
- **[@Metzpapa](https://github.com/Metzpapa)** — File download and listing tools (#75)
- **[@JCSnap](https://github.com/JCSnap)** — Student tool bug fixes (#72, #73)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Created by [Vishal Sachdev](https://github.com/vishalsachdev)

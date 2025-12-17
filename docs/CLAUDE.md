# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Note**: This guide is for developers working ON the Canvas MCP codebase. If you're an AI agent USING the MCP server, see [AGENTS.md](../AGENTS.md) instead.

# Canvas MCP Development Guide

## Environment Setup
- Install uv package manager: `pip install uv`
- Install dependencies: `uv pip install -e .`
- Create `.env` file with `CANVAS_API_TOKEN` and `CANVAS_API_URL`
- Server installed as CLI command: `canvas-mcp-server`

## Commands
- **Start server**: `canvas-mcp-server` (or `./start_canvas_server.sh` for legacy setup)
- **Test server**: `canvas-mcp-server --test`
- **View config**: `canvas-mcp-server --config`
- **Claude Desktop config**: Update `~/Library/Application Support/Claude/claude_desktop_config.json`

## Repository Structure
```
canvas-mcp/
├── src/canvas_mcp/        # Main application code
│   ├── core/             # Core utilities (client, config, validation)
│   ├── tools/            # MCP tool implementations
│   ├── resources/        # MCP resources and prompts
│   └── server.py         # FastMCP server entry point
├── docs/                 # Essential documentation
├── archive/              # Legacy code and development specs (git-ignored)
├── .env                  # Configuration
└── start_canvas_server.sh # Server startup script
```

## Architecture Overview

### Core Design Patterns
- **FastMCP framework**: Built on FastMCP for robust MCP server implementation with proper tool registration
- **Type-driven validation**: All MCP tools use `@validate_params` decorator with sophisticated Union/Optional type handling
- **Dual-layer caching**: Bidirectional course code ↔ ID mapping via `course_code_to_id_cache` and `id_to_course_code_cache`
- **Flexible identifiers**: Support for Canvas IDs, course codes, and SIS IDs through `get_course_id()` abstraction
- **ISO 8601 standardization**: All dates converted via `format_date()` and `parse_date()` functions

### MCP Tool Organization
- **Progressive disclosure**: List → Details → Content → Analytics pattern
- **Functional grouping**: Tools organized by Canvas entity (courses, assignments, discussions, messaging, etc.)
- **Consistent naming**: `{action}_{entity}[_{specifier}]` pattern
- **Educational analytics focus**: Student performance, completion rates, missing work identification
- **Discussion workflow**: Browse → View → Read → Reply pattern for student interaction
- **Messaging workflow**: Analytics → Target → Template → Send pattern for automated communications

### API Layer Architecture
- **Centralized requests**: All Canvas API calls go through `make_canvas_request()`
- **Form data support**: Messaging endpoints use `use_form_data=True` for Canvas compatibility
- **Automatic pagination**: `fetch_all_paginated_results()` handles Canvas pagination transparently
- **Async throughout**: All I/O operations use async/await
- **Graceful error handling**: Returns JSON error responses rather than raising exceptions
- **Privacy protection**: Student data anonymization via configurable `anonymize_response_data()`

## Key Components

### Parameter Validation System
- `validate_parameter()`: Runtime type coercion supporting complex types
- `@validate_params`: Automatic validation decorator for all MCP tools
- Handles Union types, Optional types, string→JSON conversion, comma-separated lists

### Course Identifier Handling
- `get_course_id()`: Converts any identifier type to Canvas ID
- `get_course_code()`: Reverse lookup from ID to human-readable code
- `refresh_course_cache()`: Rebuilds identifier mapping from Canvas API

### Analytics Engine
- `get_student_analytics()`: Multi-dimensional educational data analysis
- `get_assignment_analytics()`: Statistical performance analysis with grade distribution
- `get_peer_review_completion_analytics()`: Peer review tracking and completion analysis
- `get_peer_review_comments()`: Extract actual peer review comment text and analysis
- `analyze_peer_review_quality()`: Comprehensive comment quality analysis with metrics
- `identify_problematic_peer_reviews()`: Automated flagging of low-quality reviews
- Temporal filtering (current vs. all assignments)
- Risk identification and performance categorization

### Messaging System
- `send_conversation()`: Core Canvas messaging with form data support
- `send_peer_review_reminders()`: Automated peer review reminder workflow
- `send_peer_review_followup_campaign()`: Complete analytics → messaging pipeline
- `MessageTemplates`: Flexible template system for various communication types
- Privacy-aware: Works with anonymization while preserving functional user IDs

## Coding Standards
- **Type hints**: Mandatory for all functions, use Union/Optional appropriately
- **MCP tools**: Use `@mcp.tool()` decorator with `@validate_params`
- **Async functions**: All API interactions must be async
- **Course identifiers**: Use `Union[str, int]` and `get_course_id()` for flexibility
- **Date handling**: Use `format_date()` for all date outputs
- **Error responses**: Return JSON strings with "error" key for failures
- **Form data**: Use `use_form_data=True` for Canvas messaging endpoints
- **Privacy**: Student IDs preserved, names anonymized in `_should_anonymize_endpoint()`

## Discussion Forum Interaction Workflow
- **Browse discussions**: `list_discussion_topics(course_id)` - Find available discussion forums
- **View student posts**: `list_discussion_entries(course_id, topic_id)` - See all posts in a discussion
- **Read full content**: `get_discussion_entry_details(course_id, topic_id, entry_id)` - Get complete student comment
- **Reply to students**: `reply_to_discussion_entry(course_id, topic_id, entry_id, "Your response")` - Respond to student comments
- **Create discussions**: `create_discussion_topic(course_id, title, message)` - Start new discussion forums
- **Post new entries**: `post_discussion_entry(course_id, topic_id, message)` - Add top-level posts

## Canvas Messaging Workflow
- **Analyze completion**: `get_peer_review_completion_analytics(course_id, assignment_id)` - Get students needing reminders
- **Target recipients**: Extract user IDs from analytics results for messaging
- **Choose template**: Use `MessageTemplates.get_template()` or custom message content
- **Send reminders**: `send_peer_review_reminders()` for targeted messaging
- **Bulk campaigns**: `send_peer_review_followup_campaign()` for complete automated workflow
- **Monitor delivery**: Check Canvas inbox for message delivery confirmation

## Peer Review Comment Analysis Workflow
- **Extract comments**: `get_peer_review_comments(course_id, assignment_id)` - Get all review text and metadata
- **Analyze quality**: `analyze_peer_review_quality(course_id, assignment_id)` - Generate comprehensive quality metrics
- **Flag problems**: `identify_problematic_peer_reviews(course_id, assignment_id)` - Find reviews needing attention
- **Export data**: `extract_peer_review_dataset(course_id, assignment_id, format="csv")` - Export for further analysis
- **Generate reports**: `generate_peer_review_feedback_report(course_id, assignment_id)` - Create instructor-ready reports
- **Take action**: Use problematic review lists to provide targeted feedback or follow-up

## Canvas API Specifics
- Base URL from `CANVAS_API_URL` environment variable
- Authentication via Bearer token in `CANVAS_API_TOKEN`
- Always use pagination for list endpoints
- Course codes preferred over IDs in user-facing output
- Handle both published and unpublished content states
- **Messaging requires form data**: Use `use_form_data=True` for `/conversations` endpoints
- **Privacy protection**: Real user IDs preserved for functionality, names anonymized for privacy

## Documentation Maintenance

### Source of Truth Hierarchy

This repository has multiple documentation files for different audiences. To prevent redundancy:

| File | Audience | Contains | Updates When |
|------|----------|----------|--------------|
| `AGENTS.md` | AI agents/MCP clients | Tool tables, workflows, constraints, examples | Tools added/changed |
| `tools/README.md` | Human users | Comprehensive tool docs with all parameters | Tools added/changed |
| `tools/TOOL_MANIFEST.json` | Programmatic access | Machine-readable tool catalog | Tools added/changed |
| `README.md` | Everyone (entry point) | Installation, overview, links to other docs | Major releases only |
| `examples/*.md` | Human users | Workflow tutorials, not tool reference | New workflows added |
| `docs/CLAUDE.md` | Developers | Codebase architecture, NOT tool usage | Architecture changes |

### Rules to Prevent Redundancy

1. **Tool documentation**:
   - Source of truth: `tools/README.md` (humans) and `AGENTS.md` (agents)
   - `README.md` inline section exists ONLY for fetch-constrained agents
   - Do NOT add tool details to examples/*.md - link to tools/README.md instead

2. **Example prompts**:
   - Source of truth: `AGENTS.md` (has example prompts per tool)
   - `tools/TOOL_MANIFEST.json` mirrors these for machine access
   - Quickstart guides use DIFFERENT examples (workflow-focused, not tool-focused)

3. **Rate limits/constraints**:
   - Source of truth: `AGENTS.md` (agent-facing constraints)
   - Do NOT duplicate in README.md or tools/README.md

4. **Workflows**:
   - Source of truth: `AGENTS.md` (common workflows) + `examples/*.md` (detailed tutorials)
   - `TOOL_MANIFEST.json` has simplified workflow references

5. **When adding a new tool**:
   - Update `tools/README.md` with full documentation
   - Update `AGENTS.md` tool table (keep it concise)
   - Update `tools/TOOL_MANIFEST.json` with parameters and examples
   - Do NOT update README.md unless it's a major feature

6. **When updating tool behavior**:
   - Update the source of truth files above
   - Check for stale references in examples/*.md

### What NOT to Do

- Do NOT copy tool tables between files (they drift)
- Do NOT add installation instructions outside README.md
- Do NOT add architecture details to AGENTS.md (that's for CLAUDE.md)
- Do NOT add example prompts to tools/README.md (that's for AGENTS.md)

## Psychology

Do not be afraid to question what I say. Do not always respond with "You're right!" Question the assertions I make and decide whether they are true. If they are probably true, don't question them. If they are probably false, question them. If you are unsure, question them. Always think critically about what I say and decide for yourself whether it is true or false

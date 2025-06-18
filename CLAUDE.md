# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Canvas MCP Development Guide

## Environment Setup
- Create virtual env: `python -m venv canvas-mcp`
- Activate: `source canvas-mcp/bin/activate`
- Install dependencies: `pip install -r requirements.txt`
- Create `.env` file with `CANVAS_API_TOKEN` and `CANVAS_API_URL`

## Commands
- **Start server**: `./start_canvas_server.sh`
- **Test MCP server**: Start server manually and check stderr output for debugging
- **Extract API docs**: `python extract_canvas_api_docs.py` (creates canvas_api_docs/ directory)
- **Get course grades**: `python get_course_grades.py <course_id>` (outputs gradebook.json)
- **Claude Desktop config**: Update `~/Library/Application Support/Claude/claude_desktop_config.json`

## Architecture Overview

### Core Design Patterns
- **Type-driven validation**: All MCP tools use `@validate_params` decorator with sophisticated Union/Optional type handling
- **Dual-layer caching**: Bidirectional course code ↔ ID mapping via `course_code_to_id_cache` and `id_to_course_code_cache`
- **Flexible identifiers**: Support for Canvas IDs, course codes, and SIS IDs through `get_course_id()` abstraction
- **ISO 8601 standardization**: All dates converted via `format_date()` and `parse_date()` functions

### MCP Tool Organization
- **Progressive disclosure**: List → Details → Content → Analytics pattern
- **Functional grouping**: Tools organized by Canvas entity (courses, assignments, pages, etc.)
- **Consistent naming**: `{action}_{entity}[_{specifier}]` pattern
- **Educational analytics focus**: Student performance, completion rates, missing work identification

### API Layer Architecture
- **Centralized requests**: All Canvas API calls go through `make_canvas_request()`
- **Automatic pagination**: `fetch_all_paginated_results()` handles Canvas pagination transparently  
- **Async throughout**: All I/O operations use async/await
- **Graceful error handling**: Returns JSON error responses rather than raising exceptions

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
- Temporal filtering (current vs. all assignments)
- Risk identification and performance categorization

## Coding Standards
- **Type hints**: Mandatory for all functions, use Union/Optional appropriately
- **MCP tools**: Use `@mcp.tool()` decorator with `@validate_params`
- **Async functions**: All API interactions must be async
- **Course identifiers**: Use `Union[str, int]` and `get_course_id()` for flexibility
- **Date handling**: Use `format_date()` for all date outputs
- **Error responses**: Return JSON strings with "error" key for failures

## Canvas API Specifics
- Base URL from `CANVAS_API_URL` environment variable
- Authentication via Bearer token in `CANVAS_API_TOKEN`
- Always use pagination for list endpoints
- Course codes preferred over IDs in user-facing output
- Handle both published and unpublished content states
# Architecture & Key Components

> Design reference extracted from CLAUDE.md.

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

# Global Architecture Map

## Dependency Graph

```
server.py (entry point)
├── core/config.py          → env vars, CanvasConfig
├── core/cache.py           → refresh_course_cache()
├── core/client.py          → make_canvas_request(), fetch_all_paginated_results()
├── core/validation.py      → @validate_params, validate_parameter()
├── core/audit.py           → log_access(), log_execution()
├── core/logging.py         → get_logger(), sanitize_for_log()
├── tools/*.py              → register_*_tools(mcp) pattern
│   └── Every tool imports: make_canvas_request, get_course_id, validate_params, format_date
└── resources/resources.py  → register_resources_and_prompts(mcp)
```

## Shared Types & Abstractions

### Current (core/types.py)
- Currently minimal/empty — types are scattered across files

### Cross-Cutting Functions (used by 10+ tool files)
| Function | Module | Consumers |
|----------|--------|-----------|
| `make_canvas_request()` | core/client.py | All tools/*.py |
| `fetch_all_paginated_results()` | core/client.py | 8+ tool files |
| `get_course_id()` | core/cache.py | All tools/*.py |
| `get_course_code()` | core/cache.py | 6+ tool files |
| `format_date()` | core/dates.py | All tools/*.py |
| `parse_date()` | core/dates.py | 4 tool files |
| `validate_params` | core/validation.py | All tools/*.py |
| `get_logger()` | core/logging.py | core/*.py |
| `sanitize_for_log()` | core/logging.py | core/audit.py |

## Registration Pattern

All tool modules follow the same pattern:
```python
def register_*_tools(mcp):
    @mcp.tool()
    @validate_params
    async def tool_name(...) -> str:
        ...
```

This creates **nested function definitions** which inflate cyclomatic complexity of the outer `register_*_tools` function. The CC numbers for these functions reflect the **sum of all inner tool functions**, not a single monolithic function.

## Key Architectural Issues

### 1. Monolithic Registration Functions
- `register_discussion_tools` (CC=194): 12+ tools defined as nested functions
- `register_assignment_tools` (CC=139): 8+ tools as nested functions
- `register_rubric_tools` (CC=106): 10+ tools as nested functions
- **Root cause**: FastMCP `@mcp.tool()` requires access to the `mcp` instance, forcing nested definitions

### 2. validate_parameter() God Function (CC=47)
- Handles Union types, Optional, str→int coercion, JSON parsing, list splitting, bool conversion
- Deep nesting (depth=10) from type-dispatch logic

### 3. Print-Based Logging
- 28 `print(..., file=sys.stderr)` calls in core/ and server.py
- Structured logging module exists (`core/logging.py`) but is underused

### 4. Silent Failures (5 locations)
- `except: pass` blocks that swallow errors without logging

### 5. Response Formatting Duplication
- Each tool builds JSON response strings independently
- No shared response builder/formatter

## Naming Conventions (Current)

| Pattern | Examples | Consistency |
|---------|----------|-------------|
| Tools: `verb_noun` | `list_courses`, `get_page_details` | Good |
| Core: `verb_noun` | `make_canvas_request`, `get_course_id` | Good |
| Registration: `register_*_tools` | All tool modules | Consistent |
| Tests: `test_verb_noun` | `test_list_modules_basic` | Good |
| Fetch vs Get | Mixed: `fetch_all_paginated_results` vs `get_course_id` | Needs alignment |

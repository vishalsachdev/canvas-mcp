***

title: Enable AI-Assisted Rubric Creation and Posting to Canvas
type: feat
date: 2026-02-05
----------------

# Enable AI-Assisted Rubric Creation and Posting to Canvas

## Overview

Add the ability to create rubrics programmatically and post them to Canvas LMS. This feature enables AI agents to brainstorm rubrics with educators, generate structured rubric definitions, and post them directly to Canvas for use in grading assignments.

## Problem Statement

The Canvas MCP currently has **12 rubric tools** but the core `create_rubric` tool is **disabled** due to Canvas API 500 errors. Educators cannot:

* Create rubrics via AI conversation

* Post AI-generated rubrics to Canvas

* Import rubrics from files

The root cause appears to be **incorrect data format** - the current implementation uses JSON body instead of form-data with bracket notation (which works for `grade_with_rubric`).

## Proposed Solution

Implement a dual-approach solution:

1. **Fix the API-based creation** - Change `create_rubric` to use form-data with bracket notation
2. **Add CSV import** - Implement the `/rubrics/upload` endpoint as a reliable alternative
3. **Support multiple workflows** - Interactive chat, template-based, and file import

## Technical Approach

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     User Workflows                               │
├──────────────────┬──────────────────┬───────────────────────────┤
│  Interactive     │  Template-Based  │  File Import              │
│  Chat            │  Generation      │  (JSON/CSV)               │
│                  │                  │                           │
│  User ←→ AI      │  Assignment →    │  File → Validate →        │
│  brainstorm      │  AI generates    │  Preview → Upload         │
└────────┬─────────┴────────┬─────────┴─────────────┬─────────────┘
         │                  │                       │
         └──────────────────┴───────────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────────┐
         │        Rubric Data (Internal JSON)       │
         │  {                                       │
         │    "title": "...",                       │
         │    "criteria": {                         │
         │      "1": { "description": "...",        │
         │             "points": 10,                │
         │             "ratings": {...} }           │
         │    }                                     │
         │  }                                       │
         └────────────────────┬─────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │  Direct API     │             │  CSV Upload     │
    │  (form-data)    │             │  (file upload)  │
    │                 │             │                 │
    │  POST /rubrics  │             │  POST /rubrics/ │
    │  + form params  │             │  upload         │
    └────────┬────────┘             └────────┬────────┘
             │                               │
             └───────────────┬───────────────┘
                             │
                             ▼
                   ┌─────────────────┐
                   │  Canvas LMS     │
                   │  Rubric Created │
                   └────────┬────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │  associate_rubric_with_     │
              │  assignment (optional)      │
              └─────────────────────────────┘
```

### Implementation Phases

#### Phase 1: Fix Direct API Creation

**Goal**: Re-enable `create_rubric` with correct form-data format

**Tasks**:

1. Create test script to verify Canvas API format requirements
2. Update `create_rubric` to use form-data with bracket notation
3. Add `build_rubric_form_data()` helper function (similar to `build_rubric_assessment_form_data`)
4. Re-enable the tool and update docstrings
5. Add comprehensive tests

**Files to modify**:

* `src/canvas_mcp/tools/rubrics.py` - Main implementation

* `tests/tools/test_rubrics.py` - Add creation tests

**Key code change** - Transform from:

```python
# Current (broken)
request_data = {
    "rubric": rubric_data,
    "rubric_association": {...}
}
response = await make_canvas_request("post", endpoint, data=request_data)
```

To:

```python
# Fixed (form-data with bracket notation)
form_data = build_rubric_form_data(title, criteria, association)
# Results in: rubric[title]=..., rubric[criteria][1][description]=..., etc.
response = await make_canvas_request("post", endpoint, data=form_data, use_form_data=True)
```

#### Phase 2: Add CSV Import

**Goal**: Provide reliable alternative via Canvas's CSV upload endpoint

**Tasks**:

1. Implement `get_rubric_template()` tool to download Canvas CSV template
2. Implement `import_rubric_csv()` tool for file upload
3. Add `export_rubric_to_csv()` tool for exporting existing rubrics
4. Handle async upload status polling
5. Add tests

**New tools**:

```python
@mcp.tool()
async def get_rubric_template(course_identifier: str | int) -> str:
    """Download the Canvas rubric CSV template.

    Returns the CSV template format that can be filled in and uploaded.
    """

@mcp.tool()
async def import_rubric_csv(
    course_identifier: str | int,
    csv_content: str,
    association_id: str | int | None = None,
    association_type: str = "Course"
) -> str:
    """Import a rubric from CSV content.

    Uses Canvas's /rubrics/upload endpoint for reliable creation.
    """

@mcp.tool()
async def export_rubric_to_csv(
    course_identifier: str | int,
    rubric_id: str | int
) -> str:
    """Export an existing rubric to CSV format.

    Useful for backing up rubrics or editing externally.
    """
```

**Files to create/modify**:

* `src/canvas_mcp/tools/rubrics.py` - Add new tools

* `tests/tools/test_rubrics.py` - Add import/export tests

#### Phase 3: JSON Import/Export

**Goal**: Enable file-based workflow with JSON format

**Tasks**:

1. Define canonical JSON schema for rubrics
2. Implement `import_rubric_json()` tool
3. Implement `export_rubric_to_json()` tool
4. Add validation helpers
5. Add tests

**New tools**:

```python
@mcp.tool()
async def import_rubric_json(
    course_identifier: str | int,
    rubric_json: str | dict,
    association_id: str | int | None = None,
    use_for_grading: bool = False
) -> str:
    """Create a rubric from JSON definition.

    JSON Schema:
    {
      "title": "Rubric Title",
      "free_form_criterion_comments": true,
      "criteria": {
        "1": {
          "description": "Criterion Name",
          "long_description": "Optional extended description",
          "points": 10,
          "ratings": {
            "1": {"description": "Excellent", "points": 10},
            "2": {"description": "Good", "points": 7},
            "3": {"description": "Needs Work", "points": 0}
          }
        }
      }
    }
    """

@mcp.tool()
async def export_rubric_to_json(
    course_identifier: str | int,
    rubric_id: str | int
) -> str:
    """Export a rubric to JSON format for backup or external editing."""
```

**Files to create/modify**:

* `src/canvas_mcp/tools/rubrics.py` - Add new tools

* `src/canvas_mcp/core/rubric_schema.py` - JSON schema and validation (new file)

* `tests/tools/test_rubrics.py` - Add JSON import/export tests

#### Phase 4: Validation and UX Improvements

**Goal**: Robust validation and helpful error messages

**Tasks**:

1. Add client-side validation before API calls
2. Implement `validate_rubric()` tool for dry-run checks
3. Add `preview_rubric()` tool for formatted display
4. Improve error messages with actionable guidance

**Validation rules**:

* Title: required, non-empty, < 255 characters

* Criteria: at least 1 required

* Each criterion: description required, points >= 0

* Each rating: description required, points >= 0

* Ratings should be ordered by points (highest to lowest)

**New tools**:

```python
@mcp.tool()
async def validate_rubric(rubric_json: str | dict) -> str:
    """Validate a rubric definition without creating it.

    Checks:
    - Required fields present
    - Point values valid
    - Rating ordering correct
    - Character limits respected

    Returns validation result with any issues found.
    """

@mcp.tool()
async def preview_rubric(rubric_json: str | dict) -> str:
    """Format a rubric definition for human review.

    Returns a nicely formatted text representation of the rubric
    showing all criteria and ratings in an easy-to-read format.
    """
```

## Acceptance Criteria

### Functional Requirements

* [x] `create_rubric` tool successfully creates rubrics via Canvas API (Phase 1 complete)

* [ ] `import_rubric_csv` tool uploads CSV rubrics to Canvas (Phase 2 - future)

* [ ] `import_rubric_json` tool creates rubrics from JSON definitions (Phase 3 - future)

* [ ] `export_rubric_to_csv` exports rubrics in Canvas CSV format (Phase 2 - future)

* [ ] `export_rubric_to_json` exports rubrics in JSON format (Phase 3 - future)

* [ ] `validate_rubric` validates rubric definitions without API calls (Phase 4 - future)

* [ ] `preview_rubric` formats rubrics for human review (Phase 4 - future)

* [x] All tools handle errors gracefully with actionable messages

### Non-Functional Requirements

* [x] Tests cover success paths, error handling, and edge cases (21 tests)

* [ ] Documentation updated (AGENTS.md, tools/README.md, TOOL\_MANIFEST.json) (Phase 1 PR)

* [x] Follows existing code patterns (validation decorator, error handling, caching)

### Quality Gates

* [x] All tests pass: `pytest tests/tools/test_rubrics.py` (21 passed)

* [ ] Type checking passes: `mypy src/canvas_mcp/tools/rubrics.py`

* [x] Linting passes: `ruff check src/canvas_mcp/tools/rubrics.py` (no new issues)

* [ ] Code reviewed

## Success Metrics

1. **API success rate**: `create_rubric` succeeds > 95% of valid requests
2. **Coverage**: > 80% test coverage for new code
3. **User adoption**: Rubric creation tools used in real courses

## Dependencies & Prerequisites

* Canvas API access with `manage_rubrics` permission

* Understanding of exact form-data format Canvas expects (requires testing)

* CSV upload endpoint availability (may vary by Canvas instance)

## Risk Analysis & Mitigation

| Risk                                 | Likelihood | Impact | Mitigation                                         |
| ------------------------------------ | ---------- | ------ | -------------------------------------------------- |
| Form-data format still doesn't work  | Medium     | High   | CSV import as fallback; test extensively first     |
| CSV upload endpoint not available    | Low        | Medium | Direct API as primary, document limitation         |
| Canvas API rate limits               | Low        | Medium | Add delays between calls, batch operations         |
| Destructive update behavior persists | Known      | Medium | Keep `update_rubric` disabled, document workaround |

## Testing Strategy

### Unit Tests

```python
# tests/tools/test_rubrics.py

# Phase 1: Create Rubric
async def test_create_rubric_success()
async def test_create_rubric_with_association()
async def test_create_rubric_validation_error()
async def test_create_rubric_api_error()
async def test_create_rubric_permission_denied()

# Phase 2: CSV Import/Export
async def test_get_rubric_template()
async def test_import_rubric_csv_success()
async def test_import_rubric_csv_invalid_format()
async def test_export_rubric_to_csv()

# Phase 3: JSON Import/Export
async def test_import_rubric_json_success()
async def test_import_rubric_json_invalid_schema()
async def test_export_rubric_to_json()

# Phase 4: Validation
async def test_validate_rubric_valid()
async def test_validate_rubric_missing_title()
async def test_validate_rubric_invalid_points()
async def test_preview_rubric_formatting()
```

### Integration Tests

```python
# Manual testing checklist
# [ ] Create rubric via API in test course
# [ ] Verify rubric appears in Canvas UI
# [ ] Associate rubric with assignment
# [ ] Grade submission using created rubric
# [ ] Export rubric, modify, reimport
```

## Documentation Plan

Update these files after implementation:

1. **AGENTS.md** - Add new tools to rubric section
2. **tools/README.md** - Full documentation for new tools
3. **tools/TOOL\_MANIFEST.json** - Add tool definitions
4. **CLAUDE.md** - Update roadmap/backlog

## Future Considerations

1. **Copy rubric between courses** - Common workflow, could add `copy_rubric()` tool
2. **Rubric templates** - Pre-built rubric structures for common assignment types
3. **Bulk rubric creation** - Create multiple rubrics from a single JSON/CSV file
4. **Fix** **`update_rubric`** - If Canvas fixes their API, re-enable with careful testing

## References & Research

### Internal References

* Existing rubric tools: `src/canvas_mcp/tools/rubrics.py`

* Form-data pattern: `src/canvas_mcp/tools/modules.py:146` (create\_module)

* Form-data for grading: `src/canvas_mcp/tools/rubrics.py:738` (grade\_with\_rubric)

### External References

* Canvas Rubrics API: <https://canvas.instructure.com/doc/api/rubrics.html>

* Developer Portal: <https://developerdocs.instructure.com/services/canvas/resources/rubrics>

* Community discussion: <https://community.canvaslms.com/t5/Canvas-Question-Forum/Uploading-rubric-from-CSV-sheet/m-p/602222>

### Key Technical Insight

The working `grade_with_rubric` uses this form-data pattern:

```python
form_data = {
    "rubric_assessment[_8027][points]": "100",
    "rubric_assessment[_8027][comments]": "Great work!"
}
response = await make_canvas_request("put", endpoint, data=form_data, use_form_data=True)
```

The same pattern should work for rubric creation:

```python
form_data = {
    "rubric[title]": "My Rubric",
    "rubric[criteria][1][description]": "Content Quality",
    "rubric[criteria][1][points]": "10",
    "rubric[criteria][1][ratings][1][description]": "Excellent",
    "rubric[criteria][1][ratings][1][points]": "10",
    # ... more criteria and ratings
    "rubric_association[association_type]": "Course",
    "rubric_association[association_id]": "12345"
}
```

## Appendix: JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Canvas Rubric",
  "type": "object",
  "required": ["title", "criteria"],
  "properties": {
    "title": {
      "type": "string",
      "minLength": 1,
      "maxLength": 255
    },
    "free_form_criterion_comments": {
      "type": "boolean",
      "default": true
    },
    "criteria": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "required": ["description", "points"],
        "properties": {
          "description": {"type": "string", "minLength": 1},
          "long_description": {"type": "string"},
          "points": {"type": "number", "minimum": 0},
          "ratings": {
            "type": "object",
            "additionalProperties": {
              "type": "object",
              "required": ["description", "points"],
              "properties": {
                "description": {"type": "string"},
                "long_description": {"type": "string"},
                "points": {"type": "number", "minimum": 0}
              }
            }
          }
        }
      }
    }
  }
}
```
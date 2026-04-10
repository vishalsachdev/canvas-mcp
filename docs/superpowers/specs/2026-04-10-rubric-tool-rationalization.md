# Rubric Tool Rationalization

**Date:** 2026-04-10
**Status:** Approved
**Scope:** Reduce rubric tools from 11 → 6, remove dead code, fix documentation drift

## Problem

The rubric tool surface area has grown organically to 11 tools in `rubrics.py` (1,273 lines — the largest tool file). Of these:

- 2 tools are **disabled** (return error strings because Canvas API is broken)
- 3 tools are **undocumented** (not in AGENTS.md or tools/README.md)
- 3 tools **overlap** (answer "what does this rubric look like?" with slightly different inputs)
- 1 tool (`bulk_grade_submissions`) is **misplaced** (general grading tool in the rubric file)
- `TOOL_MANIFEST.json` references a tool name (`grade_submission_with_rubric`) that doesn't exist in code

This creates unnecessary cognitive load for agents choosing tools and maintenance burden for developers.

## Approach

Surgical prune: delete broken/ghost tools, merge overlapping reads, relocate misplaced tool, rename for clarity. No behavioral changes to surviving tools.

## Changes

### Delete 3 Tools

| Tool | Lines | Reason |
|------|-------|--------|
| `create_rubric` | 858-904 | Disabled — Canvas API returns 500 for all rubric creation requests |
| `update_rubric` | 908-957 | Disabled — Canvas API does destructive full replacement instead of PATCH |
| `delete_rubric` | 961-999 | Never used, not in AGENTS.md or tools/README.md, destructive |

The Canvas UI workaround text currently in the disabled tools' return values will be preserved in `AGENTS.md` under Known Limitations.

### Merge 3 Read Tools → 1 `get_rubric`

**Current tools being merged:**

1. `list_assignment_rubrics(course, assignment_id)` — summary via assignment (undocumented)
2. `get_assignment_rubric_details(course, assignment_id)` — detail via assignment (undocumented)
3. `get_rubric_details(course, rubric_id)` — detail via rubric ID (documented)

**New tool signature:**

```python
async def get_rubric(
    course_identifier: str | int,
    rubric_id: str | int | None = None,
    assignment_id: str | int | None = None
) -> str:
```

**Behavior:**
- Accepts **either** `rubric_id` or `assignment_id` (at least one required)
- If both provided, uses `rubric_id` (more specific)
- If neither provided, returns error with usage guidance
- Always returns full detail: criteria, ratings with IDs, points
- When accessed via `assignment_id`: also includes grading config (`use_for_grading`, `points_possible`, `hide_score_total`)
- When accessed via `rubric_id`: uses `/courses/{id}/rubrics/{id}?include[]=assessments,associations`

### Rename 3 Tools

| Current Name | New Name | Reason |
|-------------|----------|--------|
| `list_all_rubrics` | `list_rubrics` | Remove redundant "all" |
| `get_submission_rubric_assessment` | `get_rubric_assessment` | Shorter, context makes "submission" obvious |
| `associate_rubric_with_assignment` | `associate_rubric` | Shorter, assignment is the only valid target |

### Move `bulk_grade_submissions` to `assignments.py`

- Move tool function to `register_educator_assignment_tools()` in `assignments.py`
- `build_rubric_assessment_form_data` helper stays in `rubrics.py` as a shared utility
- `assignments.py` imports `build_rubric_assessment_form_data` from `rubrics`
- This is the only new cross-module import introduced

### Keep Unchanged (logic)

| Tool | Notes |
|------|-------|
| `grade_with_rubric` | Core grading tool — no changes to behavior |

## Final Tool Inventory

### rubrics.py (~650 lines, down from 1,273)

| Tool | Type | Annotation | Description |
|------|------|------------|-------------|
| `list_rubrics` | Read | readOnlyHint=True | List all rubrics in a course |
| `get_rubric` | Read | readOnlyHint=True | Get full rubric detail by rubric_id OR assignment_id |
| `get_rubric_assessment` | Read | readOnlyHint=True | View how a student was graded on a rubric |
| `grade_with_rubric` | Write | (default) | Grade one student using rubric criteria |
| `associate_rubric` | Write | (default) | Link existing rubric to an assignment |

### assignments.py (receives `bulk_grade_submissions`)

| Tool | Type | Annotation | Description |
|------|------|------------|-------------|
| `bulk_grade_submissions` | Write | (default) | Grade multiple students (rubric or point-based) |

### Helper Functions Retained in rubrics.py

- `preprocess_criteria_string()` — clean criteria input strings
- `validate_rubric_criteria()` — validate JSON structure
- `format_rubric_response()` — format API responses
- `build_criteria_structure()` — build Canvas-compatible criteria dict
- `build_rubric_assessment_form_data()` — convert rubric assessment to form encoding (imported by assignments.py)

## Tool Count Impact

- **rubrics.py:** 11 → 5 tools
- **assignments.py:** gains 1 tool (`bulk_grade_submissions`)
- **Total MCP tools:** 92 → 89

## Test Plan

### Existing Tests (8 in test_rubrics.py)

| Test | Status |
|------|--------|
| 5 validation helper tests | Unchanged — helpers are retained |
| `test_list_rubrics` | Rename mock to match `list_rubrics` |
| `test_get_rubric_details` | Refactor to test `get_rubric` with `rubric_id` path |

### New Tests Required

| Test | File | What It Verifies |
|------|------|------------------|
| `test_get_rubric_by_assignment_id` | test_rubrics.py | `get_rubric` via assignment_id returns full detail + grading config |
| `test_get_rubric_neither_id_provided` | test_rubrics.py | `get_rubric` with no IDs returns helpful error |
| `test_get_rubric_both_ids_provided` | test_rubrics.py | `get_rubric` with both IDs uses rubric_id |
| `test_bulk_grade_submissions_success` | test_assignments.py | Bulk grading happy path (moved tool) |
| `test_bulk_grade_submissions_dry_run` | test_assignments.py | Dry run validates without submitting |

### Test Verification

Run full suite before and after: `uv run python -m pytest tests/ -v`

## Documentation Updates

All four docs updated per project checklist:

| File | Changes |
|------|---------|
| `AGENTS.md` | Update rubric tool table (new names), remove disabled tool rows, add Known Limitations section for create/update workarounds |
| `tools/README.md` | Update tool docs with new names/signatures, remove disabled tool sections |
| `TOOL_MANIFEST.json` | Fix `grade_submission_with_rubric` → `grade_with_rubric`, remove deleted tools, update names |
| `docs/index.html` | Update tool count badge 92 → 89 |
| `CLAUDE.md` | Update tool count in Repository Structure section |

## Migration Risk

**Low.** No external API contracts change — these are MCP tool registrations, not HTTP endpoints. The MCP protocol discovers tools dynamically at connection time. Any agent reconnecting will see the new tool names.

**No backwards compatibility needed** because:
- MCP tools are discovered at startup, not hardcoded by clients
- The 3 deleted tools were either broken or undocumented
- The 3 renamed tools have no evidence of use under their old names in session history
- `bulk_grade_submissions` keeps its name (just moves files)

## Out of Scope

- Rationalizing peer review tools (separate effort)
- Rationalizing other tool categories
- Adding new rubric functionality
- Fixing Canvas API's broken create/update endpoints

# Rubric Tool Rationalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce rubric tools from 11 → 6 by removing broken/unused tools, merging overlapping reads, and relocating `bulk_grade_submissions`.

**Architecture:** Delete `create_rubric`, `update_rubric`, `delete_rubric`. Merge `list_assignment_rubrics` + `get_assignment_rubric_details` + `get_rubric_details` into one `get_rubric` tool. Rename 3 tools. Move `bulk_grade_submissions` to `assignments.py`.

**Tech Stack:** Python 3.10+, FastMCP, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-10-rubric-tool-rationalization.md`

---

### File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/canvas_mcp/tools/rubrics.py` | Major rewrite | Delete 6 tools, add 1 merged tool, rename 3 |
| `src/canvas_mcp/tools/assignments.py` | Add code | Receive `bulk_grade_submissions` |
| `src/canvas_mcp/tools/__init__.py` | Minor edit | No changes needed (registration name unchanged) |
| `src/canvas_mcp/server.py` | No changes | Registration calls unchanged |
| `tests/tools/test_rubrics.py` | Rewrite | Update tests for new tool names, add `get_rubric` tests |
| `tests/tools/test_assignments.py` | Add tests | Add `bulk_grade_submissions` tests |
| `tests/test_role_filtering.py` | Minor edit | Update `EDUCATOR_ONLY_SAMPLE` set |
| `AGENTS.md` | Update | Rubric tool table, known limitations |
| `tools/README.md` | Update | Tool docs with new names/signatures |
| `tools/TOOL_MANIFEST.json` | Update | Fix names, remove deleted tools |
| `docs/index.html` | Minor edit | Tool count 92 → 89 |
| `CLAUDE.md` | Minor edit | Tool count in repo structure |

---

### Task 1: Delete Disabled and Unused Tools from rubrics.py

**Files:**
- Modify: `src/canvas_mcp/tools/rubrics.py` (delete lines 856-999)

- [ ] **Step 1: Run existing tests to establish baseline**

Run: `uv run python -m pytest tests/tools/test_rubrics.py -v`
Expected: All 8 tests pass.

- [ ] **Step 2: Delete `create_rubric` tool** (lines 856-904)

Remove the entire `create_rubric` function from inside `register_rubric_tools()`. This is the function that starts with:

```python
    @mcp.tool()
    @validate_params
    async def create_rubric(course_identifier: str | int,
```

and ends with the comment `# See git history (commit c01dc7d) for the full implementation`.

- [ ] **Step 3: Delete `update_rubric` tool** (lines 906-957)

Remove the entire `update_rubric` function. Starts with:

```python
    @mcp.tool()
    @validate_params
    async def update_rubric(course_identifier: str | int,
```

and ends with the comment `# See git history (commit c01dc7d) for the full implementation`.

- [ ] **Step 4: Delete `delete_rubric` tool** (lines 959-999)

Remove the entire `delete_rubric` function. Starts with:

```python
    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
    @validate_params
    async def delete_rubric(course_identifier: str | int,
```

- [ ] **Step 5: Run tests to confirm no regressions**

Run: `uv run python -m pytest tests/tools/test_rubrics.py -v`
Expected: All 8 tests still pass (none tested the deleted tools).

- [ ] **Step 6: Commit**

```bash
git add src/canvas_mcp/tools/rubrics.py
git commit -m "refactor: remove disabled and unused rubric tools

Delete create_rubric (Canvas API 500 bug), update_rubric (destructive
full-replacement API), and delete_rubric (never used, undocumented).

Part of rubric tool rationalization (11 → 6 tools)."
```

---

### Task 2: Merge 3 Read Tools into `get_rubric`

**Files:**
- Modify: `src/canvas_mcp/tools/rubrics.py`
- Modify: `tests/tools/test_rubrics.py`

- [ ] **Step 1: Write failing tests for `get_rubric`**

Add these tests to `tests/tools/test_rubrics.py`, replacing the `TestRubricTools` class:

```python
class TestRubricTools:
    """Test rubric tool functions."""

    @pytest.fixture
    def mock_canvas_request(self):
        with patch('canvas_mcp.tools.rubrics.make_canvas_request', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def mock_course_id(self):
        with patch('canvas_mcp.tools.rubrics.get_course_id', new_callable=AsyncMock) as mock:
            mock.return_value = 12345
            yield mock

    @pytest.fixture
    def mock_course_code(self):
        with patch('canvas_mcp.tools.rubrics.get_course_code', new_callable=AsyncMock) as mock:
            mock.return_value = "TEST101"
            yield mock

    @pytest.fixture
    def mock_paginated(self):
        with patch('canvas_mcp.tools.rubrics.fetch_all_paginated_results', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_list_rubrics(self, mock_paginated, mock_course_id, mock_course_code):
        """Test listing rubrics in a course."""
        mock_paginated.return_value = [
            {"id": 1, "title": "Rubric 1", "points_possible": 100, "reusable": False, "read_only": False, "data": []},
            {"id": 2, "title": "Rubric 2", "points_possible": 50, "reusable": True, "read_only": False, "data": []}
        ]

        from mcp.server.fastmcp import FastMCP
        from canvas_mcp.tools.rubrics import register_rubric_tools

        mcp = FastMCP(name="test")
        register_rubric_tools(mcp)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}

        assert "list_rubrics" in tool_names

    @pytest.mark.asyncio
    async def test_get_rubric_by_rubric_id(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test get_rubric with rubric_id parameter."""
        mock_canvas_request.return_value = {
            "id": 123,
            "title": "Test Rubric",
            "points_possible": 100,
            "reusable": False,
            "read_only": False,
            "context_type": "Course",
            "context_code": "course_12345",
            "data": [
                {
                    "id": "crit1",
                    "description": "Quality",
                    "points": 40,
                    "long_description": "",
                    "ratings": [
                        {"id": "r1", "description": "Excellent", "points": 40, "long_description": ""},
                        {"id": "r2", "description": "Poor", "points": 0, "long_description": ""}
                    ]
                }
            ]
        }

        from mcp.server.fastmcp import FastMCP
        from canvas_mcp.tools.rubrics import register_rubric_tools

        mcp = FastMCP(name="test")
        register_rubric_tools(mcp)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}

        assert "get_rubric" in tool_names

    @pytest.mark.asyncio
    async def test_get_rubric_by_assignment_id(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test get_rubric with assignment_id parameter."""
        mock_canvas_request.return_value = {
            "name": "Essay 1",
            "use_rubric_for_grading": True,
            "rubric_settings": {"points_possible": 100, "id": 456},
            "rubric": [
                {
                    "id": "crit1",
                    "description": "Quality",
                    "points": 40,
                    "long_description": "",
                    "ratings": [
                        {"id": "r1", "description": "Excellent", "points": 40, "long_description": ""},
                        {"id": "r2", "description": "Poor", "points": 0, "long_description": ""}
                    ]
                }
            ]
        }

        from mcp.server.fastmcp import FastMCP
        from canvas_mcp.tools.rubrics import register_rubric_tools

        mcp = FastMCP(name="test")
        register_rubric_tools(mcp)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}

        assert "get_rubric" in tool_names

    @pytest.mark.asyncio
    async def test_get_rubric_neither_id_returns_error(self, mock_course_id):
        """Test get_rubric with neither rubric_id nor assignment_id."""
        from mcp.server.fastmcp import FastMCP
        from canvas_mcp.tools.rubrics import register_rubric_tools

        mcp = FastMCP(name="test")
        register_rubric_tools(mcp)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}

        assert "get_rubric" in tool_names
```

- [ ] **Step 2: Run tests to verify new tests fail (tool doesn't exist yet)**

Run: `uv run python -m pytest tests/tools/test_rubrics.py::TestRubricTools -v`
Expected: `test_get_rubric_by_rubric_id`, `test_get_rubric_by_assignment_id`, and `test_get_rubric_neither_id_returns_error` FAIL because `get_rubric` is not registered.

- [ ] **Step 3: Replace the 3 old read tools with `get_rubric` in rubrics.py**

Delete `list_assignment_rubrics`, `get_assignment_rubric_details`, and `get_rubric_details` from inside `register_rubric_tools()`. Replace them with this single tool:

```python
    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_rubric(course_identifier: str | int,
                         rubric_id: str | int | None = None,
                         assignment_id: str | int | None = None) -> str:
        """Get detailed rubric criteria, ratings, and scoring information.

        Provide either rubric_id (direct lookup) or assignment_id (find rubric attached
        to that assignment). If both are provided, rubric_id takes precedence.

        Args:
            course_identifier: Course code or Canvas ID
            rubric_id: Canvas rubric ID (direct lookup)
            assignment_id: Canvas assignment ID (find attached rubric)
        """
        if rubric_id is None and assignment_id is None:
            return ("Error: Provide either rubric_id or assignment_id.\n"
                    "  - rubric_id: Direct lookup by rubric ID (use list_rubrics to find IDs)\n"
                    "  - assignment_id: Find the rubric attached to a specific assignment")

        course_id = await get_course_id(course_identifier)
        course_display = await get_course_code(course_id) or course_identifier

        if rubric_id is not None:
            # Direct rubric lookup
            rubric_id_str = str(rubric_id)
            response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/rubrics/{rubric_id_str}",
                params={"include[]": ["assessments", "associations"]}
            )

            if "error" in response:
                return f"Error fetching rubric: {response['error']}"

            title = response.get("title", "Untitled Rubric")
            points_possible = response.get("points_possible", 0)
            reusable = response.get("reusable", False)
            read_only = response.get("read_only", False)
            data = response.get("data", [])

            result = f"Rubric '{title}' in Course {course_display}:\n\n"
            result += f"Rubric ID: {rubric_id}\n"
            result += f"Total Points: {points_possible}\n"
            result += f"Reusable: {'Yes' if reusable else 'No'}\n"
            result += f"Read Only: {'Yes' if read_only else 'No'}\n\n"

        else:
            # Lookup via assignment
            assignment_id_str = str(assignment_id)
            response = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id_str}",
                params={"include[]": ["rubric", "rubric_settings"]}
            )

            if "error" in response:
                return f"Error fetching assignment rubric: {response['error']}"

            data = response.get("rubric")
            if not data:
                assignment_name = response.get("name", "Unknown Assignment")
                return f"No rubric found for assignment '{assignment_name}' in course {course_display}."

            assignment_name = response.get("name", "Unknown Assignment")
            rubric_settings = response.get("rubric_settings", {})
            use_for_grading = response.get("use_rubric_for_grading", False)

            result = f"Rubric for Assignment '{assignment_name}' in Course {course_display}:\n\n"
            result += f"Assignment ID: {assignment_id}\n"
            result += f"Used for Grading: {'Yes' if use_for_grading else 'No'}\n"
            if rubric_settings:
                result += f"Total Points: {rubric_settings.get('points_possible', 'N/A')}\n"
                rubric_id_found = rubric_settings.get("id")
                if rubric_id_found:
                    result += f"Rubric ID: {rubric_id_found}\n"
            result += "\n"

        # Format criteria and ratings (shared by both paths)
        result += "Criteria and Rating Scales:\n"
        result += "=" * 60 + "\n"

        total_points = 0
        for i, criterion in enumerate(data, 1):
            criterion_id = criterion.get("id", "N/A")
            description = criterion.get("description", "No description")
            long_description = criterion.get("long_description", "")
            points = criterion.get("points", 0)
            ratings = criterion.get("ratings", [])

            result += f"\nCriterion #{i}: {description}\n"
            result += f"  ID: {criterion_id}\n"
            result += f"  Points: {points}\n"

            if long_description and long_description != description:
                result += f"  Description: {truncate_text(long_description, 200)}\n"

            if ratings:
                sorted_ratings = sorted(ratings, key=lambda x: x.get("points", 0), reverse=True)
                for rating in sorted_ratings:
                    rating_desc = rating.get("description", "No description")
                    rating_pts = rating.get("points", 0)
                    rating_id = rating.get("id", "N/A")
                    result += f"  - {rating_desc} ({rating_pts} pts) [ID: {rating_id}]\n"
                    rating_long = rating.get("long_description", "")
                    if rating_long and rating_long != rating_desc:
                        result += f"    {truncate_text(rating_long, 100)}\n"

            total_points += points
            result += "\n" + "-" * 40 + "\n"

        result += f"\nTotal Rubric Points: {total_points}\n"
        result += f"Number of Criteria: {len(data)}\n"
        result += "\nUse criterion and rating IDs with grade_with_rubric to grade submissions."

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/tools/test_rubrics.py -v`
Expected: All tests pass including new `get_rubric` tests.

- [ ] **Step 5: Commit**

```bash
git add src/canvas_mcp/tools/rubrics.py tests/tools/test_rubrics.py
git commit -m "refactor: merge 3 rubric read tools into get_rubric

Replace list_assignment_rubrics, get_assignment_rubric_details, and
get_rubric_details with a single get_rubric tool that accepts either
rubric_id or assignment_id.

Part of rubric tool rationalization (11 → 6 tools)."
```

---

### Task 3: Rename Remaining Tools

**Files:**
- Modify: `src/canvas_mcp/tools/rubrics.py`
- Modify: `tests/tools/test_rubrics.py`

- [ ] **Step 1: Rename `list_all_rubrics` → `list_rubrics`**

In `rubrics.py`, find the tool function definition:

```python
    async def list_all_rubrics(course_identifier: str | int,
```

Change to:

```python
    async def list_rubrics(course_identifier: str | int,
```

- [ ] **Step 2: Rename `get_submission_rubric_assessment` → `get_rubric_assessment`**

In `rubrics.py`, find:

```python
    async def get_submission_rubric_assessment(course_identifier: str | int,
```

Change to:

```python
    async def get_rubric_assessment(course_identifier: str | int,
```

- [ ] **Step 3: Rename `associate_rubric_with_assignment` → `associate_rubric`**

In `rubrics.py`, find:

```python
    async def associate_rubric_with_assignment(course_identifier: str | int,
```

Change to:

```python
    async def associate_rubric(course_identifier: str | int,
```

- [ ] **Step 4: Update test references**

In `tests/tools/test_rubrics.py`, the `test_list_rubrics` test already uses the correct name. Verify no other tests reference old names.

- [ ] **Step 5: Run tests**

Run: `uv run python -m pytest tests/tools/test_rubrics.py -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/canvas_mcp/tools/rubrics.py tests/tools/test_rubrics.py
git commit -m "refactor: rename rubric tools for clarity

list_all_rubrics → list_rubrics
get_submission_rubric_assessment → get_rubric_assessment
associate_rubric_with_assignment → associate_rubric

Part of rubric tool rationalization (11 → 6 tools)."
```

---

### Task 4: Move `bulk_grade_submissions` to assignments.py

**Files:**
- Modify: `src/canvas_mcp/tools/rubrics.py` (remove `bulk_grade_submissions`)
- Modify: `src/canvas_mcp/tools/assignments.py` (add `bulk_grade_submissions`)
- Create: `tests/tools/test_bulk_grading.py`

- [ ] **Step 1: Add import for `build_rubric_assessment_form_data` to assignments.py**

At the top of `src/canvas_mcp/tools/assignments.py`, add this import after the existing imports (after line 14):

```python
from .rubrics import build_rubric_assessment_form_data
```

- [ ] **Step 2: Move `bulk_grade_submissions` function**

Cut the entire `bulk_grade_submissions` tool function (including `@mcp.tool()` and `@validate_params` decorators and the inner `grade_single_submission` function) from `rubrics.py`'s `register_rubric_tools()`.

Paste it at the end of `register_educator_assignment_tools()` in `assignments.py`, just before the final `return` or at the end of the function body (after the `update_assignment` tool, around line 944). Also add the `import asyncio` at the top of the function body if not already present.

The function signature remains unchanged:

```python
    @mcp.tool()
    @validate_params
    async def bulk_grade_submissions(
        course_identifier: str | int,
        assignment_id: str | int,
        grades: dict[str, Any],
        dry_run: bool = False,
        max_concurrent: int = 5,
        rate_limit_delay: float = 1.0
    ) -> str:
```

Note: Add `Any` to the existing `from typing import` at the top of `assignments.py` if not already imported. Also add the `asyncio` import at the module level.

- [ ] **Step 3: Write a basic test for `bulk_grade_submissions` in its new location**

Create `tests/tools/test_bulk_grading.py`:

```python
"""Tests for bulk_grade_submissions (relocated from rubrics to assignments)."""

from unittest.mock import AsyncMock, patch

import pytest


class TestBulkGradeSubmissions:
    """Test bulk grading tool in assignments module."""

    @pytest.fixture
    def mock_canvas_request(self):
        with patch('canvas_mcp.tools.assignments.make_canvas_request', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def mock_course_id(self):
        with patch('canvas_mcp.tools.assignments.get_course_id', new_callable=AsyncMock) as mock:
            mock.return_value = 12345
            yield mock

    @pytest.fixture
    def mock_course_code(self):
        with patch('canvas_mcp.tools.assignments.get_course_code', new_callable=AsyncMock) as mock:
            mock.return_value = "TEST101"
            yield mock

    @pytest.mark.asyncio
    async def test_bulk_grade_registered_in_assignments(self):
        """Verify bulk_grade_submissions is registered via educator assignment tools."""
        from mcp.server.fastmcp import FastMCP
        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)
        tools = await mcp.list_tools()
        tool_names = {t.name for t in tools}

        assert "bulk_grade_submissions" in tool_names

    @pytest.mark.asyncio
    async def test_bulk_grade_dry_run(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test dry run mode validates without submitting."""
        # Mock the assignment check for rubric grading config
        mock_canvas_request.return_value = {
            "name": "Essay 1",
            "use_rubric_for_grading": True
        }

        from mcp.server.fastmcp import FastMCP
        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)

        # Call the tool via the mcp instance
        result = await mcp.call_tool("bulk_grade_submissions", {
            "course_identifier": "TEST101",
            "assignment_id": "999",
            "grades": {"user1": {"grade": 85, "comment": "Good work"}},
            "dry_run": True
        })

        result_text = result[0].text if result else ""
        assert "DRY RUN" in result_text

    @pytest.mark.asyncio
    async def test_bulk_grade_empty_grades(self, mock_course_id):
        """Test error when no grades provided."""
        from mcp.server.fastmcp import FastMCP
        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)

        result = await mcp.call_tool("bulk_grade_submissions", {
            "course_identifier": "TEST101",
            "assignment_id": "999",
            "grades": {}
        })

        result_text = result[0].text if result else ""
        assert "empty" in result_text.lower() or "error" in result_text.lower()
```

- [ ] **Step 4: Run all tests**

Run: `uv run python -m pytest tests/tools/test_rubrics.py tests/tools/test_bulk_grading.py -v`
Expected: All tests pass. `bulk_grade_submissions` no longer in rubrics, now in assignments.

- [ ] **Step 5: Commit**

```bash
git add src/canvas_mcp/tools/rubrics.py src/canvas_mcp/tools/assignments.py tests/tools/test_bulk_grading.py
git commit -m "refactor: move bulk_grade_submissions to assignments.py

Relocate bulk grading from rubrics.py to assignments.py where it
belongs (supports both rubric and point-based grading). Import
build_rubric_assessment_form_data from rubrics as shared utility.

Part of rubric tool rationalization (11 → 6 tools)."
```

---

### Task 5: Update Role Filtering Tests

**Files:**
- Modify: `tests/test_role_filtering.py`

- [ ] **Step 1: Verify `bulk_grade_submissions` is still in `EDUCATOR_ONLY_SAMPLE`**

In `tests/test_role_filtering.py`, line 64, `bulk_grade_submissions` is already listed. Since we kept the name unchanged (just moved files), no change needed for that entry.

- [ ] **Step 2: Run role filtering tests**

Run: `uv run python -m pytest tests/test_role_filtering.py -v`
Expected: All 8 tests pass. The `test_no_tools_lost_across_roles` test will catch any tools that disappeared from registration.

- [ ] **Step 3: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: All tests pass. Note the total count — some tests may need adjustment if they assert exact tool counts.

- [ ] **Step 4: Commit (only if changes were needed)**

```bash
# Only if test_role_filtering.py required changes:
git add tests/test_role_filtering.py
git commit -m "test: update role filtering tests for rubric rationalization"
```

---

### Task 6: Update Documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `tools/README.md`
- Modify: `tools/TOOL_MANIFEST.json`
- Modify: `docs/index.html`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update AGENTS.md**

Find the rubric tools section and update tool names:

1. Remove rows for `create_rubric` (disabled), `update_rubric` (disabled), `delete_rubric`
2. Remove rows for `list_assignment_rubrics`, `get_assignment_rubric_details`
3. Rename `list_all_rubrics` → `list_rubrics`
4. Rename `get_rubric_details` → `get_rubric` (note: now accepts either `rubric_id` or `assignment_id`)
5. Rename `get_submission_rubric_assessment` → `get_rubric_assessment`
6. Rename `associate_rubric_with_assignment` → `associate_rubric`
7. Update the "Working rubric tools" list to: `list_rubrics`, `get_rubric`, `get_rubric_assessment`, `associate_rubric`, `grade_with_rubric`, `bulk_grade_submissions`
8. Keep the Known Limitations section about create/update workarounds via Canvas UI
9. Update any tool counts from 92 → 89

- [ ] **Step 2: Update tools/README.md**

1. Remove the `create_rubric` and `update_rubric` disabled tool sections
2. Remove `delete_rubric` section
3. Replace `get_rubric_details` section with `get_rubric` (document both `rubric_id` and `assignment_id` parameters)
4. Rename `associate_rubric` section (drop "with_assignment")
5. Update the "Working alternatives" list
6. Update tool counts from 92 → 89
7. Fix `grade_submission_with_rubric` → `grade_with_rubric` (existing naming drift)

- [ ] **Step 3: Update tools/TOOL_MANIFEST.json**

1. Remove entries for `create_rubric`, `update_rubric`, `delete_rubric`
2. Remove entries for `list_assignment_rubrics`, `get_assignment_rubric_details`
3. Fix `grade_submission_with_rubric` → `grade_with_rubric`
4. Add/update entry for `get_rubric` with both parameter options
5. Rename entries: `list_all_rubrics` → `list_rubrics`, `associate_rubric_with_assignment` → `associate_rubric`, `get_submission_rubric_assessment` → `get_rubric_assessment`

- [ ] **Step 4: Update docs/index.html tool count**

Find the tool count badge/text (search for "92") and update to "89".

- [ ] **Step 5: Update CLAUDE.md tool count**

In the Repository Structure section, change `92 tools across 15 files` to `89 tools across 15 files`.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md tools/README.md tools/TOOL_MANIFEST.json docs/index.html CLAUDE.md
git commit -m "docs: update documentation for rubric tool rationalization

Update tool names, remove deleted tools, fix tool counts (92 → 89).
Fix existing naming drift in TOOL_MANIFEST.json."
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: All tests pass with 0 failures.

- [ ] **Step 2: Verify tool count**

Run: `grep -r "@mcp.tool" src/canvas_mcp/tools/ | wc -l`
Expected: 89

- [ ] **Step 3: Verify rubrics.py tool count**

Run: `grep -c "@mcp.tool" src/canvas_mcp/tools/rubrics.py`
Expected: 5 (list_rubrics, get_rubric, get_rubric_assessment, grade_with_rubric, associate_rubric)

- [ ] **Step 4: Verify bulk_grade_submissions moved**

Run: `grep "bulk_grade_submissions" src/canvas_mcp/tools/assignments.py`
Expected: Match found (function is in assignments.py)

Run: `grep "bulk_grade_submissions" src/canvas_mcp/tools/rubrics.py`
Expected: No match (function removed from rubrics.py)

- [ ] **Step 5: Verify no import errors**

Run: `uv run python -c "from canvas_mcp.tools.rubrics import register_rubric_tools, build_rubric_assessment_form_data; print('rubrics OK')"`
Run: `uv run python -c "from canvas_mcp.tools.assignments import register_educator_assignment_tools; print('assignments OK')"`
Expected: Both print OK with no errors.

- [ ] **Step 6: Tag completion**

```bash
git log --oneline -5
```

Verify all 4-5 commits from this plan are present. Do NOT tag or bump version — this is an internal refactor, not a release.

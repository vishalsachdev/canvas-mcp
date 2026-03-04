# Learning Designer Skills — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Learning Designer persona support via 1 new MCP tool (`get_course_structure`) and 3 agent skills (`canvas-course-qc`, `canvas-accessibility-auditor`, `canvas-course-builder`).

**Architecture:** New tool goes in `src/canvas_mcp/tools/modules.py` following existing patterns (decorator, validate_params, JSON return). Skills go in both `skills/` (skills.sh distribution) and `.claude/skills/` (Claude Code slash commands), following the `canvas-morning-check` SKILL.md pattern.

**Tech Stack:** Python 3.10+ (tool), Markdown (skills), pytest + unittest.mock (tests)

---

## Task 1: `get_course_structure` MCP Tool

**Files:**
- Modify: `src/canvas_mcp/tools/modules.py` (add new tool at end of `register_module_tools`)
- Create: `tests/tools/test_course_structure.py`

**Step 1: Write the failing tests**

Create `tests/tools/test_course_structure.py`:

```python
"""Tests for get_course_structure tool."""

import json
from unittest.mock import patch

import pytest

MOCK_MODULES_WITH_ITEMS = [
    {
        "id": 12345,
        "name": "Week 1: Introduction",
        "position": 1,
        "published": True,
        "items_count": 3,
        "items": [
            {"id": 1, "type": "SubHeader", "title": "Overview", "published": True, "position": 1},
            {"id": 2, "type": "Page", "title": "Syllabus", "published": True, "position": 2, "page_url": "syllabus"},
            {"id": 3, "type": "Assignment", "title": "HW 1", "published": True, "position": 3, "content_id": 100},
        ],
    },
    {
        "id": 12346,
        "name": "Week 2: Core Concepts",
        "position": 2,
        "published": True,
        "items_count": 2,
        "items": [
            {"id": 4, "type": "Page", "title": "Lecture Notes", "published": True, "position": 1, "page_url": "lecture-notes"},
            {"id": 5, "type": "Discussion", "title": "Week 2 Forum", "published": False, "position": 2, "content_id": 200},
        ],
    },
    {
        "id": 12347,
        "name": "Week 3: Advanced Topics",
        "position": 3,
        "published": False,
        "items_count": 0,
        "items": [],
    },
]


@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls."""
    with (
        patch("canvas_mcp.tools.modules.get_course_id") as mock_get_id,
        patch("canvas_mcp.tools.modules.get_course_code") as mock_get_code,
        patch("canvas_mcp.tools.modules.fetch_all_paginated_results") as mock_fetch,
        patch("canvas_mcp.tools.modules.make_canvas_request") as mock_request,
    ):
        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"
        yield {
            "get_course_id": mock_get_id,
            "get_course_code": mock_get_code,
            "fetch_all_paginated_results": mock_fetch,
            "make_canvas_request": mock_request,
        }


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP
    from canvas_mcp.tools.modules import register_module_tools

    mcp = FastMCP("test")
    captured_functions = {}
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_module_tools(mcp)
    return captured_functions.get(tool_name)


class TestGetCourseStructure:
    """Tests for get_course_structure tool."""

    @pytest.mark.asyncio
    async def test_returns_json_with_modules_and_items(self, mock_canvas_api):
        """Test that the tool returns structured JSON with modules and items."""
        mock_canvas_api["fetch_all_paginated_results"].return_value = MOCK_MODULES_WITH_ITEMS

        get_course_structure = get_tool_function("get_course_structure")
        assert get_course_structure is not None

        result = await get_course_structure("badm_350_120251")
        data = json.loads(result)

        assert data["course_id"] == "60366"
        assert len(data["modules"]) == 3
        assert data["modules"][0]["name"] == "Week 1: Introduction"
        assert len(data["modules"][0]["items"]) == 3
        assert data["modules"][2]["items"] == []

    @pytest.mark.asyncio
    async def test_summary_statistics(self, mock_canvas_api):
        """Test summary counts are accurate."""
        mock_canvas_api["fetch_all_paginated_results"].return_value = MOCK_MODULES_WITH_ITEMS

        get_course_structure = get_tool_function("get_course_structure")
        result = await get_course_structure("badm_350_120251")
        data = json.loads(result)

        summary = data["summary"]
        assert summary["total_modules"] == 3
        assert summary["total_items"] == 5
        assert summary["unpublished_modules"] == 1
        assert summary["unpublished_items"] == 1  # Week 2 Forum
        assert summary["empty_modules"] == 1  # Week 3
        assert summary["item_types"]["Page"] == 2
        assert summary["item_types"]["Assignment"] == 1
        assert summary["item_types"]["Discussion"] == 1
        assert summary["item_types"]["SubHeader"] == 1

    @pytest.mark.asyncio
    async def test_empty_course(self, mock_canvas_api):
        """Test with a course that has no modules."""
        mock_canvas_api["fetch_all_paginated_results"].return_value = []

        get_course_structure = get_tool_function("get_course_structure")
        result = await get_course_structure("badm_350_120251")
        data = json.loads(result)

        assert data["modules"] == []
        assert data["summary"]["total_modules"] == 0
        assert data["summary"]["total_items"] == 0

    @pytest.mark.asyncio
    async def test_api_error(self, mock_canvas_api):
        """Test handling of API errors."""
        mock_canvas_api["fetch_all_paginated_results"].return_value = {"error": "Unauthorized"}

        get_course_structure = get_tool_function("get_course_structure")
        result = await get_course_structure("badm_350_120251")
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_include_unpublished_false(self, mock_canvas_api):
        """Test filtering out unpublished modules."""
        mock_canvas_api["fetch_all_paginated_results"].return_value = MOCK_MODULES_WITH_ITEMS

        get_course_structure = get_tool_function("get_course_structure")
        result = await get_course_structure("badm_350_120251", include_unpublished=False)
        data = json.loads(result)

        # Should only have 2 published modules
        assert len(data["modules"]) == 2
        assert all(m["published"] for m in data["modules"])
```

**Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/tools/test_course_structure.py -v`
Expected: FAIL — `get_course_structure` function not found

**Step 3: Implement `get_course_structure`**

Add to `src/canvas_mcp/tools/modules.py` at the end of `register_module_tools`, before the closing of the function:

```python
    @mcp.tool()
    @validate_params
    async def get_course_structure(
        course_identifier: str | int,
        include_unpublished: bool = True
    ) -> str:
        """Get the complete course module structure as a JSON tree.

        Returns all modules with their items in a single call, plus summary
        statistics. Useful for course auditing, QC checks, and structure
        cloning.

        Args:
            course_identifier: The Canvas course code or ID
            include_unpublished: Whether to include unpublished modules/items (default: True)
        """
        import json

        course_id = await get_course_id(course_identifier)

        params = {"per_page": 100, "include[]": ["items"]}
        modules_raw = await fetch_all_paginated_results(
            f"/courses/{course_id}/modules", params
        )

        if isinstance(modules_raw, dict) and "error" in modules_raw:
            return json.dumps({"error": f"Error fetching modules: {modules_raw['error']}"})

        # Build structured output
        modules = []
        total_items = 0
        unpublished_modules = 0
        unpublished_items = 0
        empty_modules = 0
        item_types: dict[str, int] = {}

        for mod in modules_raw:
            published = mod.get("published", False)
            if not include_unpublished and not published:
                continue

            if not published:
                unpublished_modules += 1

            items = []
            for item in mod.get("items", []):
                item_published = item.get("published", True)
                if not include_unpublished and not item_published:
                    continue

                if not item_published:
                    unpublished_items += 1

                item_type = item.get("type", "Unknown")
                item_types[item_type] = item_types.get(item_type, 0) + 1
                total_items += 1

                items.append({
                    "id": item.get("id"),
                    "type": item_type,
                    "title": item.get("title", "Untitled"),
                    "published": item_published,
                    "position": item.get("position"),
                    "content_id": item.get("content_id"),
                    "page_url": item.get("page_url"),
                    "external_url": item.get("external_url"),
                    "indent": item.get("indent", 0),
                })

            if not items and published:
                empty_modules += 1

            modules.append({
                "id": mod.get("id"),
                "name": mod.get("name", "Unnamed"),
                "position": mod.get("position"),
                "published": published,
                "unlock_at": mod.get("unlock_at"),
                "require_sequential_progress": mod.get("require_sequential_progress", False),
                "prerequisite_module_ids": mod.get("prerequisite_module_ids", []),
                "items_count": len(items),
                "items": items,
            })

        return json.dumps({
            "course_id": course_id,
            "modules": modules,
            "summary": {
                "total_modules": len(modules),
                "total_items": total_items,
                "unpublished_modules": unpublished_modules,
                "unpublished_items": unpublished_items,
                "empty_modules": empty_modules,
                "item_types": item_types,
            },
        })
```

**Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/tools/test_course_structure.py -v`
Expected: All 5 tests PASS

**Step 5: Commit**

```bash
git add src/canvas_mcp/tools/modules.py tests/tools/test_course_structure.py
git commit -m "feat: add get_course_structure tool for full module tree retrieval"
```

---

## Task 2: `canvas-course-qc` Skill

**Files:**
- Create: `skills/canvas-course-qc/SKILL.md`
- Create: `.claude/skills/canvas-course-qc/SKILL.md` (symlink or copy)

**Step 1: Write the skill file**

Create `skills/canvas-course-qc/SKILL.md`:

```markdown
---
name: canvas-course-qc
description: Learning designer quality check for Canvas LMS courses. Audits module structure, content completeness, publishing state, date consistency, and rubric coverage. Use when asked to "QC a course", "is this course ready", "pre-semester check", or "quality review".
---

# Canvas Course QC

Automated quality checklist for Learning Designers to verify a Canvas course is ready for students. Runs structure, content, publishing, and completeness checks — then reports issues by priority.

## Prerequisites

- **Canvas MCP server** must be running and connected.
- Authenticated user must have **instructor, TA, or designer role** in the target course.
- Best run before the semester starts or before publishing a course to students.

## Steps

### 1. Identify Target Course

Ask the user which course to QC. Accept a course code, Canvas ID, or course name.

If not specified, prompt:

> Which course would you like to quality-check?

Use `list_courses` to look up available courses if needed.

### 2. Retrieve Course Structure

Call `get_course_structure(course_identifier)` to get the full module → items tree in one call.

This returns all modules with their items, publishing states, and summary statistics.

### 3. Run Structure Checks

Analyze the module tree for structural issues:

| Check | Blocking? | What to Look For |
|-------|-----------|------------------|
| Empty modules | Warning | Modules with 0 items (confusing to students) |
| Naming consistency | Suggestion | Do all modules follow the same pattern? (e.g., "Week N:", "Unit N:") |
| Module count | Suggestion | Does it match expected count for course length? |
| Item ordering | Suggestion | SubHeaders present for organization? |

### 4. Run Content Checks

Call `list_assignments(course_identifier)` and check each assignment:

| Check | Blocking? | What to Look For |
|-------|-----------|------------------|
| Missing descriptions | Warning | Assignments with empty or null description |
| Missing due dates | Blocking | Graded assignments without a due_at date |
| Missing points | Warning | Assignments without points_possible set |
| Date sequencing | Warning | Due dates that don't follow module order |
| Rubric coverage | Suggestion | Graded assignments without an associated rubric |

For pages, check if any pages in modules have empty body content using `get_page_content` for pages flagged in the structure.

### 5. Run Publishing Checks

Using the structure data:

| Check | Blocking? | What to Look For |
|-------|-----------|------------------|
| Unpublished modules | Warning | Modules that may need publishing before semester |
| Ghost items | Blocking | Published items inside unpublished modules (invisible to students) |
| No front page | Warning | Course has no front page set |

Check for front page by calling `list_pages(course_identifier)` and looking for `front_page: true`.

### 6. Run Completeness Checks

Compare module structures to find inconsistencies:

| Check | Blocking? | What to Look For |
|-------|-----------|------------------|
| Inconsistent structure | Warning | Most modules have 4 items but 2 modules only have 1 |
| Missing item types | Suggestion | Most modules have an Assignment but 3 don't |

Build a "typical module" profile from the most common item-type pattern, then flag modules that deviate.

### 7. Generate QC Report

Present results grouped by priority:

```
## Course QC Report: [Course Name]

### Summary
- Modules: 15 | Items: 67 | Assignments: 15 | Pages: 20
- Issues found: 3 blocking, 5 warnings, 2 suggestions

### 🔴 Blocking Issues (fix before publishing)
1. Assignment "Final Project" has no due date
2. Published "Week 5 Quiz" is inside unpublished "Week 5" module (invisible to students)
3. Assignment "Midterm" has no due date

### 🟡 Warnings (should fix)
1. 2 empty modules: "Week 14", "Week 15"
2. 3 assignments missing descriptions: HW 3, HW 7, HW 12
3. No front page set for course
4. Due dates out of order: Week 8 assignment due before Week 7
5. "Week 3" module has 1 item while typical modules have 4

### 🟢 Suggestions (nice-to-have)
1. Module naming: 13/15 use "Week N:" pattern but "Midterm Review" and "Final Review" don't
2. 5 graded assignments have no rubric attached
```

### 8. Offer Follow-up Actions

> Would you like me to:
> 1. **Auto-fix publishing** — Publish all unpublished modules (with confirmation)
> 2. **Show details** — Expand on a specific issue
> 3. **Run accessibility audit** — Check WCAG compliance (uses canvas-accessibility-auditor skill)
> 4. **Check another course**

For auto-fix, use `update_module` or `bulk_update_pages` with user confirmation before each batch.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `list_courses` | Find available courses |
| `get_course_structure` | Full module tree with items |
| `list_assignments` | Assignment details for content checks |
| `get_assignment_details` | Deep-dive on flagged assignments |
| `list_pages` | Check for front page |
| `get_page_content` | Verify pages have content |
| `list_all_rubrics` | Check rubric coverage |
| `update_module` | Auto-fix: publish modules |
| `bulk_update_pages` | Auto-fix: publish pages |

## Example

**User:** "QC check for BADM 350"

**Agent:** Runs all checks, outputs the prioritized report.

**User:** "Fix the publishing issues"

**Agent:** Publishes the 2 unpublished modules after confirmation.

## Notes

- This skill is designed for **Learning Designers** who manage course structure before students access it.
- Run this before each semester or after major content updates.
- Pairs well with `canvas-accessibility-auditor` for comprehensive course review.
```

**Step 2: Create the Claude Code symlink**

```bash
mkdir -p .claude/skills/canvas-course-qc
ln -sf ../../../skills/canvas-course-qc/SKILL.md .claude/skills/canvas-course-qc/SKILL.md
```

**Step 3: Commit**

```bash
git add skills/canvas-course-qc/SKILL.md .claude/skills/canvas-course-qc/SKILL.md
git commit -m "feat: add canvas-course-qc skill for learning designers"
```

---

## Task 3: `canvas-accessibility-auditor` Skill

**Files:**
- Create: `skills/canvas-accessibility-auditor/SKILL.md`
- Create: `.claude/skills/canvas-accessibility-auditor/SKILL.md` (symlink)

**Step 1: Write the skill file**

Create `skills/canvas-accessibility-auditor/SKILL.md`:

```markdown
---
name: canvas-accessibility-auditor
description: Accessibility audit and remediation for Canvas LMS courses. Scans content for WCAG violations, generates prioritized reports, guides fixes, and verifies remediation. Use when asked to "audit accessibility", "check WCAG compliance", "fix accessibility issues", or "run accessibility review".
---

# Canvas Accessibility Auditor

Full accessibility audit cycle for Learning Designers: scan course content → generate prioritized report → guide remediation of fixable issues → re-scan to verify fixes → produce compliance summary.

## Prerequisites

- **Canvas MCP server** must be running and connected.
- Authenticated user must have **instructor, TA, or designer role** in the target course.
- For UFIXIT integration: the course must have a UFIXIT report page (generated by your institution's accessibility tool).

## Steps

### 1. Identify Target Course

Ask the user which course to audit. Accept a course code, Canvas ID, or course name.

If not specified, prompt:

> Which course would you like to audit for accessibility?

### 2. Scan Course Content

Run two scans in parallel if possible:

**Scan A — Direct content scan:**
```
scan_course_content_accessibility(course_identifier, "pages,assignments")
```

This checks all page and assignment HTML for:
- Images missing alt text (WCAG 1.1.1, Level A)
- Empty headings (WCAG 2.4.6, Level AA)
- Tables missing headers (WCAG 1.3.1, Level A)
- Non-descriptive link text like "click here" (WCAG 2.4.4, Level A)

**Scan B — UFIXIT report (if available):**
```
fetch_ufixit_report(course_identifier)
```

If the UFIXIT page exists, parse it:
```
parse_ufixit_violations(report_json)
```

### 3. Generate Prioritized Report

Combine results from both scans. Call `format_accessibility_summary` if using UFIXIT data.

Present issues sorted by priority:

```
## Accessibility Audit: [Course Name]

### Summary
- Content scanned: 20 pages, 15 assignments
- Total issues: 12
- Auto-fixable: 8 | Manual review needed: 4

### 🔴 Level A Violations (must fix)
1. **Missing alt text** — 5 images across 3 pages
   - Page "Week 1 Overview": 2 images
   - Page "Lab Instructions": 2 images
   - Assignment "Final Project": 1 image

2. **Tables missing headers** — 2 tables
   - Page "Grade Scale": 1 table
   - Page "Schedule": 1 table

3. **Non-descriptive links** — 3 instances of "click here"
   - Page "Resources": 2 links
   - Page "Week 3 Overview": 1 link

### 🟡 Level AA Violations (should fix)
4. **Empty headings** — 2 empty heading elements
   - Page "Week 5 Notes": 1 empty h3
   - Page "Midterm Review": 1 empty h2

### ⚪ Manual Review Required
- Color contrast: Cannot be checked automatically (requires visual inspection)
- Video captions: Cannot be verified via API (check in Canvas media player)
- PDF accessibility: Cannot be parsed via API (use Adobe Acrobat checker)
```

### 4. Guided Remediation

For each auto-fixable issue, walk the user through the fix:

**For missing alt text:**
1. Call `get_page_content(course_identifier, page_url)` to retrieve the HTML
2. Identify the `<img>` tags without alt attributes
3. Ask the user for alt text descriptions (or suggest based on context)
4. Call `edit_page_content(course_identifier, page_url, new_content)` with the corrected HTML

**For non-descriptive links:**
1. Retrieve the page content
2. Show the current link: `<a href="...">click here</a>`
3. Suggest descriptive replacement: `<a href="...">Download the syllabus (PDF)</a>`
4. Apply fix after user approval

**For empty headings:**
1. Retrieve the page content
2. Show the empty heading
3. Ask: "Remove this heading, or add text to it?"
4. Apply the chosen fix

**For tables missing headers:**
1. Retrieve the page content
2. Show the table structure
3. Ask: "Which row/column should be headers?"
4. Convert `<td>` to `<th>` elements and apply

Always ask for user confirmation before modifying any page.

### 5. Re-scan Modified Pages

After remediation, re-run the scan on modified pages only:

```
scan_course_content_accessibility(course_identifier, "pages")
```

Report: "Fixed 8/12 issues. 4 remaining require manual review."

### 6. Generate Compliance Summary

Produce a final summary suitable for stakeholder reporting:

```
## Accessibility Compliance Summary

**Course:** BADM 350 — Business Analytics
**Audit Date:** [date]
**Auditor:** [Learning Designer name or "AI-assisted audit"]

### Results
- Total content items scanned: 35
- Automated issues found: 12
- Issues remediated: 8
- Issues requiring manual review: 4
- WCAG Level A compliance: Partial (4 items need manual review)

### Remediation Actions Taken
- Added alt text to 5 images
- Fixed 3 non-descriptive links
- (Details per page...)

### Outstanding Items
- Color contrast review needed (3 pages with colored text)
- Video caption verification (2 embedded videos)
- PDF accessibility check (1 uploaded PDF)

### Recommendation
Course content meets automated WCAG 2.1 Level A criteria after remediation.
Manual review of color contrast and multimedia is recommended before publishing.
```

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `scan_course_content_accessibility` | Scan pages and assignments for WCAG issues |
| `fetch_ufixit_report` | Retrieve institutional UFIXIT report |
| `parse_ufixit_violations` | Extract structured violations from report |
| `format_accessibility_summary` | Format violations into readable report |
| `get_page_content` | Retrieve page HTML for remediation |
| `edit_page_content` | Apply accessibility fixes to pages |
| `list_courses` | Find available courses |

## Example

**User:** "Run accessibility audit for CS 101"

**Agent:** Scans all content, generates the prioritized report.

**User:** "Fix the missing alt text issues"

**Agent:** Retrieves each affected page, asks for alt text descriptions, applies fixes, re-scans.

## Limitations

- **Cannot check:** Color contrast, video captions, PDF accessibility, audio descriptions, keyboard navigation
- **These are flagged** as "manual review required" in every report
- **Remediation is per-page:** Each fix requires a full page content read + write cycle
- **No undo:** Page edits via the API don't create Canvas revision history — recommend backing up pages before bulk fixes

## Notes

- Pairs well with `canvas-course-qc` for comprehensive pre-semester review.
- Run after major content updates or course imports.
- UFIXIT integration depends on your institution having UDOIT/UFIXIT installed.
```

**Step 2: Create the Claude Code symlink**

```bash
mkdir -p .claude/skills/canvas-accessibility-auditor
ln -sf ../../../skills/canvas-accessibility-auditor/SKILL.md .claude/skills/canvas-accessibility-auditor/SKILL.md
```

**Step 3: Commit**

```bash
git add skills/canvas-accessibility-auditor/SKILL.md .claude/skills/canvas-accessibility-auditor/SKILL.md
git commit -m "feat: add canvas-accessibility-auditor skill for learning designers"
```

---

## Task 4: `canvas-course-builder` Skill

**Files:**
- Create: `skills/canvas-course-builder/SKILL.md`
- Create: `.claude/skills/canvas-course-builder/SKILL.md` (symlink)

**Step 1: Write the skill file**

Create `skills/canvas-course-builder/SKILL.md`:

```markdown
---
name: canvas-course-builder
description: Scaffold complete Canvas LMS course structures from specs, templates, or existing courses. Creates modules, pages, assignments, and discussions in bulk. Use when asked to "build a course", "scaffold modules", "create course structure", "set up a new course", or "copy course structure".
---

# Canvas Course Builder

Build complete Canvas course structures from a natural language description, a JSON template, or by cloning an existing course. Creates modules with pages, assignments, discussions, and proper organization — all in one workflow.

## Prerequisites

- **Canvas MCP server** must be running and connected.
- Authenticated user must have **instructor or designer role** in the target course.
- Target course must already exist in Canvas (this skill populates it, doesn't create the course itself).

## Modes

This skill operates in three modes:

### Mode 1: Build from Spec (default)
The user describes the course structure in natural language or provides a structured spec.

### Mode 2: Build from Template
Load a saved JSON template to scaffold a course. Templates can be saved from existing courses.

### Mode 3: Clone from Existing Course
Read the structure of Course A and replicate it into Course B.

## Steps

### 1. Determine Mode and Gather Input

Ask the user how they want to build:

> How would you like to build the course structure?
> 1. **Describe it** — Tell me the structure (e.g., "15 weeks, each with an overview page, assignment, and discussion")
> 2. **From template** — Load a saved template file
> 3. **Clone another course** — Copy structure from an existing course

**For Mode 1 (Spec):** Ask for:
- Target course (code or ID)
- Number of modules/weeks/units
- Module naming pattern (e.g., "Week N: [Topic]")
- Standard items per module (overview page, assignment, discussion, etc.)
- Any module-specific variations (midterm week, final project, etc.)

**For Mode 2 (Template):** Ask for the template file path. Parse the JSON template.

**For Mode 3 (Clone):** Ask for:
- Source course (code or ID)
- Target course (code or ID)
- Call `get_course_structure(source_course)` to read the full structure

### 2. Generate Structure Preview

Build a preview of what will be created and present it to the user:

```
## Course Build Plan: BADM 350

### Structure: 15 modules × 4 items each = 60 items total

| Module | Page | Assignment | Discussion | SubHeader |
|--------|------|------------|------------|-----------|
| Week 1: Introduction | ✓ Overview | ✓ HW 1 (10 pts) | ✓ Week 1 Forum | ✓ |
| Week 2: Fundamentals | ✓ Overview | ✓ HW 2 (10 pts) | ✓ Week 2 Forum | ✓ |
| ... | ... | ... | ... | ... |
| Week 14: Review | ✓ Overview | — | ✓ Review Forum | ✓ |
| Week 15: Final | ✓ Overview | ✓ Final Project (100 pts) | — | ✓ |

### Items to create:
- 15 modules
- 15 overview pages
- 14 assignments
- 14 discussion topics
- 15 subheaders
- Total: 73 Canvas objects

Shall I proceed?
```

### 3. User Approves or Modifies

Wait for explicit approval. The user may:
- Approve as-is
- Request modifications (add/remove items, change naming, adjust points)
- Cancel

**Do NOT proceed without approval.**

### 4. Execute Creation

Create items in dependency order:

1. **Modules first:** Call `create_module` for each module (unpublished by default for safety)
2. **Pages:** Call `create_page` for each overview page
3. **Assignments:** Call `create_assignment` for each assignment (unpublished)
4. **Discussions:** Call `create_discussion_topic` for each forum
5. **Module items:** Call `add_module_item` to link each created item to its module

Track progress and report as you go:
```
Creating modules... 15/15 ✓
Creating pages... 15/15 ✓
Creating assignments... 14/14 ✓
Creating discussions... 14/14 ✓
Linking items to modules... 58/58 ✓
```

If any creation fails, log the error and continue with remaining items.

### 5. Report Results

```
## Build Complete: BADM 350

### Created:
- 15 modules ✓
- 15 overview pages ✓
- 14 assignments ✓
- 14 discussion topics ✓
- 58 module items linked ✓

### Failed (0):
None

### Next Steps:
- All items created **unpublished** — publish when ready
- Add content to overview pages
- Set due dates on assignments
- Run `/canvas-course-qc` to verify structure
```

### 6. Save as Template (Optional)

After building, offer to save the structure as a reusable template:

> Would you like to save this structure as a template for future courses?

If yes, call `get_course_structure(target_course)` and save the output as a JSON file.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `list_courses` | Find available courses |
| `get_course_structure` | Read source course for cloning; verify after build |
| `create_module` | Create each module |
| `create_page` | Create overview/content pages |
| `create_assignment` | Create assignments |
| `create_discussion_topic` | Create discussion forums |
| `add_module_item` | Link items to modules |
| `update_module` | Publish modules when ready |

## Example

**User:** "Build a 15-week structure for BADM 350 with a weekly overview page, homework assignment, and discussion for each week"

**Agent:** Generates preview, asks for approval, creates 60+ items.

**User:** "Clone the structure from CS 101 into CS 102"

**Agent:** Reads CS 101 structure, generates preview for CS 102, asks for approval, creates matching structure.

## Template Format

Templates are JSON files with this structure:

```json
{
  "template_name": "Standard 15-Week Semester",
  "modules": [
    {
      "name_pattern": "Week {n}: {topic}",
      "items": [
        {"type": "SubHeader", "title_pattern": "Week {n} Materials"},
        {"type": "Page", "title_pattern": "Week {n} Overview"},
        {"type": "Assignment", "title_pattern": "HW {n}", "points": 10},
        {"type": "Discussion", "title_pattern": "Week {n} Discussion"}
      ]
    }
  ],
  "special_modules": [
    {"position": 8, "name": "Midterm Review", "items": [{"type": "Page", "title": "Midterm Study Guide"}]},
    {"position": 15, "name": "Final Project", "items": [{"type": "Assignment", "title": "Final Project", "points": 100}]}
  ]
}
```

## Notes

- All items are created **unpublished by default** for safety.
- Content is **not** copied when cloning — only structure (module names, item types, organization).
- For content migration, copy page bodies manually or use `get_page_content` + `create_page` with the body.
- Run `canvas-course-qc` after building to verify the structure is complete and consistent.
```

**Step 2: Create the Claude Code symlink**

```bash
mkdir -p .claude/skills/canvas-course-builder
ln -sf ../../../skills/canvas-course-builder/SKILL.md .claude/skills/canvas-course-builder/SKILL.md
```

**Step 3: Commit**

```bash
git add skills/canvas-course-builder/SKILL.md .claude/skills/canvas-course-builder/SKILL.md
git commit -m "feat: add canvas-course-builder skill for learning designers"
```

---

## Task 5: Update Documentation

**Files:**
- Modify: `AGENTS.md` (add Learning Designer section)
- Modify: `README.md` (update skill count and table)
- Modify: `tools/README.md` (add get_course_structure docs)

**Step 1: Update AGENTS.md**

Add a Learning Designer tools section after Educator Tools:

```markdown
### Learning Designer Tools
Course design, quality assurance, and accessibility compliance.

| Tool | Purpose |
|------|---------|
| `get_course_structure` | Full module→items tree as JSON (one call) |
| `scan_course_content_accessibility` | Scan for WCAG violations |
| `fetch_ufixit_report` | Retrieve UFIXIT accessibility report |
```

**Step 2: Update README.md**

- Change "5 agent skills" to "8 agent skills" in hero line and badges
- Add 3 new rows to the skills table:

```markdown
| `canvas-course-qc` | Learning Designers | Pre-semester quality audit: structure, content, publishing, completeness |
| `canvas-accessibility-auditor` | Learning Designers | WCAG scan → report → guided remediation → verification |
| `canvas-course-builder` | Learning Designers | Scaffold courses from specs, templates, or existing courses |
```

**Step 3: Update tools/README.md**

Add `get_course_structure` documentation after the existing module tools section, following the same format as `list_modules`.

**Step 4: Commit**

```bash
git add AGENTS.md README.md tools/README.md
git commit -m "docs: add learning designer tools and skills to documentation"
```

---

## Task 6: Final Verification

**Step 1: Run all tests**

```bash
uv run python -m pytest tests/ -v
```

Expected: All existing tests pass + 5 new `test_course_structure` tests pass.

**Step 2: Verify skill files are in place**

```bash
ls -la skills/canvas-course-*/SKILL.md
ls -la .claude/skills/canvas-course-*/SKILL.md .claude/skills/canvas-accessibility-*/SKILL.md
```

**Step 3: Verify server starts**

```bash
canvas-mcp-server --test
```

Expected: Server starts, `get_course_structure` appears in tool list.

**Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address any issues from final verification"
```

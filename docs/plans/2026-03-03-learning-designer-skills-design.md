# Learning Designer Skills — Design Document

**Date:** 2026-03-03
**Status:** Approved
**Goal:** Add Learning Designer persona support to Canvas MCP via 3 new skills + 1 new tool

## Context

Canvas MCP has 85+ tools and 5 skills targeting students and educators. Learning Designers (LDs) — who build, audit, and maintain courses — have zero dedicated skills despite being heavy Canvas users. The existing tools (modules, pages, assignments, accessibility) cover LD primitives, but lack orchestration for LD-specific workflows.

## Persona: Learning Designer

Full-spectrum role covering:
- **Course builder** — scaffolds new courses from scratch (modules, pages, assignments, rubrics)
- **Course QC/auditor** — reviews for quality, accessibility, completeness, consistency
- **Content developer** — creates/updates content within existing structures
- **Content migrator** — replicates structures and content across courses/semesters

Works across multiple courses simultaneously. Needs both multi-course maintenance and deep single-course builds.

## Pain Points (All Four Selected)

1. **Course scaffolding** — manually creating 15+ modules with items = 90+ tool calls
2. **Accessibility compliance** — UFIXIT reports exist but remediation is page-by-page manual work
3. **QC and consistency** — no automated checks for published state, dates, descriptions, rubrics
4. **Content migration** — no cross-course copy or template workflows

## Approach: Skills-First (Approach A)

3 focused skills composing existing tools + 1 new supporting tool. Each skill ships independently and works across 40+ agents via skills.sh.

---

## Skill 1: `canvas-course-builder`

**Purpose:** Scaffold complete course structures from specs, templates, or existing courses.

**Triggers:** "Build a course", "Scaffold modules", "Create week 1-15 structure", "Set up new course"

### Modes

1. **From spec** — LD describes structure in natural language or JSON
2. **From template** — Load a saved template (e.g., "standard-15-week")
3. **From existing course** — Copy structure from Course A to Course B

### Workflow

```
1. Gather course spec (natural language, JSON, or source course ID)
2. Generate structure preview (modules × items, naming, dates)
3. User approves/modifies plan
4. Execute creation (parallel subagents for speed)
5. Report results with success/failure per item
```

### Existing Tools Used
- `create_module`, `add_module_item`, `create_page`, `create_assignment`
- `create_discussion_topic`
- `get_course_structure` (NEW — needed for copy mode and QC)
- `list_modules`, `list_module_items` (read existing structure)

### Template System
- Templates stored as JSON in user's workspace or project `templates/` dir
- Save: read course structure → serialize to template JSON
- Load: parse template → generate creation plan → execute
- Standard templates: "15-week semester", "8-week accelerated", "workshop"

---

## Skill 2: `canvas-accessibility-auditor`

**Purpose:** Full accessibility audit → prioritized report → guided remediation → verification.

**Triggers:** "Audit accessibility", "Run accessibility check", "Fix accessibility issues", "WCAG review"

### Workflow

```
1. Scan course content
   - scan_course_content_accessibility(course, "pages,assignments,discussions,syllabus")
   - fetch_ufixit_report (if institutional UFIXIT page exists)

2. Generate prioritized report
   - Group by content item (Page X: 3 issues)
   - Sort by: WCAG Level A → AA → severity → frequency
   - Classify: auto-fixable vs. manual review required

3. Guided remediation (per issue)
   - Propose specific fix with before/after preview
   - LD approves → edit_page_content applies fix
   - Categories: missing alt text, empty headings, bad link text, tables

4. Re-scan modified pages to verify fixes

5. Generate compliance summary
   - Pages scanned, issues found, issues fixed, remaining
   - WCAG conformance level achieved
   - Exportable for stakeholder reporting
```

### Existing Tools Used
- `scan_course_content_accessibility`, `fetch_ufixit_report`
- `parse_ufixit_violations`, `format_accessibility_summary`
- `get_page_content`, `edit_page_content`

### Limitations (Document in Skill)
- Cannot check color contrast (requires rendering)
- Cannot check video captions (requires media analysis)
- Cannot check PDF accessibility (requires document parsing)
- These are flagged as "manual review required" in the report

---

## Skill 3: `canvas-course-qc`

**Purpose:** Automated quality checklist for course readiness.

**Triggers:** "QC check", "Is this course ready?", "Run quality review", "Pre-semester checklist"

### Quality Checks

**Structure:**
- All modules have items? (flag empty modules)
- Module naming consistent? (detect pattern: "Week N:", "Unit N:", etc.)
- Items in logical order? SubHeaders present?
- Module count matches expected (e.g., 15 for semester course)

**Content:**
- All assignments have descriptions? Points? Due dates?
- Due dates sequential? (Week 1 before Week 2)
- Rubrics attached to graded assignments?
- All pages have content? (not blank)
- Syllabus page exists and has content?

**Publishing:**
- Unpublished modules that should be published?
- Published items in unpublished modules? (invisible to students)
- Front page set?

**Completeness:**
- All modules have same structure? (e.g., all have overview + assignment)
- Missing items compared to sibling modules?

### Workflow

```
1. Inventory: get_course_structure (one call for full tree)
2. Run all checks against inventory
3. Generate report: Pass/Fail per category
   - Blocking (will confuse students)
   - Warning (should fix before launch)
   - Suggestion (nice-to-have)
4. Optional auto-fix: publish modules, update settings (with confirmation)
```

### Existing Tools Used
- `get_course_structure` (NEW), `list_assignments`, `get_assignment_details`
- `list_pages`, `get_page_content`, `list_all_rubrics`
- `update_page_settings`, `bulk_update_pages`, `update_module` (for auto-fix)

---

## New Tool: `get_course_structure`

**Purpose:** Return full module → items tree in a single call.

**Why needed:** Currently requires `list_modules` + N × `list_module_items` calls. For a 15-module course, that's 16 API calls. This tool uses Canvas's `include[]=items` parameter to get everything in 1-2 paginated calls.

**Parameters:**
- `course_identifier` (str | int): Course code or ID
- `include_unpublished` (bool, default: true): Include unpublished modules/items

**Returns:**
```json
{
  "course_id": 12345,
  "modules": [
    {
      "id": 123, "name": "Week 1", "position": 1, "published": true,
      "items_count": 5,
      "items": [
        {"id": 1, "type": "Page", "title": "Overview", "published": true},
        {"id": 2, "type": "Assignment", "title": "HW 1", "points": 100, "due_at": "..."},
        {"id": 3, "type": "Discussion", "title": "Week 1 Forum"}
      ]
    }
  ],
  "summary": {
    "total_modules": 15,
    "total_items": 67,
    "unpublished_modules": 1,
    "unpublished_items": 3,
    "item_types": {"Page": 20, "Assignment": 15, "Discussion": 15, "SubHeader": 15, "ExternalUrl": 2}
  }
}
```

**Implementation:** Add to `src/canvas_mcp/tools/modules.py`. Uses existing `list_modules` with `include[]=items` query parameter.

---

## Implementation Priority

| Order | Deliverable | Effort | Dependencies |
|-------|------------|--------|-------------|
| 1 | `get_course_structure` tool | Small | None — pure API call |
| 2 | `canvas-course-qc` skill | Medium | Needs get_course_structure |
| 3 | `canvas-accessibility-auditor` skill | Medium | Uses existing tools only |
| 4 | `canvas-course-builder` skill | Large | Needs get_course_structure, benefits from QC for verification |

**Rationale:** QC first because it's the quickest LD win (audit existing courses immediately). Accessibility second (existing tools + orchestration). Builder last (largest scope, benefits from having QC to verify output).

---

## Skills Distribution

All 3 skills will be:
- Available as Claude Code slash commands (`.claude/skills/`)
- Published to skills.sh for 40+ agents (`skills/` directory)
- Following existing skill patterns from canvas-morning-check, canvas-week-plan, etc.

## Success Criteria

- LD can scaffold a 15-week course in < 5 minutes (vs. 2+ hours manually)
- LD can run accessibility audit + fix common issues in one session
- LD can verify course readiness with a single command
- All 3 skills work across Claude Code, Cursor, Codex, and other agents

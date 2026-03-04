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

Call `get_course_structure(course_identifier)` to get the full module-to-items tree in one call.

This returns all modules with their items, publishing states, and summary statistics.

### 3. Run Structure Checks

Analyze the module tree for structural issues:

| Check | Priority | What to Look For |
|-------|----------|------------------|
| Empty modules | Warning | Modules with 0 items (confusing to students) |
| Naming consistency | Suggestion | Do all modules follow the same pattern? (e.g., "Week N:", "Unit N:") |
| Module count | Suggestion | Does it match expected count for course length? |
| Item ordering | Suggestion | SubHeaders present for organization? |

### 4. Run Content Checks

Call `list_assignments(course_identifier)` and check each assignment:

| Check | Priority | What to Look For |
|-------|----------|------------------|
| Missing due dates | Blocking | Graded assignments without a due_at date |
| Missing descriptions | Warning | Assignments with empty or null description |
| Missing points | Warning | Assignments without points_possible set |
| Date sequencing | Warning | Due dates that don't follow module order |
| Rubric coverage | Suggestion | Graded assignments without an associated rubric |

For pages, check if any pages in modules have empty body content using `get_page_content` for pages flagged in the structure.

### 5. Run Publishing Checks

Using the structure data:

| Check | Priority | What to Look For |
|-------|----------|------------------|
| Ghost items | Blocking | Published items inside unpublished modules (invisible to students) |
| Unpublished modules | Warning | Modules that may need publishing before semester |
| No front page | Warning | Course has no front page set |

Check for front page by calling `list_pages(course_identifier)` and looking for `front_page: true`.

### 6. Run Completeness Checks

Compare module structures to find inconsistencies:

| Check | Priority | What to Look For |
|-------|----------|------------------|
| Inconsistent structure | Warning | Most modules have 4 items but some only have 1 |
| Missing item types | Suggestion | Most modules have an Assignment but some don't |

Build a "typical module" profile from the most common item-type pattern, then flag modules that deviate.

### 7. Generate QC Report

Present results grouped by priority:

```
## Course QC Report: [Course Name]

### Summary
- Modules: 15 | Items: 67 | Assignments: 15 | Pages: 20
- Issues found: 3 blocking, 5 warnings, 2 suggestions

### Blocking Issues (fix before publishing)
1. Assignment "Final Project" has no due date
2. Published "Week 5 Quiz" is inside unpublished "Week 5" module (invisible to students)
3. Assignment "Midterm" has no due date

### Warnings (should fix)
1. 2 empty modules: "Week 14", "Week 15"
2. 3 assignments missing descriptions: HW 3, HW 7, HW 12
3. No front page set for course
4. Due dates out of order: Week 8 assignment due before Week 7
5. "Week 3" module has 1 item while typical modules have 4

### Suggestions (nice-to-have)
1. Module naming: 13/15 use "Week N:" pattern but "Midterm Review" and "Final Review" don't
2. 5 graded assignments have no rubric attached
```

### 8. Offer Follow-up Actions

After presenting the report, offer actionable next steps:

> Would you like me to:
> 1. **Auto-fix publishing** -- Publish all unpublished modules (with confirmation)
> 2. **Show details** -- Expand on a specific issue
> 3. **Run accessibility audit** -- Check WCAG compliance (uses canvas-accessibility-auditor skill)
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

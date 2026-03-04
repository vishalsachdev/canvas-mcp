---
name: canvas-course-builder
description: Scaffold complete Canvas LMS course structures from specs, templates, or existing courses. Creates modules, pages, assignments, and discussions in bulk. Use when asked to "build a course", "scaffold modules", "create course structure", "set up a new course", or "copy course structure".
---

# Canvas Course Builder

Build complete Canvas course structures from a natural language description, a JSON template, or by cloning an existing course. Creates modules with pages, assignments, discussions, and proper organization in one workflow.

## Prerequisites

- **Canvas MCP server** must be running and connected.
- Authenticated user must have **instructor or designer role** in the target course.
- Target course must already exist in Canvas (this skill populates it, does not create the course itself).

## Modes

This skill operates in three modes:

### Mode 1: Build from Spec (default)
The user describes the course structure in natural language or provides a structured spec.

### Mode 2: Build from Template
Load a saved JSON template to scaffold a course.

### Mode 3: Clone from Existing Course
Read the structure of Course A and replicate it into Course B.

## Steps

### 1. Determine Mode and Gather Input

Ask the user how they want to build:

> How would you like to build the course structure?
> 1. **Describe it** -- Tell me the structure (e.g., "15 weeks, each with an overview page, assignment, and discussion")
> 2. **From template** -- Load a saved template file
> 3. **Clone another course** -- Copy structure from an existing course

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
## Course Build Plan: [Course Name]

### Structure: 15 modules x 4 items each = 60 items total

| Module | Page | Assignment | Discussion | SubHeader |
|--------|------|------------|------------|-----------|
| Week 1: Introduction | Overview | HW 1 (10 pts) | Week 1 Forum | Materials |
| Week 2: Fundamentals | Overview | HW 2 (10 pts) | Week 2 Forum | Materials |
| ... | ... | ... | ... | ... |
| Week 14: Review | Overview | -- | Review Forum | Materials |
| Week 15: Final | Overview | Final Project (100 pts) | -- | Materials |

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
Creating modules... 15/15 done
Creating pages... 15/15 done
Creating assignments... 14/14 done
Creating discussions... 14/14 done
Linking items to modules... 58/58 done
```

If any creation fails, log the error and continue with remaining items.

### 5. Report Results

```
## Build Complete: [Course Name]

### Created:
- 15 modules
- 15 overview pages
- 14 assignments
- 14 discussion topics
- 58 module items linked

### Failed (0):
None

### Next Steps:
- All items created **unpublished** -- publish when ready
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

## Example

**User:** "Build a 15-week structure for BADM 350 with a weekly overview page, homework, and discussion"

**Agent:** Generates preview, asks for approval, creates 60+ items.

**User:** "Clone the structure from CS 101 into CS 102"

**Agent:** Reads CS 101 structure, generates preview for CS 102, asks approval, creates matching structure.

## Notes

- All items are created **unpublished by default** for safety.
- Content is **not** copied when cloning -- only structure (module names, item types, organization).
- For content migration, copy page bodies using `get_page_content` + `create_page` with the body.
- Run `canvas-course-qc` after building to verify the structure is complete and consistent.

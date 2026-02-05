# Local-First Content Authoring Workflow

**Date:** 2026-02-04
**Status:** Brainstorm complete, ready for planning

## What We're Building

A local-first content authoring system that lets teachers:
1. **Pull** entire courses from Canvas as markdown files
2. **Edit** content locally in their preferred editor (VS Code, Cursor, etc.)
3. **Apply** institutional HTML templates (Franklin School branding)
4. **Push** content back to Canvas as **unpublished drafts** (never overwrites)

### Target Workflow

```
Teacher in Cursor/VS Code:
  ↓
"Pull my Canvas course"  →  Local markdown files created
  ↓
Edit markdown files locally (with MCP chatbot assistance)
  ↓
"Push this module to Canvas"  →  Creates unpublished drafts
  ↓
Teacher reviews in Canvas, publishes manually
```

## Why This Approach

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Push behavior | Create NEW unpublished drafts | Safety first - never overwrite existing Canvas content |
| Pull behavior | Overwrite local files | Local is working copy, Canvas is source of truth for existing content |
| Conflict handling | None needed | Push creates new drafts, no conflicts possible |
| Template location | Local `templates/` folder | Teachers control their own templates |
| Naming on push | Add "- Revised" suffix | Distinguishes drafts from originals |

### Safety Philosophy

**Canvas is sacred.** Any push operation:
- Creates a NEW item (page, assignment, discussion)
- Sets `published: false` by default
- Adds "- Revised" suffix to title
- Teacher must manually review and publish

This eliminates accidental data loss and gives teachers full control.

## Folder Structure Convention

```
courses/
└── {course-name}/
    ├── course.yaml              # Course metadata + Canvas ID
    ├── templates/
    │   ├── franklin-page.html   # Institutional page template
    │   └── franklin-assignment.html
    └── modules/
        └── {module-name}/
            ├── module.yaml      # Module metadata + Canvas ID
            ├── _lesson-plan.md  # Underscore prefix = don't push
            ├── reading.md       # → Canvas Page
            ├── project.md       # → Canvas Assignment
            └── discussion.md    # → Canvas Discussion
```

### Frontmatter Schema

```yaml
---
type: page | assignment | discussion
title: "Human-readable title"
template: franklin-page          # Optional, references templates/ folder
canvas_id: 12345                 # Populated after pull, null for new content

# Assignment-specific:
points: 100
due_at: 2026-03-15T23:59:00
submission_types: [online_text_entry, online_upload]

# Discussion-specific:
graded: false
require_initial_post: true
---

# Content starts here...
```

## Proposed MCP Tools

### Workspace Setup
| Tool | Description |
|------|-------------|
| `init_workspace(course_id, local_path)` | Create folder structure from Canvas course |
| `pull_course(course_id, local_path)` | Download all content as markdown (overwrites local) |
| `pull_module(course_id, module_id, local_path)` | Download single module |

### Content Push (Creates Unpublished Drafts)
| Tool | Description |
|------|-------------|
| `push_file(file_path, course_id)` | Transform + push single file as draft |
| `push_module(module_path, course_id)` | Push all files in module folder |
| `push_course(course_path)` | Push entire course |

### Preview & Status
| Tool | Description |
|------|-------------|
| `preview_transform(file_path)` | Show HTML output without pushing |
| `list_workspace_files(course_path)` | Show all local files and their types |

## Template System

Templates are Jinja2-compatible HTML files:

```html
<!-- templates/franklin-page.html -->
<div class="franklin-page">
  <header class="franklin-header">
    <img src="logo.png" alt="Franklin School">
  </header>
  <main class="franklin-content">
    {{ content }}
  </main>
  <footer class="franklin-footer">
    <!-- Standard footer -->
  </footer>
</div>
```

- `{{ content }}` placeholder receives rendered markdown
- Templates stored locally, not in Canvas
- Fallback to plain markdown→HTML if no template specified

## Content Type Detection

From frontmatter `type:` field, or inferred from filename:
- `*-page.md`, `reading.md`, `lesson.md` → Page
- `*-assignment.md`, `project.md`, `homework.md` → Assignment
- `*-discussion.md`, `discussion.md` → Discussion
- `_*.md` (underscore prefix) → Skip (teacher notes)

## Technical Notes

### Build On Existing Infrastructure
- Use existing `create_page()`, `create_assignment()`, etc. internally
- Leverage `make_canvas_request()` for all API calls
- Follow `@validate_params` pattern for new tools
- Store workspace state in local JSON (no external database)

### HTML Conversion
- Markdown → HTML via Python `markdown` library
- Template rendering via `jinja2`
- Both are lightweight, no heavy dependencies

## Open Questions

1. **Module creation:** If local module doesn't exist in Canvas, create it?
2. **File attachments:** How to handle images/files referenced in markdown?
3. **Canvas ID tracking:** Store in frontmatter or separate `.sync-state/` file?
4. **Batch preview:** Preview all files in a module at once?

## Success Criteria

- [ ] Teacher can pull an existing course to local markdown files
- [ ] Teacher can edit markdown and push as unpublished Canvas drafts
- [ ] Institutional templates are applied correctly
- [ ] No existing Canvas content is ever overwritten
- [ ] Works in Cursor/VS Code with MCP chatbot

## Related Ideas (Future)

- **Sync status dashboard:** Show which files are newer locally vs Canvas
- **Selective pull:** Pull only specific content types
- **Template library:** Shared institutional templates
- **Version history:** Track changes over time locally

---

**Next step:** Run `/workflows:plan` to create implementation plan

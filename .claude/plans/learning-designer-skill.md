# Plan: Learning Designer Persona Skill

**Status:** Backlog — revisit after workshop (late Feb 2026)
**Context:** Workshop for learning designers next week; this plan captures the research and design for a `/learning-design` skill.

---

## Strategic Context

Canvas MCP (87 tools) has a future as a **persona-based skill collection** — keep the MCP monolithic, add persona-specific Claude Code skills as guided entry points. Research validated this approach:

- [awesome-mcp-personas](https://github.com/toolprint/awesome-mcp-personas) — persona-based MCP groupings are an emerging pattern
- [Armin Ronacher](https://lucumr.pocoo.org/2025/12/13/skills-vs-mcp/) — Skills fill the gap between "too long to eagerly load, too short to tell the agent how to use it"
- [David Cramer](https://cra.mr/mcp-skills-and-agents/) — MCP provides access, Skills provide expertise

### Existing Skills (renamed Feb 2026)
- `/morning-check` — Educator morning health check
- `/week-plan` — Student weekly planner

### Proposed Skills Roadmap
1. `/learning-design` — **This plan** (learning designer persona)
2. `/peer-review` — Peer review analytics pipeline (13 tools, unique differentiator)
3. `/grade-batch` — Assignment → rubric → bulk grade workflow
4. `/communicate` — Announcement + discussion + reminder orchestration
5. `/accessibility` — Scan → parse → report → remediate

---

## Learning Designer Persona

**Key distinction:** An educator *uses* the course; a learning designer *architects* it. Core question: "Is my course design working?" (not "How are my students doing?")

### What They Care About

| Need | Existing Tools | Gap |
|------|---------------|-----|
| **Course structure audit** | `get_course_content_overview`, `list_modules`, `list_pages`, `list_assignments` | No single structural map; needs 4-5 chained calls |
| **Assessment-objective alignment** | `get_assignment_details`, `list_all_rubrics`, `associate_rubric_with_assignment` | Canvas API doesn't expose learning outcomes; rubric creation disabled (API bug) |
| **Workload pacing analysis** | `list_assignments` (has due dates, points) | No tool aggregates by week to show point load distribution |
| **Accessibility compliance** | `scan_course_content_accessibility`, `fetch_ufixit_report`, `parse_ufixit_violations`, `format_accessibility_summary` | Solid — 4 tools covering full audit cycle |
| **Peer review effectiveness** | 13 peer review tools | Strongest area — no competitor has this depth |
| **Content consistency/QA** | Individual queries per module/page/assignment | No automated course QA checklist (CCEC v3.0 has 70 criteria) |
| **Bulk scaffolding** | `create_module`, `add_module_item`, `create_page`, `bulk_update_pages` | Works but tedious; `execute_typescript` better for full course skeleton |

### Blocked by Canvas API
- Learning objectives/outcomes — not exposed via REST API
- Rubric creation — Canvas returns 500 errors
- Mastery Paths — no API support

---

## Proposed Skill Design: `/learning-design`

### Subcommand Pattern
```
/learning-design audit     → Course structure + accessibility + QA checks
/learning-design pacing    → Workload heatmap across the semester
/learning-design reviews   → Peer review quality analysis
/learning-design publish   → Bulk module/page publishing workflow
```

### Workflow 1: Course Audit
```
1. get_course_content_overview(course_id)
2. list_assignments(course_id)
3. For each assignment: check rubric exists, check points/due date set
4. scan_course_content_accessibility(course_id)
5. Output: structural map + QA checklist + accessibility report
```

### Workflow 2: Workload Pacing
```
1. list_assignments(course_id, include_all=True)
2. Group by week (based on due_at dates)
3. Calculate: points per week, assignments per week, submission types
4. Output: weekly workload table + flag overloaded/empty weeks
```

### Workflow 3: Peer Review Effectiveness
```
1. get_peer_review_completion_analytics(course_id, assignment_id)
2. analyze_peer_review_quality(course_id, assignment_id)
3. identify_problematic_peer_reviews(course_id, assignment_id)
4. Output: completion rates + quality metrics + flagged reviews
```

### Workflow 4: Bulk Publishing
```
1. list_modules(course_id) — show unpublished content
2. User selects modules/pages to publish
3. bulk_update_pages() + update_module() for batch publish
4. create_announcement() to notify students
```

---

## High-Impact Quick Wins (no new MCP tools needed)

These are pure orchestration — the skill just chains existing tools:

1. **Course QA checklist** — "all assignments have rubrics, all modules have items, all pages accessible"
2. **Workload pacing** — `list_assignments` + date grouping math
3. **Course structure map** — `get_course_content_overview` + formatted output

---

## Workshop Tie-in

The workshop for learning designers could demo:
- Live course audit using existing MCP tools
- Accessibility scan workflow
- Peer review quality analysis
- Show the gap: what a `/learning-design` skill would automate

Workshop feedback could validate which workflows matter most before building the skill.

---

## References
- [EDUCAUSE 2025: Learning & Instructional Design](https://community.canvaslms.com/t5/Canvas-LMS-Blog/EDUCAUSE-2025-Insights-Learning-amp-Instructional-Design/ba-p/660645)
- [Canvas Course Evaluation Checklist v3.0](https://shriistee.medium.com/improving-learner-experience-on-canvas-with-the-canvas-course-evaluation-checklist-v3-0-23d776aeac50)
- [Canvas Course Accessibility Checklist](https://community.canvaslms.com/t5/Canvas-LMS-Blog/Canvas-Course-Accessibility-Checklist/ba-p/650334)
- [awesome-mcp-personas](https://github.com/toolprint/awesome-mcp-personas)
- [Skills vs Dynamic MCP Loadouts — Armin Ronacher](https://lucumr.pocoo.org/2025/12/13/skills-vs-mcp/)
- [MCP, Skills, and Agents — David Cramer](https://cra.mr/mcp-skills-and-agents/)

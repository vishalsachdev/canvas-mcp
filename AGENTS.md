# Canvas MCP - AI Agent Guide

This guide helps AI agents (Claude, Cursor, Zed, Windsurf, and other MCP clients) effectively use the Canvas MCP server.

## Quick Start

Canvas MCP is a Model Context Protocol server that bridges AI assistants with Canvas Learning Management System. It provides tools for students to track their academic work and for educators to manage courses, grade assignments, and communicate with students.

**Key capability:** The server supports both traditional MCP tool calls AND a code execution API for bulk operations with 99.7% token savings.

## Authentication

All tools require valid Canvas credentials — either an API token or a session cookie.

> **Note:** The public hosted server (`mcp.illinihunt.org`) has been **retired** — a public MCP endpoint without an access gate would expose the code-execution tool. Use local (self-hosted) mode below. The HTTP/streamable transport remains supported for self-hosting behind your own authentication; an authenticated institutional deployment is tracked in [#115](https://github.com/vishalsachdev/canvas-mcp/issues/115).

### Local (Self-Hosted) — API Token (Recommended)
Configure credentials in the MCP server's `.env` file:
```
CANVAS_API_TOKEN=your_token_here
CANVAS_API_URL=https://your-institution.instructure.com/api/v1
```

Students and educators use the same server but have access to different tools based on Canvas API permissions.

### Local (Self-Hosted) — Session Cookie (Alternative)
If you cannot generate a Canvas API token (e.g. your institution restricts token creation), you can authenticate using the `canvas_session` cookie from an active browser session instead:

```
CANVAS_SESSION_COOKIE=<value of the canvas_session cookie>
CANVAS_API_URL=https://your-institution.instructure.com/api/v1
```

To get the cookie value: open Canvas in your browser → DevTools → Application → Cookies → copy the value of `canvas_session` (everything after `canvas_session=`).

> **Limitations:** Session cookies expire when your browser session ends (typically hours, not days). The session cookie auth path is not officially documented by Instructure and may stop working without notice. **API tokens are strongly preferred.** Do not set `CANVAS_SESSION_COOKIE` and `CANVAS_API_TOKEN` at the same time — the API token takes precedence.

### HTTP Transport (Multi-User / Hosted)
In HTTP mode each client supplies its own credentials per-request via headers. Set only `CANVAS_API_URL` on the server; do **not** set `CANVAS_API_TOKEN` or `CANVAS_SESSION_COOKIE` in the server's `.env`.

| Header | Value |
|--------|-------|
| `X-Canvas-Token` | Canvas API token (preferred) |
| `X-Canvas-Session-Cookie` | `canvas_session` cookie value (fallback) |
| `X-MCP-Access-Key` | Gate key if `MCP_ACCESS_KEYS` is configured |

When both `X-Canvas-Token` and `X-Canvas-Session-Cookie` are present, the API token takes precedence. A request with neither header is rejected with HTTP 401.

**Troubleshooting:**

| Error | Cause | Fix |
|-------|-------|-----|
| `401 Missing credentials` | No token or cookie header sent | Add `X-Canvas-Token` or `X-Canvas-Session-Cookie` |
| `401 Missing X-MCP-Access-Key` | Key gate active, no key provided | Add `X-MCP-Access-Key` header |
| `401 Unauthorized` (Canvas) | Invalid/expired credentials | Regenerate token or refresh browser session |

### Tool Profile (Optional)
Reduce tool overhead by setting a role-based profile. Only tools relevant to the selected role are registered:

```
# In .env:
CANVAS_ROLE=student    # ~32 tools (student + shared)
CANVAS_ROLE=educator   # ~87 tools (educator + shared)
CANVAS_ROLE=all        # All 90 tools (default)
```

Or via CLI flag: `canvas-mcp-server --role student` (CLI flag takes precedence over env var).

## Tool Categories

### Student Tools
Personal academic tracking using Canvas "self" endpoints. Students only see their own data.

| Tool | Purpose |
|------|---------|
| `get_my_upcoming_assignments` | Assignments due in next N days |
| `get_my_todo_items` | Canvas TODO list |
| `get_my_submission_status` | What's submitted vs missing |
| `get_my_course_grades` | Current grades across courses |
| `get_my_peer_reviews_todo` | Pending peer reviews to complete |

### Educator Tools
Course management, grading, and analytics. Requires instructor/TA role.

| Tool | Purpose |
|------|---------|
| `list_assignments` | All assignments in a course |
| `get_assignment_details` | Full assignment info including description |
| `list_submissions` | Student submissions for grading |
| `get_assignment_analytics` | Performance statistics |
| `create_assignment` | Create new assignment with due date, submission types, peer reviews |
| `update_assignment` | Update existing assignment (name, due date, points, published, etc.) |
| `get_student_analytics` | Individual student performance |
| `check_enrollment` | Is a given NetID enrolled in a course? Returns yes/no only, never the roster |
| `list_rubrics` | List rubrics in a course |
| `get_rubric` | View rubric details (by rubric_id or assignment_id) |
| `get_rubric_assessment` | View rubric assessment for a student submission |
| `create_rubric` | Create rubric with criteria, ratings, and optional assignment association |
| `associate_rubric` | Associate existing rubric with an assignment |
| `grade_with_rubric` | Grade single submission with rubric |
| `bulk_grade_submissions` | Grade multiple submissions efficiently |
| `send_conversation` | Message students |
| `send_peer_review_reminders` | Automated reminder workflow |
| `create_announcement` | Post course announcements |

### Shared Tools (Students & Educators)
Content access tools available to all authenticated users.

| Tool | Purpose |
|------|---------|
| `list_courses` | Enrolled courses |
| `get_course_details` | Course info and syllabus |
| `list_pages` | Course pages |
| `get_page_content` | Read page content |
| `update_page_settings` | Publish/unpublish, set front page, editing roles |
| `bulk_update_pages` | Update multiple pages at once |
| `list_modules` | List course modules |
| `create_module` | Create a new module |
| `update_module` | Update module settings |
| `delete_module` | Delete a module |
| `add_module_item` | Add content to a module |
| `update_module_item` | Update module item settings |
| `delete_module_item` | Remove item from module |
| `list_announcements` | Course announcements |
| `list_discussion_topics` | Discussion forums |
| `list_discussion_entries` | Posts in a discussion |
| `post_discussion_entry` | Add a discussion post |
| `reply_to_discussion_entry` | Reply to a post |

### Learning Designer Tools
Course design, quality assurance, and accessibility compliance.

| Tool | Purpose |
|------|---------|
| `get_course_structure` | Full module→items tree as JSON (one call) |
| `scan_course_content_accessibility` | Scan for WCAG violations |
| `fetch_ufixit_report` | Retrieve UFIXIT accessibility report |
| `parse_ufixit_violations` | Extract structured violations from report |
| `format_accessibility_summary` | Format violations into readable report |

### Developer Tools
Advanced tools for bulk operations and custom logic.

| Tool | Purpose |
|------|---------|
| `search_canvas_tools` | Discover available code API operations |
| `list_code_api_modules` | List TypeScript modules |
| `execute_typescript` | Run TypeScript for bulk operations |

## When to Use What

| Scenario | Recommended Approach | Why |
|----------|---------------------|-----|
| Single query ("Show my grades") | Traditional MCP tools | Simple, direct |
| List request ("Show assignments") | Traditional MCP tools | Low token cost |
| Grade 1-9 submissions | `grade_with_rubric` | Straightforward |
| Grade 10+ submissions | `bulk_grade_submissions` | Concurrent processing |
| Grade 30+ with custom logic | `execute_typescript` | 99.7% token savings |
| Complex data processing | `execute_typescript` | Data stays local |

### Token Efficiency Decision Tree

```
Is it a simple query?
├── Yes → Use traditional MCP tools
└── No → Is it bulk grading with known grades?
    ├── Yes → Use bulk_grade_submissions
    └── No → Does it need custom analysis logic?
        ├── Yes → Use execute_typescript
        └── No → Use traditional MCP tools
```

## Common Workflows

### Student: Weekly Planning
```
1. "What assignments do I have due this week?"
   → get_my_upcoming_assignments(days=7)

2. "Have I submitted everything?"
   → get_my_submission_status()

3. "What peer reviews do I need to do?"
   → get_my_peer_reviews_todo()
```

### Educator: Check Assignment Progress
```
1. "Show me Assignment 3 submissions"
   → list_submissions(course_id, assignment_id)

2. "Who hasn't submitted?"
   → get_assignment_analytics(course_id, assignment_id)

3. "Send reminders to missing students"
   → send_conversation(course_id, recipients, subject, body)
```

### Educator: Bulk Grading
```
1. "What's the rubric for Assignment 5?"
   → get_rubric(course_id, rubric_id=...)

2. "Grade these 50 submissions using the rubric"
   → bulk_grade_submissions(course_id, assignment_id, grades)

   OR for complex grading logic:
   → execute_typescript with bulkGrade function
```

### Educator: Discussion Participation
```
1. "Show discussion posts for Topic 3"
   → list_discussion_entries(course_id, topic_id)

2. "Who hasn't participated?"
   → Analyze entries to find missing students

3. "Post a reminder"
   → create_announcement(course_id, title, message)
```

## Capability Boundaries

### Can Do
- Read courses, assignments, grades, discussions, pages
- Submit grades with or without rubrics
- Send Canvas messages and announcements
- Create rubrics programmatically with defined criteria and ratings
- Use existing rubrics for grading (edit rubrics via Canvas UI if needed)
- Analyze peer review completion
- Execute TypeScript for bulk operations
- Access student data (with FERPA-compliant anonymization option)

### Cannot Do
- Create or delete courses
- Modify course settings or structure
- Access data outside user's Canvas permissions
- Bypass Canvas API rate limits
- Access other students' data (for student users)
- Modify Canvas system configuration

### Known Canvas API Limitations
Some Canvas API endpoints have bugs or limitations that prevent certain operations:

| Tool | Issue | Workaround |
|------|-------|------------|
| `update_rubric` | Partial updates wipe all criteria (full replacement, not PATCH) | Edit rubrics via Canvas web UI |

**Working rubric tools:** `create_rubric`, `list_rubrics`, `get_rubric`, `get_rubric_assessment`, `associate_rubric`, `grade_with_rubric`, `bulk_grade_submissions`

**Rubric workflow:** Use `create_rubric` to create rubrics programmatically. Edit rubrics via Canvas UI when needed, then use `associate_rubric` to link them to assignments.

### Data Access Rules
| User Type | Can Access |
|-----------|-----------|
| Student | Own submissions, grades, enrollments only |
| TA | Students in assigned sections |
| Instructor | All students in their courses |

## Rate Limits and Constraints

### Canvas API Limits
- **Rate limit:** ~700 requests/10 minutes (varies by institution)
- **Pagination:** Most list endpoints return 10-100 items per page
- **File size:** Attachments limited by Canvas instance settings

### Recommendations
- Use `bulk_grade_submissions` with `max_concurrent: 5` for grading
- Add `rate_limit_delay: 1000` (1 second) between batches
- Use `execute_typescript` for operations on 30+ items
- Always use `dry_run: true` first for bulk operations

## Error Handling

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| 401 Unauthorized | Invalid/expired token | Generate new Canvas API token |
| 403 Forbidden | Insufficient permissions | Check Canvas role permissions |
| 404 Not Found | Invalid course/assignment ID | Verify IDs exist |
| 422 Unprocessable | Invalid parameters | Check parameter format |
| 429 Too Many Requests | Rate limit exceeded | Reduce request frequency |

### Recovery Strategies
1. **Auth errors (401/403):** Stop and report - cannot recover without user action
2. **Not found (404):** Verify resource exists, check for typos in identifiers
3. **Rate limits (429):** Wait and retry with exponential backoff
4. **Validation (422):** Check parameter types and required fields

## Tool Discovery

### Runtime Discovery
Use the `search_canvas_tools` MCP tool to find available code API operations:

```
search_canvas_tools("grading", "signatures")  → Find grading tools
search_canvas_tools("", "names")              → List all tools
search_canvas_tools("bulk", "full")           → Full details on bulk ops
```

### Static Discovery
See `/tools/TOOL_MANIFEST.json` for machine-readable tool catalog.
See `/tools/README.md` for comprehensive human-readable documentation.

## Course Identifier Formats

Canvas MCP accepts multiple identifier formats:

| Format | Example | Notes |
|--------|---------|-------|
| Canvas ID | `12345` | Numeric course ID |
| Course code | `badm_350_120251_246794` | SIS course code |
| SIS ID | `sis_course_id:ABC123` | If configured |

The server automatically resolves identifiers to Canvas IDs.

## Privacy and Anonymization

### For Educators
Enable FERPA-compliant anonymization:
```
ENABLE_DATA_ANONYMIZATION=true
```

This converts student names to anonymous IDs (e.g., `Student_a8f7e23d`) before data reaches the AI. A local mapping file allows educators to correlate IDs with real students.

### For Students
No anonymization needed - students only access their own data via Canvas "self" endpoints.

## Additional Resources

- **Tool Documentation:** `/tools/README.md`
- **Code API Guide:** `/src/canvas_mcp/code_api/README.md`
- **Student Guide:** https://canvas-mcp.illinihunt.org/student-guide.html
- **Educator Guide:** https://canvas-mcp.illinihunt.org/educator-guide.html
- **Development Guide:** `/CLAUDE.md`

## Claude Memory Lookup

When prior context may matter, search Claude memories at runtime instead of copying memory content into this repo. Use this as a nudge, not a mandatory step for every tiny edit.

- Safe local roots: /Users/vishal/code, /Users/vishal/teaching, /Users/vishal/research, /Users/vishal/admin, /Users/vishal/vault.
- Do not search Box, iCloud, or other cloud-sync folders for this purpose.
- Start with global memory: /Users/vishal/.claude/memory/MEMORY.md and /Users/vishal/.claude/projects/-Users-vishal/memory/MEMORY.md.
- For the current project, derive the likely Claude memory folder from the path. Example: /Users/vishal/code/AgentLab -> /Users/vishal/.claude/projects/-Users-vishal-code-AgentLab/memory/.
- If the topic could cross projects, search relevant memory files with rg across /Users/vishal/.claude/projects/*/memory/*.md.
- Prefer memory pointers and summaries over duplicating long memory content here.

## External Actions Require Explicit Approval

Never publish, post, send, delete, deploy, submit, schedule, purchase, or otherwise take an external action without explicit approval from Vishal.

This includes LinkedIn, email, Slack/Teams, Canvas, GitHub PRs/issues/comments, deployments, forms, purchases, and browser-based actions that affect external systems.

Drafting is allowed. Composing into a browser editor is allowed only when asked. Stop before the final action button.

Before any external action, ask: "Do you want me to [exact action] now?" Only proceed after a clear yes to that exact action. Do not treat "looks good," "ok," or "use this" as permission to publish, send, delete, deploy, submit, schedule, purchase, or post.

For LinkedIn posts: prepare the text, optionally paste it into the composer, then stop. Never click Post unless Vishal explicitly says "Post it."

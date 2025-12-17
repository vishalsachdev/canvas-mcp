# Canvas MCP - AI Agent Guide

This guide helps AI agents (Claude, Cursor, Zed, Windsurf, and other MCP clients) effectively use the Canvas MCP server.

## Quick Start

Canvas MCP is a Model Context Protocol server that bridges AI assistants with Canvas Learning Management System. It provides tools for students to track their academic work and for educators to manage courses, grade assignments, and communicate with students.

**Key capability:** The server supports both traditional MCP tool calls AND a code execution API for bulk operations with 99.7% token savings.

## Authentication Required

All tools require a valid Canvas API token. The token must be configured in the MCP server's environment:

```
CANVAS_API_TOKEN=your_token_here
CANVAS_API_URL=https://your-institution.instructure.com
```

Students and educators use the same server but have access to different tools based on Canvas API permissions.

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
| `get_student_analytics` | Individual student performance |
| `create_rubric` | Create grading rubrics |
| `grade_submission_with_rubric` | Grade single submission |
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
| `list_announcements` | Course announcements |
| `list_discussion_topics` | Discussion forums |
| `list_discussion_entries` | Posts in a discussion |
| `post_discussion_entry` | Add a discussion post |
| `reply_to_discussion_entry` | Reply to a post |

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
| Grade 1-9 submissions | `grade_submission_with_rubric` | Straightforward |
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
   → get_rubric_details(course_id, rubric_id)

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
- Create and manage rubrics
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
- **Student Guide:** `/docs/STUDENT_GUIDE.md`
- **Educator Guide:** `/docs/EDUCATOR_GUIDE.md`
- **Development Guide:** `/docs/CLAUDE.md`

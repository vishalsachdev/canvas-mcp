---
name: canvas-morning-check
description: Educator morning course health check for Canvas LMS. Shows submission rates, struggling students, grade distribution, and upcoming deadlines. Trigger phrases include "morning check", "course status", "how are my students", or any start-of-day teaching review.
---

# Canvas Morning Check

A comprehensive course health check for educators using Canvas LMS. Run it at the start of a teaching day or week to surface submission gaps, students who need support, and upcoming deadlines -- then take action directly from the results.

## Prerequisites

- **Canvas MCP server** must be running and connected to the agent's MCP client.
- The authenticated user must have an **educator or instructor role** in the target Canvas course(s).
- **FERPA compliance**: Set `ENABLE_DATA_ANONYMIZATION=true` in the Canvas MCP server environment to anonymize student names in all output. When enabled, names render as `Student_xxxxxxxx` hashes.

## Steps

### 1. Identify Target Course(s)

Ask the user which course(s) to check. Accept a course code, Canvas ID, or "all" to iterate through every active course.

If the user does not specify, prompt:

> Which course would you like to check? (Or say "all" for all active courses.)

Use the `list_courses` MCP tool if you need to look up available courses.

### 2. Collect Recent Submission Data

For each target course:

1. Call `list_assignments` to find assignments with a due date in the **past 7 days**.
2. For each recent assignment, call `get_assignment_analytics` to collect:
   - Submission rate (submitted / enrolled)
   - Average, high, and low scores
   - Late submission count

### 3. Identify Struggling Students

Call `list_submissions` to retrieve student submission records, then flag students based on these thresholds:

| Urgency | Criteria |
|---------|----------|
| **Critical** | Missing 3+ assignments in the past 2 weeks, or average grade below 60% |
| **Needs attention** | Missing 2 assignments, or average grade 60--70%, or 3+ late submissions |
| **On track** | All submissions current, grade above 70% |

Use `get_student_analytics` for deeper per-student analysis when the user requests it.

### 4. Check Upcoming Deadlines

Call `list_assignments` filtered to the **next 7 days**. For each upcoming assignment, surface:

- Assignment name
- Due date and time
- Point value
- Current submission count (if submissions have started)

### 5. Generate the Status Report

Present results in a structured format:

```
## Course Status: [Course Name]

### Submission Overview
| Assignment | Due Date | Submitted | Rate | Avg Score |
|------------|----------|-----------|------|-----------|
| Quiz 3     | Feb 24   | 28/32     | 88%  | 85.2      |
| Essay 2    | Feb 26   | 25/32     | 78%  | --        |

### Students Needing Support
**Critical (3+ missing):**
- Student_a8f7e23 (missing: Quiz 3, Essay 2, HW 5)

**Needs Attention (2 missing):**
- Student_c9b21f8 (missing: Essay 2, HW 5)
- Student_d3e45f1 (missing: Quiz 3, Essay 2)

### Upcoming This Week
- **Mar 3:** Final Project (100 pts) - 5 submitted so far
- **Mar 5:** Discussion 8 (20 pts)

### Suggested Actions
1. Send reminder to 3 students with critical status
2. Review Essay 2 submissions (78% rate, below average)
3. Post announcement about Final Project deadline
```

### 6. Offer Follow-up Actions

After presenting the report, offer actionable next steps:

> Would you like me to:
> 1. Draft and send a message to struggling students (uses `send_conversation`)
> 2. Send reminders about upcoming deadlines (uses `send_peer_review_reminders` or `send_conversation`)
> 3. Get detailed analytics for a specific assignment (uses `get_assignment_analytics`)
> 4. Check another course

If the user selects option 1, use the `send_conversation` MCP tool to message the identified students directly through Canvas.

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `list_courses` | Discover active courses |
| `list_assignments` | Find recent and upcoming assignments |
| `get_assignment_analytics` | Submission rates and score statistics |
| `list_submissions` | Per-student submission records |
| `get_student_analytics` | Detailed per-student performance data |
| `send_conversation` | Message students through Canvas inbox |

## Example

**User:** "Morning check for CS 101"

**Agent:** Runs the workflow above, outputs the status report.

**User:** "Send a reminder to students missing Quiz 3"

**Agent:** Calls `send_conversation` to message the identified students with a reminder.

## Notes

- When anonymization is enabled, maintain a local mapping of anonymous IDs so follow-up actions (messaging, grading) still target the correct students.
- This skill works best as a weekly routine -- Monday mornings are ideal.
- Pairs well with the `canvas-week-plan` skill for student-facing planning.

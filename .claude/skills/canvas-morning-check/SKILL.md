---
name: canvas-morning-check
description: Educator morning course health check. Shows submission rates, struggling students, grade distribution, and upcoming deadlines. Use when educator says "morning check", "course status", "how are my students", or at the start of a teaching day.
---

# Canvas Morning Check

Get a comprehensive status report for your courses at the start of the day or week. Identifies students who need support and upcoming deadlines.

## Prerequisites

- Canvas MCP server must be running
- User must have educator/instructor role in Canvas
- For FERPA compliance, `ENABLE_DATA_ANONYMIZATION=true` should be set

## Steps

### 1. Identify Target Course(s)

Ask the user which course(s) to check, or check all active courses:

```
Which course would you like to check? (Or say "all" for all your courses)
```

If user specifies a course, use that course identifier. If "all", iterate through active courses.

### 2. Get Recent Assignment Submissions

For each target course, use `list_assignments` to find assignments due in the past 7 days, then use `get_assignment_analytics` for each:

**Data to collect:**
- Submission rate (submitted / enrolled)
- Average score
- High/low scores
- Late submission count

### 3. Identify Struggling Students

Use `list_submissions` to find students missing multiple assignments:

**Flag students who:**
- Are missing 2+ assignments in the past 2 weeks
- Have submitted late more than twice
- Have average grade below 70%

Group by urgency:
- **Critical:** Missing 3+ assignments or grade below 60%
- **Needs attention:** Missing 2 assignments or grade 60-70%
- **On track:** All submissions current, grade above 70%

### 4. Check Upcoming Deadlines

Use `list_assignments` filtered to next 7 days:

**Show:**
- Assignment name
- Due date/time
- Point value
- Current submission count (if submissions have started)

### 5. Generate Status Report

Output a structured report:

```
## Course Status: [Course Name]

### Submission Overview
| Assignment | Due Date | Submitted | Rate | Avg Score |
|------------|----------|-----------|------|-----------|
| Quiz 3     | Dec 20   | 28/32     | 88%  | 85.2      |
| Essay 2    | Dec 22   | 25/32     | 78%  | --        |

### Students Needing Support
**Critical (3+ missing):**
- Student_a8f7e23 (missing: Quiz 3, Essay 2, HW 5)

**Needs Attention (2 missing):**
- Student_c9b21f8 (missing: Essay 2, HW 5)
- Student_d3e45f1 (missing: Quiz 3, Essay 2)

### Upcoming This Week
- **Dec 26:** Final Project (100 pts) - 5 submitted so far
- **Dec 28:** Discussion 8 (20 pts)

### Suggested Actions
1. Send reminder to 3 students with critical status
2. Review Essay 2 submissions (78% rate, below average)
3. Post announcement about Final Project deadline
```

### 6. Offer Follow-up Actions

After presenting the report, offer:

```
Would you like me to:
1. Draft a message to struggling students
2. Send reminders about upcoming deadlines
3. Get detailed analytics for a specific assignment
4. Check another course
```

## Example Usage

**User:** "Morning check for CS 101"

**Claude:** [Runs the skill, outputs status report]

**User:** "Send a reminder to students missing Quiz 3"

**Claude:** [Uses `send_conversation` to message identified students]

## Notes

- With anonymization enabled, student names appear as `Student_xxxxxxxx`
- Keep local mapping file to correlate anonymous IDs with real students
- This skill works best when run weekly (Monday mornings)
- Pairs well with `/canvas-week-plan` for students

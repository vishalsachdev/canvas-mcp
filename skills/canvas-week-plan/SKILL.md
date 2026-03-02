---
name: canvas-week-plan
description: Student weekly assignment planner for Canvas LMS. Shows all due dates, submission status, grades, and peer reviews across all courses. Use when a student says "what's due", "plan my week", "weekly check", or wants to organize their coursework.
---

# Canvas Week Plan

Generate a comprehensive weekly plan for a student, showing all upcoming assignments, current grades, submission status, and pending peer reviews across all enrolled courses.

## Prerequisites

- **Canvas MCP server** must be configured and running in the agent's MCP client (e.g., Claude Code, Cursor, Codex, OpenCode)
- The user must have a **student role** in their Canvas courses
- No anonymization is needed -- students only see their own data

## Steps

### 1. Get Upcoming Assignments

Call the MCP tool `get_my_upcoming_assignments` with `days_ahead=7` to retrieve all assignments due in the next week.

**Data to collect per assignment:**
- Assignment name
- Course name or code
- Due date and time
- Point value
- Assignment type (quiz, essay, discussion, etc.)

### 2. Check Submission Status

Call the MCP tool `get_my_submission_status` to determine what has been submitted and what has not.

**Categorize each assignment as one of:**
- **Submitted** -- already turned in
- **Not submitted** -- still needs to be done
- **Late** -- past due but late submissions still accepted
- **Missing** -- past due, no late submissions accepted

### 3. Get Current Grades

Call the MCP tool `get_my_course_grades` to show academic standing for each enrolled course.

**Collect per course:**
- Current percentage and letter grade
- Impact of upcoming assignments on grade (if calculable)

### 4. Check Peer Reviews

Call the MCP tool `get_my_peer_reviews_todo` to find any pending peer reviews.

**Collect per pending review:**
- Which assignment needs peer review
- How many reviews are required
- Deadline for completing reviews
- Reviews completed vs. remaining

### 5. Generate the Weekly Plan

Present a structured, actionable plan using the format below. Adjust courses, assignments, and numbers to match the actual data retrieved.

```
## Your Week Ahead

### Quick Stats
- **Due this week:** 5 assignments
- **Already submitted:** 2
- **Peer reviews pending:** 3
- **Highest priority:** Final Project (100 pts, due Fri)

### By Course

#### CS 101 (Current: 87% B+)
| Assignment | Due | Points | Status |
|------------|-----|--------|--------|
| Quiz 5 | Tue 11:59pm | 20 | Not submitted |
| Lab 8 | Thu 5:00pm | 30 | Submitted |

#### MATH 221 (Current: 92% A-)
| Assignment | Due | Points | Status |
|------------|-----|--------|--------|
| HW 12 | Wed 11:59pm | 25 | Not submitted |
| Final Project | Fri 11:59pm | 100 | Not submitted |

### Peer Reviews Due
- **Essay 2 Peer Review** (ENG 101) - 2 reviews needed by Thu
- **Project Proposal Review** (CS 101) - 1 review needed by Fri

### Suggested Priority Order
1. **Quiz 5** (CS 101) - Due tomorrow, 20 pts
2. **HW 12** (MATH 221) - Due Wed, 25 pts
3. **Peer Reviews** - 3 total, due Thu-Fri
4. **Final Project** (MATH 221) - Due Fri, 100 pts (start early!)

### Grade Impact
- Completing all assignments could raise your grades:
  - CS 101: 87% -> 89%
  - MATH 221: 92% -> 94%
```

### 6. Offer Drill-Down Options

After presenting the plan, let the user know what further actions are available:

```
Need more details? I can:
1. Show full assignment instructions for any item
2. Check the rubric for an assignment
3. Show your grade breakdown for a course
4. Focus on just one course
```

## MCP Tools Used

| Tool | Purpose |
|------|---------|
| `get_my_upcoming_assignments` | Fetch assignments due within a time window |
| `get_my_submission_status` | Check submitted vs. not submitted |
| `get_my_course_grades` | Retrieve current grades per course |
| `get_my_peer_reviews_todo` | Find pending peer review tasks |
| `get_assignment_details` | Drill down into a specific assignment (rubric, instructions) |

## Output Variations

### Compact Mode

If the user asks for a "quick check" or "just the highlights", use a shorter format:

```
## This Week
- 3 assignments due (2 not started)
- 2 peer reviews pending
- Grades: CS 101 (87%), MATH 221 (92%), ENG 101 (85%)

**Priority:** Quiz 5 (tomorrow), HW 12 (Wed), Final Project (Fri)
```

### Single Course Mode

If the user specifies a course (e.g., "plan my week for CS 101"), show only that course's assignments, grades, and peer reviews.

## Notes

- Best used at the start of each week (Sunday or Monday)
- Assignments are sorted by due date, then by point value
- Late and missing assignments are highlighted for attention
- All student-facing tools use the `get_my_*` prefix
- No privacy concerns since students only access their own data

---
name: canvas-week-plan
description: Student weekly assignment planner. Shows all due dates, submission status, grades, and peer reviews across all courses. Use when student says "what's due", "plan my week", "weekly check", or wants to organize their coursework.
---

# Canvas Week Plan

Generate a comprehensive weekly plan for a student, showing all upcoming assignments, current grades, submission status, and pending peer reviews across all enrolled courses.

## Prerequisites

- Canvas MCP server must be running
- User has student role in Canvas courses
- No anonymization needed (students only see their own data)

## Steps

### 1. Get Upcoming Assignments

Use `get_my_upcoming_assignments` with `days_ahead=7` to get all assignments due in the next week:

**Data to collect:**
- Assignment name
- Course name/code
- Due date and time
- Point value
- Assignment type (quiz, essay, discussion, etc.)

### 2. Check Submission Status

Use `get_my_submission_status` to determine what's been submitted:

**Categorize each assignment:**
- **Submitted:** Already turned in
- **Not submitted:** Still needs to be done
- **Late:** Past due but can still submit
- **Missing:** Past due, no late submissions accepted

### 3. Get Current Grades

Use `get_my_course_grades` to show academic standing:

**For each course:**
- Current percentage/letter grade
- Trend (up/down from last week if trackable)
- Impact of upcoming assignments on grade

### 4. Check Peer Reviews

Use `get_my_peer_reviews_todo` to find pending reviews:

**Show:**
- Which assignments need peer review
- How many reviews required
- Deadline for reviews
- Reviews completed vs. remaining

### 5. Generate Weekly Plan

Output a structured, actionable plan:

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
  - CS 101: 87% → 89%
  - MATH 221: 92% → 94%
```

### 6. Offer Drill-Down Options

After presenting the plan:

```
Need more details? I can:
1. Show full assignment instructions for any item
2. Check the rubric for an assignment
3. Show your grade breakdown for a course
4. Focus on just one course
```

## Example Usage

**User:** "What's due this week?"

**Claude:** [Runs the skill, outputs weekly plan]

**User:** "Show me the rubric for the Final Project"

**Claude:** [Uses `get_assignment_details` to fetch rubric]

## Output Variations

### Compact Mode
If user says "quick check" or "just the highlights":

```
## This Week
- 3 assignments due (2 not started)
- 2 peer reviews pending
- Grades: CS 101 (87%), MATH 221 (92%), ENG 101 (85%)

**Priority:** Quiz 5 (tomorrow), HW 12 (Wed), Final Project (Fri)
```

### Single Course Mode
If user specifies a course:

```
/canvas-week-plan CS 101
```

Show only that course's assignments, grades, and details.

## Notes

- Best used at the start of each week (Sunday/Monday)
- Assignments are sorted by due date, then by point value
- Late/missing assignments are highlighted for attention
- Works with the student tools: `get_my_*` prefix functions
- No privacy concerns since students only access their own data

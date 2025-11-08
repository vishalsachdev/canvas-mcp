# Student Workflow Examples

This guide demonstrates common student workflows using Canvas MCP with Claude Desktop.

## Daily Check-In Workflow

**Goal**: Start your day by checking what's due and what you need to complete.

### Step 1: Morning Overview

```
You: "Good morning! What do I need to focus on today?"

Claude will:
1. Check upcoming assignments (next 24-48 hours)
2. Show incomplete peer reviews
3. List recent announcements
4. Highlight TODO items
```

**Expected Response:**
```
📚 Your Daily Overview (Nov 8, 2025)

Upcoming Assignments (Next 48 Hours):
- [BADM 350] Problem Set 3 - Due Tomorrow at 11:59 PM
- [CSCI 101] Lab Assignment 5 - Due Tomorrow at 5:00 PM

Peer Reviews Needed:
- [ENGL 102] Essay 2 Peer Review - 2 reviews required (Due Nov 10)

Recent Announcements:
- [BADM 350] Office hours moved to Thursday 2-4 PM
- [HIST 201] Midterm study guide posted

TODO Items: 3 items requiring attention
```

### Step 2: Get Assignment Details

```
You: "Tell me more about the BADM 350 Problem Set 3"

Claude will:
- Fetch assignment details
- Show submission requirements
- Display rubric (if available)
- Check if you've submitted
```

### Step 3: Check Submission Status

```
You: "Have I submitted everything due this week?"

Claude will:
- List all assignments due this week
- Mark submitted vs not submitted
- Flag overdue items
- Show submission timestamps
```

## Weekly Planning Workflow

**Goal**: Plan your week and prioritize work.

### Sunday Evening Planning

```
You: "Help me plan my week. What's coming up in the next 7 days?"

Claude provides:
1. All assignments due in the next week (by date)
2. Peer reviews needed
3. Quiz/exam schedule
4. Discussion posts required
```

**Example Response:**
```
📅 Week Ahead (Nov 8-14, 2025)

Monday, Nov 8:
- No assignments due

Tuesday, Nov 9:
- [BADM 350] Problem Set 3 (11:59 PM)
- [CSCI 101] Lab 5 (5:00 PM)

Wednesday, Nov 10:
- [ENGL 102] Peer Reviews (2 required) (11:59 PM)

Thursday, Nov 11:
- [HIST 201] Discussion Post (11:59 PM)

Friday, Nov 12:
- [BADM 350] Quiz 4 (Available all day)

Weekend:
- [CSCI 101] Project Milestone 2 (Sunday 11:59 PM)

Workload Summary:
- 3 assignments
- 2 peer reviews
- 1 discussion post
- 1 quiz
```

### Prioritization

```
You: "Which of these should I prioritize?"

Claude analyzes:
- Due dates (soonest first)
- Point values
- Your current grades
- Submission status
```

## Assignment Submission Workflow

**Goal**: Ensure you've met all requirements before submitting.

### Pre-Submission Checklist

```
You: "I'm about to submit my ENGL 102 essay. What do I need to check?"

Claude will:
1. Show assignment requirements
2. Display rubric criteria
3. Check file type requirements
4. Remind you about peer review deadlines
5. Confirm submission method
```

### Post-Submission Verification

```
You: "Did my submission for ENGL 102 Essay 2 go through?"

Claude confirms:
- Submission timestamp
- Files submitted
- Submission status (submitted, late, on-time)
- Grade (if posted)
```

## Peer Review Workflow

**Goal**: Complete all peer reviews efficiently and thoughtfully.

### Step 1: See What's Needed

```
You: "What peer reviews do I need to complete?"

Response:
- Assignment name
- Number of reviews required
- Number completed
- Deadline
- Classmates assigned to you
```

### Step 2: Track Progress

```
You: "Have I completed all my peer reviews for ENGL 102?"

Claude checks:
- Required number of reviews
- Completed reviews
- Remaining reviews needed
- Time remaining until deadline
```

## Grade Monitoring Workflow

**Goal**: Stay informed about your academic performance.

### Current Grade Check

```
You: "What are my current grades in all my courses?"

Response shows:
- Course name
- Current grade (letter and percentage)
- Grade updated timestamp
- Enrollment status
```

### Course-Specific Deep Dive

```
You: "How am I doing in BADM 350?"

Claude provides:
- Current grade
- Recent assignment grades
- Missing work (if any)
- Grade trend (improving/declining)
- Upcoming assignments that affect grade
```

## Discussion Participation Workflow

**Goal**: Stay engaged with course discussions.

### View Active Discussions

```
You: "What are the active discussions in HIST 201?"

Claude lists:
- Discussion title
- Due date
- Number of posts required
- Your participation status
```

### Check Your Posts

```
You: "Show me what I posted in the Week 5 discussion"

Claude retrieves:
- Your initial post
- Replies you've made
- Responses to your posts
- Participation grade (if posted)
```

## Exam Preparation Workflow

**Goal**: Prepare effectively for upcoming exams.

### Exam Overview

```
You: "I have a BADM 350 midterm next week. Help me prepare."

Claude can:
1. Check for posted study guides
2. Review recent announcements about the exam
3. List topics covered (from syllabus)
4. Show your performance on related assignments
```

### Study Plan

```
You: "Create a study plan for my BADM 350 midterm"

Claude suggests:
- Daily study topics (based on syllabus)
- Practice problems from past assignments
- Discussion topics to review
- Resources from course pages
```

## Time Management Workflow

**Goal**: Manage your workload effectively.

### Workload Analysis

```
You: "How heavy is my workload this week?"

Claude analyzes:
- Number of assignments due
- Estimated time per assignment
- Concentration of due dates
- Recommendations for time allocation
```

### Deadline Clustering

```
You: "Do I have multiple things due on the same day?"

Claude identifies:
- Days with multiple deadlines
- Suggestions to work ahead
- Priority order
```

## Course Content Navigation

**Goal**: Quickly find course materials.

### Find Syllabus

```
You: "Show me the syllabus for BADM 350"

Claude locates:
- Syllabus page content
- Course policies
- Grading breakdown
- Office hours
- Contact information
```

### Access Recent Announcements

```
You: "What are the recent announcements in all my courses?"

Claude compiles:
- All announcements from past 7 days
- Grouped by course
- Sorted by date
```

## Troubleshooting Workflow

**Goal**: Resolve common issues.

### Missing Assignment

```
You: "I don't see Assignment 3 in my CSCI 101 assignments list"

Claude checks:
- Assignment visibility
- Due dates
- Your enrollment status
- Suggests checking with instructor if truly missing
```

### Submission Issues

```
You: "I submitted my assignment but it shows as missing"

Claude verifies:
- Submission status in Canvas
- Submission timestamp
- Files attached
- Suggests next steps (contact instructor, resubmit)
```

## Tips for Best Results

1. **Be Specific**: Mention course codes (e.g., "BADM 350" instead of "my business class")

2. **Use Follow-ups**: Claude remembers context within a conversation
   ```
   You: "Show me my assignments"
   Claude: [shows assignments]
   You: "Which of these are due this week?" # Claude knows "these" = assignments
   ```

3. **Combine Requests**: Ask for multiple things at once
   ```
   "Show me my grades and what's due this week in BADM 350"
   ```

4. **Check Regularly**: Use daily for best results
   - Morning: Check what's due
   - Evening: Verify submissions
   - Sunday: Plan the week

5. **Save Important Conversations**: Keep conversations with important deadlines or instructions

## Example Daily Routine

**Morning (8:00 AM)**
```
You: "What's on my plate today?"
```

**Before Class**
```
You: "What do I need for my 2 PM BADM 350 class?"
```

**After Class**
```
You: "What homework do I have from today's classes?"
```

**Evening (9:00 PM)**
```
You: "Did I submit everything I needed to today?"
```

**Before Bed**
```
You: "What should I prepare for tomorrow?"
```

This workflow-based approach helps you stay organized, reduce stress, and never miss a deadline!

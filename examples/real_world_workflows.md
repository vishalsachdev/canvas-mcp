# Real-World Workflows

Practical examples showing how to combine Canvas MCP features for common teaching and learning scenarios.

## For Students

### Weekly Assignment Planning

**Goal**: Plan your week based on what's due.

```
Show me everything due in the next 7 days across all my courses.
For each assignment, tell me:
1. What course it's for
2. When it's due
3. Whether I've submitted it
4. How many points it's worth
```

**Follow-up**:
```
Of those assignments, which ones are worth more than 50 points?
I should prioritize those.
```

### Pre-Exam Check

**Goal**: Make sure you haven't missed anything before exam week.

```
For MATH 221, show me:
1. All assignments from the past 4 weeks
2. Which ones I haven't submitted
3. My current grade
4. Any peer reviews I need to complete
```

**Then**:
```
What's the impact on my grade if I submit the missing assignments?
```

### Managing Multiple Courses

**Goal**: Get organized across all your classes.

```
Create a summary for me:
- List all my courses
- For each course, show my current grade
- Highlight any missing assignments
- Show upcoming deadlines in the next 2 weeks
```

## For Educators

### Monday Morning Course Check

**Goal**: Start the week knowing where your students stand.

```
For CS 101, give me a status report:
1. Submission rate for last week's assignment
2. Average score
3. Students who are falling behind (missing 2+ assignments)
4. Upcoming deadlines this week
```

**Follow-up action**:
```
Draft a supportive message to students who are missing multiple
assignments. Mention that office hours are available and we're
here to help them succeed.
```

### Discussion-Based Course Management

**Goal**: Track and encourage participation.

**Week 1**:
```
For COMM 250, show me who has posted to Discussion 1.
The due date is Friday.
```

**Week 2**:
```
For Discussion 1, show me:
1. Who made initial posts
2. Who completed peer reviews
3. Who hasn't participated at all

Then draft a reminder message for students who haven't participated.
```

**End of week**:
```
Grade Discussion 1 in COMM 250:
- 10 points for initial post
- 5 points per peer review (must do 2)
- Maximum 10 points for peer reviews
```

### Grading Workflow for Programming Assignments

**Goal**: Efficiently grade code submissions.

```
For Assignment 3 in CS 225 (Jupyter notebooks):

Use the bulk grading code API to:
1. Download all submissions
2. Check if each notebook runs without errors
3. Check if they implemented the required functions
4. Give full points (100) if error-free, 0 if errors
5. Add a comment with specific feedback
```

**Then review**:
```
Show me the grading summary. How many students got full points?
Who had errors?
```

**Follow-up with struggling students**:
```
For students who got 0 points on Assignment 3, draft an
encouraging message offering help in office hours.
```

### Midterm Grade Check-in

**Goal**: Identify students who need support.

```
For ECON 102, analyze student performance:
1. List students with grade below 70%
2. Show which assignments they're missing
3. Compare their discussion participation to class average
```

**Intervention**:
```
Draft personalized messages for students below 70%, mentioning:
- Their specific missing assignments
- Offer to meet during office hours
- Resources available (tutoring, study groups)
- Encouraging tone - it's not too late to improve
```

### End-of-Semester Workflow

**Goal**: Wrap up the semester efficiently.

```
For BADM 350, create an end-of-semester report:
1. Final grade distribution
2. Students with missing assignments
3. Overall assignment completion rate
4. Discussion participation statistics
```

**Grade finalization**:
```
Show me students who are on the border between grades
(within 2% of the next letter grade). I want to review their
work to see if any borderline cases deserve rounding up.
```

## Advanced Workflows

### Peer Review Campaign

**Goal**: Maximize peer review completion.

**Week 1 (assignment posted)**:
```
Create a peer review assignment for Essay 1 in ENG 101.
Each student should review 2 peers.
```

**Week 2 (reminder)**:
```
Who hasn't started their peer reviews for Essay 1?
Send them a reminder that reviews are due in 3 days.
```

**Week 3 (follow-up)**:
```
Analyze peer review completion:
- Who completed all reviews?
- Who completed some but not all?
- Who hasn't started?

Send targeted reminders to the last two groups.
```

**Week 4 (grading)**:
```
Grade peer reviews for Essay 1:
- 20 points for completing 2 quality reviews
- 10 points for completing 1 review
- 0 points for no reviews
```

### Flipped Classroom Management

**Goal**: Track pre-class preparation.

**Before class**:
```
For Week 5 pre-reading in HIST 101:
1. Who completed the reading quiz?
2. Who participated in the pre-class discussion?
3. What questions did students ask?
```

**Adjust lesson plan**:
```
Based on the pre-class discussion, what topics are students
most confused about? I'll focus on those in class.
```

**After class**:
```
Send the class a summary of today's key points and link to
additional resources for topics they struggled with.
```

### Data-Driven Course Improvement

**Goal**: Use analytics to improve teaching.

**Mid-semester**:
```
For MATH 121, compare this semester to last:
1. Average grades on comparable assignments
2. Submission rates
3. Discussion participation

What's different this semester?
```

**Assignment analysis**:
```
For Assignment 5 in MATH 121:
1. What was the average score?
2. Which questions did students struggle with most?
3. Compare to last semester's Assignment 5
```

**Adjust course**:
```
Based on the analysis, students are struggling with
derivatives. Draft an announcement about extra practice
problems and optional review session.
```

## Efficiency Tips

### Batch Operations

Instead of processing students one-by-one, use bulk operations:

❌ **Inefficient**:
```
Show me Student 1's grade... now Student 2... now Student 3...
```

✅ **Efficient**:
```
Show me all students' grades for Assignment 5
```

✅ **Most Efficient** (for large classes):
```
Use the bulk grading code API to analyze all submissions
```

### Templated Messages

Create templates for common messages:

```
Create a template for my late assignment reminder message.
Include:
- Student's name
- Specific assignment they're missing
- New deadline (3 days from now)
- Offer to help
- Encouraging tone
```

Then use it:
```
Send the late assignment template to all students missing
Assignment 4, with the deadline set to Friday.
```

### Combine Related Tasks

Process related tasks in one go:

```
For CS 225 Assignment 3:
1. Grade all submissions using the rubric
2. Identify students who scored below 70%
3. Draft personalized feedback for struggling students
4. Create a class announcement about common mistakes
```

## Troubleshooting Workflows

### When Grades Don't Seem Right

```
For Assignment 6 in ECON 102:
1. Show me the grade distribution
2. List any students with 0 points
3. Check if those students actually submitted something
4. Show me submission timestamps
```

### When Students Report Issues

```
Student says they submitted Assignment 2 but it shows as missing.
Check:
1. All submissions for this student in this course
2. Submission timestamps
3. Assignment status

Then explain what I find.
```

## Time-Saving Patterns

Learn these patterns to save time:

**Morning routine** (2 minutes):
```
Quick status for all my courses: submission rates for current
assignments, any concerning patterns, what needs my attention today.
```

**Grading day** (using bulk operations):
```
Bulk grade Assignment X in Course Y using [specific criteria].
Show me the results summary, then I'll review borderline cases.
```

**Student support** (targeted help):
```
Identify students who need support in Course Z (missing assignments,
low grades, low participation). Draft messages offering help.
```

## Creating Your Own Workflows

**Start with your goal**:
- What do you want to accomplish?
- Who is affected (all students, specific group)?
- What's the deadline or timeline?

**Break it into steps**:
- What information do you need first?
- What decisions need to be made?
- What actions will you take?

**Automate what you can**:
- Use bulk operations for large classes
- Create message templates for common communications
- Set up regular check-ins (weekly status checks)

**Iterate and improve**:
- If a workflow is clunky, simplify it
- Ask Claude to suggest improvements
- Share successful workflows with colleagues

Need more ideas? Check out the [Educator Guide](../docs/EDUCATOR_GUIDE.md) or [open a discussion](https://github.com/vishalsachdev/canvas-mcp/discussions) to share your workflows!

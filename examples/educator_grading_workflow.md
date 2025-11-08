# Educator Grading Workflow Examples

This guide demonstrates efficient grading workflows using Canvas MCP with Claude Desktop.

## Quick Grading Session Workflow

**Goal**: Grade assignments efficiently while maintaining consistency.

### Step 1: See What Needs Grading

```
Educator: "Show me submissions for Assignment 3 in BADM 350"

Claude displays:
- Total submissions: 87/90 submitted
- Ungraded: 87
- Late submissions: 5
- Missing: 3 students
```

### Step 2: Review the Rubric

```
Educator: "Show me the rubric for Assignment 3"

Claude shows:
- Rubric criteria
- Point values
- Rating descriptions
- Total possible points
```

### Step 3: Identify Patterns

```
Educator: "Which students haven't submitted?"

Claude lists:
- Student names (anonymized if enabled)
- Enrollment status
- Past submission history
```

## Bulk Grading Workflow (Code Execution API)

**Goal**: Grade large numbers of submissions token-efficiently.

### Scenario: Grading 90 Jupyter Notebooks

**Traditional Approach Issues:**
- 90 submissions × 15K tokens = 1.35M tokens
- Expensive and slow
- May exceed context limits

**Code Execution Approach:**

```typescript
Educator: "Grade all Jupyter notebook submissions for Assignment 123 in course 60366"

Claude Code:
import { bulkGrade } from './canvas/grading/bulkGrade';

await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    // Find the notebook attachment
    const notebook = submission.attachments?.find(f =>
      f.filename.endsWith('.ipynb')
    );

    if (!notebook) {
      console.log(`No notebook found for user ${submission.user_id}`);
      return null; // Skip this submission
    }

    // Fetch and analyze notebook (happens locally!)
    const notebookData = await fetch(notebook.url).then(r => r.json());

    // Check for execution errors
    const hasErrors = notebookData.cells.some(cell =>
      cell.outputs?.some(output =>
        output.output_type === 'error'
      )
    );

    // Check for required sections
    const hasAllSections = [
      'Introduction',
      'Analysis',
      'Conclusion'
    ].every(section =>
      notebookData.cells.some(cell =>
        cell.source.join('').includes(section)
      )
    );

    // Determine grade
    let points = 0;
    let feedback = "";

    if (!hasAllSections) {
      points = 50;
      feedback = "Missing required sections. See assignment instructions.";
    } else if (hasErrors) {
      points = 70;
      feedback = "Code contains errors. Please fix and resubmit for partial credit.";
    } else {
      points = 100;
      feedback = "Great work! All requirements met and code executes without errors.";
    }

    return {
      points: points,
      rubricAssessment: {
        "_8027": { points: points }
      },
      comment: feedback
    };
  },
  dryRun: true // Preview first!
});

Result:
✓ Would grade 87 submissions
⊘ Would skip 3 (no notebook found)
✗ 0 errors

Educator: "Looks good! Apply the grades"
[Run again with dryRun: false]

Final Result:
✓ Graded 87 submissions
⊘ Skipped 3
✗ 0 errors
Time: 2 minutes
Token usage: 3,500 (vs 1.35M traditional)
```

**Benefits:**
- 99.7% token reduction
- Consistent grading logic
- Fast execution (minutes, not hours)
- Easy to customize logic

## Discussion Grading Workflow

**Goal**: Grade discussion participation with initial post + peer review requirements.

### View Discussion Participation

```
Educator: "Show me participation in Discussion 990001"

Claude analyzes:
- Students who posted
- Number of peer reviews per student
- Late posts
- Quality indicators
```

### Bulk Grade Discussion

```typescript
Educator: "Grade discussion 990001 with: 10 pts for initial post, 5 pts per peer review (minimum 2 reviews), max 10 pts for peer reviews"

Claude Code:
import { bulkGradeDiscussion } from './canvas/discussions/bulkGradeDiscussion';

// Preview first (dry run)
await bulkGradeDiscussion({
  courseIdentifier: "60365",
  topicId: "990001",
  criteria: {
    initialPostPoints: 10,
    peerReviewPointsEach: 5,
    requiredPeerReviews: 2,
    maxPeerReviewPoints: 10
  },
  dryRun: true
});

Result Preview:
Total students: 85
  - Full credit (20 pts): 67 students
  - Partial credit: 15 students
  - No credit: 3 students

Breakdown:
  - Initial post only, no peer reviews: 8 students (10/20 pts)
  - Initial + 1 peer review: 7 students (15/20 pts)
  - No participation: 3 students (0/20 pts)

Educator: "Apply these grades"
[Run with dryRun: false and assignmentId specified]
```

## Analytics-Driven Grading Workflow

**Goal**: Use analytics to inform grading decisions.

### Identify Outliers

```
Educator: "Show me analytics for Assignment 5"

Claude provides:
- Grade distribution
- Average: 78.5
- Median: 82
- Standard deviation: 15.2
- Outliers (< 50 or > 95)
```

### Review Low Performers

```
Educator: "Which students scored below 60 on Assignment 5?"

Claude lists (anonymized):
- Student_abc123: 45/100
- Student_def456: 52/100
- Student_ghi789: 58/100

Educator: "Show me Student_abc123's submission"
[Claude fetches submission for review]
```

## Peer Review Grading Workflow

**Goal**: Evaluate and grade peer review quality.

### Analyze Peer Review Completion

```
Educator: "Show me peer review completion for Assignment 2"

Claude provides:
- Completion rate: 78% (70/90 students)
- Incomplete: 20 students
- Average reviews per student: 2.3
- Students with 0 reviews: 5
```

### Review Peer Review Quality

```
Educator: "Analyze the quality of peer reviews for Assignment 2"

Claude analyzes:
- Average comment length
- Specificity scores
- Constructive feedback indicators
- Generic/low-effort reviews flagged
```

### Send Reminders for Incomplete Reviews

```
Educator: "Send reminders to students who haven't completed peer reviews"

Claude:
1. Identifies 20 students with incomplete reviews
2. Drafts personalized reminders
3. Sends via Canvas messaging
4. Confirms delivery
```

## Rubric-Based Grading Workflow

**Goal**: Apply rubrics consistently across submissions.

### Create a Rubric

```
Educator: "Create a rubric for the final project with criteria for: content (40 pts), organization (20 pts), writing quality (20 pts), and citations (20 pts)"

Claude creates:
- 4 criteria with point values
- Rating levels (Excellent, Good, Needs Improvement, Unsatisfactory)
- Clear descriptions for each level
```

### Grade Using Rubric

```
Educator: "Grade Student_abc123's submission using the final project rubric"

Claude:
1. Fetches submission
2. Shows rubric
3. Guides through each criterion
4. Applies grades
5. Generates overall score and feedback
```

## Managing Late Submissions

**Goal**: Track and grade late work with appropriate penalties.

### Identify Late Submissions

```
Educator: "Which submissions for Assignment 3 were late?"

Claude lists:
- 12 late submissions
- Hours/days late
- Your late policy (from syllabus)
- Suggested penalties
```

### Apply Late Penalties

```
Educator: "Apply a 10% penalty per day late, max 3 days"

Claude calculates:
- Student_abc123: 2 days late, earned 85 → final 68 (20% penalty)
- Student_def456: 1 day late, earned 90 → final 81 (10% penalty)
- Student_ghi789: 5 days late → 0 (exceeds max)
```

## Feedback Workflow

**Goal**: Provide meaningful, consistent feedback.

### Bulk Feedback Comments

```typescript
Educator: "Add feedback comments to all graded submissions"

Claude Code:
await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "125",
  gradingFunction: (submission) => {
    const score = submission.score;

    let comment = "";
    if (score >= 90) {
      comment = "Excellent work! Your analysis was thorough and well-supported.";
    } else if (score >= 80) {
      comment = "Good work! Consider strengthening your supporting evidence.";
    } else if (score >= 70) {
      comment = "Satisfactory work. Review assignment rubric for areas to improve.";
    } else {
      comment = "Please see me during office hours to discuss your submission.";
    }

    return {
      points: score,
      rubricAssessment: {},
      comment: comment
    };
  }
});
```

## Progress Monitoring Workflow

**Goal**: Track student progress throughout the semester.

### Student Performance Trends

```
Educator: "Show me Student_abc123's performance trend"

Claude analyzes:
- All graded assignments
- Grade trajectory (improving/declining)
- Missing work
- At-risk indicators
```

### Identify At-Risk Students

```
Educator: "Which students are at risk in BADM 350?"

Claude identifies students with:
- Falling grade trends
- Missing multiple assignments
- Low participation
- Below 70% overall

Suggests:
- Early intervention
- Academic support resources
- Meeting invitations
```

## End-of-Semester Workflow

**Goal**: Final grading and grade posting.

### Final Grade Calculation

```
Educator: "Calculate final grades for BADM 350 using: Assignments 50%, Midterm 20%, Final 30%"

Claude:
1. Fetches all assignment grades
2. Applies category weights
3. Calculates final percentages
4. Converts to letter grades
5. Identifies borderline cases
```

### Grade Distribution Review

```
Educator: "Show me the final grade distribution"

Claude provides:
- A: 23 students (25.6%)
- B: 38 students (42.2%)
- C: 20 students (22.2%)
- D: 6 students (6.7%)
- F: 3 students (3.3%)

+ Histogram visualization
+ Comparison to department averages
```

## Best Practices for Efficient Grading

### 1. Use Consistent Rubrics
- Create detailed rubrics before assignment release
- Apply rubrics consistently across all submissions
- Document rating criteria clearly

### 2. Leverage Bulk Operations
- Use code execution API for 50+ submissions
- Apply consistent logic programmatically
- Preview with dry runs before applying

### 3. Enable Data Anonymization
```bash
# In .env file
ENABLE_DATA_ANONYMIZATION=true
```
- Reduces bias in grading
- FERPA compliant
- De-anonymize when needed via local mapping files

### 4. Provide Timely Feedback
- Grade in batches (easier to maintain consistency)
- Use template comments for common feedback
- Customize for individual circumstances

### 5. Track Progress
- Monitor completion rates regularly
- Identify struggling students early
- Intervene before it's too late

### 6. Automate Reminders
- Send bulk reminders for missing work
- Follow up on incomplete peer reviews
- Use message templates for consistency

## Common Grading Scenarios

### Scenario 1: Regrading Requests
```
Student requests regrade on Assignment 4

Educator: "Show me Student_abc123's Assignment 4 submission and grade"
[Review submission]
Educator: "What did I dock points for?"
[Review rubric assessment]
Educator: "Adjust the Organization criterion to 18/20 and update the comment"
[Apply change]
```

### Scenario 2: Extra Credit
```
Educator: "Add 5 bonus points to all students who attended the guest lecture"

[Claude can help identify attendees and apply bonus points]
```

### Scenario 3: Curve Application
```
Educator: "Apply a 5-point curve to all Assignment 6 grades"

Claude:
- Fetches all grades
- Adds 5 points (capped at max)
- Updates submissions
- Reports: 87 students affected, 3 already at max
```

These workflows demonstrate how Canvas MCP can significantly reduce grading time while improving consistency and fairness!

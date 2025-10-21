---
name: grading-assistant
description: Helps educators efficiently grade Canvas submissions with rubric consistency, personalized feedback, and batch processing workflows
tags: [educator, grading, rubrics, feedback, efficiency]
version: 1.0.0
mcp_server: canvas-api
author: Canvas MCP Team
privacy: FERPA-compliant, uses Canvas MCP anonymization
---

# Grading Assistant Skill

## Purpose
Streamline educator grading workflows by providing rubric-based grading assistance, personalized feedback generation, batch processing capabilities, and consistency checking across submissions.

## When to Activate
Activate this skill when educators ask about:
- "Help me grade these submissions"
- "I need to grade [assignment name]"
- "Apply this rubric to student work"
- "Give me feedback suggestions for this submission"
- Batch grading assignments
- Maintaining grading consistency
- Generating personalized feedback
- Rubric application

## Required MCP Tools
This skill uses the following Canvas MCP tools:
- `get_assignment_details` - Get assignment and rubric information
- `list_assignment_submissions` - Fetch all submissions for an assignment
- `get_submission_details` - Get individual submission content
- `grade_with_rubric` - Apply rubric scores and comments
- `get_rubric_details` - Review rubric criteria and levels
- `list_courses` - Get course information

## FERPA Compliance
This skill respects Canvas MCP's data anonymization settings:
- When `ENABLE_DATA_ANONYMIZATION=true`, student names are anonymized
- All grading recommendations use anonymous IDs
- Educators can map anonymous IDs to real students locally
- No PII is sent to AI for analysis

## Process Flow

### Step 1: Context Gathering
1. Identify the assignment (by name or ID)
2. Call `get_assignment_details` to get rubric and requirements
3. Call `list_assignment_submissions` to get all submissions
4. Call `get_rubric_details` if rubric is used

### Step 2: Grading Mode Selection
Determine the appropriate mode based on educator needs:

**A. Individual Grading Mode**
- Grade one submission at a time
- Detailed feedback for each criterion
- Interactive rubric application

**B. Batch Grading Mode**
- Process multiple submissions
- Consistent rubric application
- Pattern identification across submissions

**C. Review Mode**
- Check grading consistency
- Identify outliers
- Suggest grade adjustments

### Step 3: Rubric Application (If Applicable)

**For each rubric criterion**:
1. Understand the criterion description
2. Review performance level descriptors
3. Analyze student work against descriptors
4. Recommend appropriate level
5. Suggest specific feedback

**Consistency checks**:
- Compare similar responses across submissions
- Flag potential grading discrepancies
- Ensure criteria are applied uniformly

### Step 4: Feedback Generation

**Personalized feedback includes**:
- Strengths demonstrated in the work
- Specific areas for improvement
- Connection to rubric criteria
- Actionable suggestions
- Encouraging tone

**Feedback templates** (adapt to specific work):
- **Excellent work**: Highlight specific strengths + challenge for growth
- **Good work**: Acknowledge strengths + specific improvements
- **Needs improvement**: Constructive guidance + concrete next steps
- **Incomplete**: What's missing + how to complete

### Step 5: Batch Processing Workflow

**For batch grading**:
1. Process submissions in logical order (alphabetical, by section, etc.)
2. Apply rubric consistently
3. Generate individualized feedback
4. Track common errors/patterns
5. Provide batch summary with insights

**Batch insights include**:
- Common mistakes across submissions
- Well-done elements
- Rubric criteria causing confusion
- Suggestions for future assignment revisions

## Grading Assistant Modes

### Mode 1: Interactive Rubric Grading

**Use case**: Educator wants guidance while grading

**Process**:
```
1. Fetch submission content
2. Display rubric criteria
3. For each criterion:
   - Show student's work relevant to criterion
   - Display rubric levels
   - Recommend appropriate level with reasoning
   - Suggest specific feedback
4. Summarize recommended grade
5. Allow educator to adjust before submitting
```

**Example interaction**:
```
Educator: "Help me grade John's essay submission"

Skill:
- Fetches essay content
- Retrieves rubric
- For "Thesis Statement" criterion:
  * Shows student's thesis
  * Recommends "Proficient" level
  * Explains why (clear, specific, arguable)
  * Suggests feedback: "Strong thesis. Consider..."
- Continues for all criteria
- Provides overall grade recommendation and summary
```

### Mode 2: Batch Grading with Consistency

**Use case**: Grade many submissions efficiently

**Process**:
```
1. Fetch all submissions
2. Identify common patterns
3. Create grading templates for common scenarios
4. For each submission:
   - Apply rubric
   - Use appropriate feedback template
   - Customize for individual work
5. Provide batch summary
```

**Example interaction**:
```
Educator: "Grade all submissions for Assignment 3"

Skill:
- Fetches 45 submissions
- Identifies 3 common response patterns
- Creates feedback templates
- Processes each submission with:
  * Rubric scores
  * Personalized feedback
  * Consistency with similar submissions
- Generates summary: "32 proficient, 10 developing, 3 needs revision.
  Common issue: Citation formatting. 85% demonstrated good analysis."
```

### Mode 3: Feedback Enhancement

**Use case**: Educator has grades, needs better feedback

**Process**:
```
1. Fetch existing grades/comments
2. Analyze for:
   - Specificity
   - Actionability
   - Tone
   - Completeness
3. Suggest enhanced feedback
4. Maintain educator's grading decisions
```

**Example interaction**:
```
Educator: "Make my feedback more specific"

Skill:
- Reviews: "Good work. 85/100"
- Enhances to: "Excellent analysis of the primary source (criterion 1:
  exemplary). Your thesis is clear and well-supported. To improve further,
  consider integrating more secondary sources in section 2 (criterion 3:
  proficient). This would strengthen your argument. Great work overall! 85/100"
```

### Mode 4: Grading Analytics & Consistency Check

**Use case**: Review grading for fairness and consistency

**Process**:
```
1. Analyze grade distribution
2. Check rubric application consistency
3. Identify potential outliers
4. Suggest reviews where needed
5. Provide grade distribution insights
```

**Example interaction**:
```
Educator: "Check my grading consistency for this assignment"

Skill:
- Analyzes 50 graded submissions
- Finds: "Criterion 2 (Analysis) shows inconsistent application.
  Similar responses scored 3-5 points apart."
- Identifies 5 submissions for review
- Shows: "Grade distribution: Mean 82, Median 84, SD 12.
  Typical for this assignment type."
```

## Feedback Best Practices

### Effective Feedback Components

**1. Specific Praise**
❌ "Good job"
✅ "Your thesis statement clearly articulates your argument and previews your main points"

**2. Targeted Improvement**
❌ "Needs work"
✅ "Consider adding transitions between paragraphs 3 and 4 to improve flow"

**3. Rubric Connection**
✅ "Criterion 1 (Thesis): Exemplary. Your thesis is specific, arguable, and well-positioned"

**4. Actionable Guidance**
✅ "Next time, try outlining your evidence before writing to ensure balanced support"

**5. Encouraging Tone**
✅ "You're making great progress in your analytical writing. Keep it up!"

### Feedback Templates

**Template: Exemplary Work**
```
[Specific strength] demonstrates [criterion] at the exemplary level.
Your [specific element] shows [what it demonstrates].
To continue growing: [stretch goal].
Excellent work!
```

**Template: Proficient Work**
```
Strong work on [specific element]. You successfully [what they did well].
To reach the next level, consider [specific improvement].
[Encouraging statement].
```

**Template: Developing Work**
```
You're making progress on [criterion]. I can see [positive element].
To improve: [specific, actionable steps].
[Encouraging forward look].
```

**Template: Needs Revision**
```
This submission needs revision to meet the assignment requirements.
Specifically: [what's missing or problematic].
Here's how to improve: [concrete steps].
Please see me in office hours if you'd like to discuss.
```

## Common Grading Scenarios

### Scenario 1: Clear Rubric, Objective Criteria
**Approach**: Direct rubric application with specific evidence
**Example**: Math problem set, coding assignment, lab report

### Scenario 2: Subjective Criteria, Needs Interpretation
**Approach**: Comparative assessment, provide rationale
**Example**: Essays, creative projects, discussions

### Scenario 3: Incomplete Submissions
**Approach**: Identify what's missing, provide completion guidance
**Example**: Partial submissions, missing components

### Scenario 4: Exceptional Work Beyond Rubric
**Approach**: Acknowledge excellence, provide stretch feedback
**Example**: Student exceeds assignment requirements

### Scenario 5: Academic Integrity Concerns
**Approach**: Flag for educator review, don't make assumptions
**Note**: Never accuse, but note patterns requiring attention

## Output Formats

### Individual Submission Grading

```markdown
## Grading Recommendation: [Student ID / Name]
**Assignment**: [Assignment Name]
**Submission Date**: [Date]
**Total Points Recommended**: [X/Y points]

### Rubric Breakdown

#### Criterion 1: [Name] ([X points])
**Recommended Level**: [Level name] ([Points])
**Reasoning**: [Why this level is appropriate based on student work]
**Feedback**: [Specific, personalized feedback for this criterion]

#### Criterion 2: [Name] ([X points])
[Same format]

### Overall Feedback
[Comprehensive feedback combining all criteria, highlighting strengths,
areas for improvement, and actionable next steps]

### Educator Notes
- [Any grading considerations or questions for educator to review]
- [Patterns noticed in this work]
```

### Batch Grading Summary

```markdown
## Batch Grading Summary: [Assignment Name]
**Submissions Graded**: [X]
**Date**: [Date]

### Grade Distribution
- **Exemplary (90-100)**: [N students]
- **Proficient (80-89)**: [N students]
- **Developing (70-79)**: [N students]
- **Needs Revision (<70)**: [N students]

**Mean**: [X] | **Median**: [X] | **SD**: [X]

### Common Strengths
1. [Pattern noticed across many submissions]
2. [Pattern noticed across many submissions]

### Common Areas for Improvement
1. [Pattern noticed across many submissions]
   - Suggestion: [How to address in future]
2. [Pattern noticed across many submissions]
   - Suggestion: [How to address in future]

### Rubric Criterion Analysis
**Criterion 1: [Name]**
- Mean score: [X]
- Most common level: [Level]
- Note: [Any patterns]

[Repeat for each criterion]

### Submissions Needing Review
1. [Student ID]: [Reason for review]
2. [Student ID]: [Reason for review]

### Recommendations for Future
- [Assignment design improvement]
- [Rubric clarification needed]
- [Instructional adjustment suggested]

### Individual Grading Details
[Link to or include individual grading for each submission]
```

## Consistency Guidelines

### Ensuring Fair Grading

**1. Calibration Phase**
- Grade 3-5 submissions first
- Establish grading standards
- Create mental anchors for each rubric level

**2. Regular Calibration Checks**
- Every 10-15 submissions, review previous grades
- Ensure consistent application
- Adjust if drift detected

**3. Comparative Grading**
- Group similar responses
- Ensure similar work receives similar scores
- Document reasoning for variations

**4. Rubric Adherence**
- Always reference rubric criteria
- Don't grade on implicit expectations
- If rubric doesn't fit, note for revision

**5. Blind Grading When Possible**
- Use anonymized IDs (Canvas MCP provides this)
- Grade work, not students
- Reduce unconscious bias

## Error Handling

**No rubric available**:
- Offer holistic grading guidance
- Ask educator for grading criteria
- Provide general feedback structure

**Submission not viewable**:
- Explain the limitation
- Suggest checking Canvas directly
- Offer to grade based on description

**Large batch (>50 submissions)**:
- Recommend chunking into smaller batches
- Process in groups of 20-25
- Provide break points for educator review

**Ambiguous rubric criteria**:
- Flag ambiguity for educator
- Request clarification
- Provide best-effort interpretation

## Integration with Other Skills

**Works well with**:
- `rubric-designer`: Use well-designed rubrics for grading
- `student-support-identifier`: Flag struggling students during grading
- `assignment-analytics`: Combine grading with performance analysis

## Skill Maintenance Notes

**Update when**:
- Canvas MCP grading tools change
- New feedback research emerges
- Educator feedback suggests improvements
- Rubric standards evolve

**Version History**:
- v1.0.0: Initial release with core grading functionality

---

*This skill is part of the Canvas MCP Skills collection. For more information, visit: https://github.com/vishalsachdev/canvas-mcp*

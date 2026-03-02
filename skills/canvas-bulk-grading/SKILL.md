---
name: canvas-bulk-grading
description: Bulk grading workflows for Canvas LMS assignments using rubrics. Covers single grading, batch grading, and code execution strategies with safety-first dry runs.
---

# Canvas Bulk Grading

Grade Canvas LMS assignments efficiently using rubric-based workflows. This skill requires the Canvas MCP server to be running and authenticated with an instructor or TA token.

## Prerequisites

- Canvas MCP server running and connected
- Authenticated with an **educator** (instructor/TA) Canvas API token
- Assignment must exist and have submissions to grade
- Rubric must already be created in Canvas and associated with the assignment (Canvas API cannot reliably create rubrics -- use the Canvas web UI for that)

## Workflow

### Step 1: Gather Assignment and Rubric Information

Before grading, retrieve the assignment details and its rubric criteria.

```
get_assignment_details(course_identifier, assignment_id)
```

Then get the rubric. Use `get_assignment_rubric_details` if the rubric is already linked to the assignment, or `list_all_rubrics` to browse all rubrics in the course:

```
get_assignment_rubric_details(course_identifier, assignment_id)
list_all_rubrics(course_identifier)
get_rubric_details(course_identifier, rubric_id)
```

Record the **criterion IDs** (often prefixed with underscore, e.g., `_8027`) and **rating IDs** from the rubric response. These are required for rubric-based grading.

### Step 2: List Submissions

Retrieve all student submissions to determine how many need grading:

```
list_submissions(course_identifier, assignment_id)
```

Note the `user_id` for each submission and the `workflow_state` (submitted, graded, pending_review). Count the submissions that need grading to determine which strategy to use.

### Step 3: Choose a Grading Strategy

Use this decision tree based on the number of submissions to grade:

```
How many submissions need grading?
|
+-- 1-9 submissions
|   Use grade_with_rubric (one call per submission)
|
+-- 10-29 submissions
|   Use bulk_grade_submissions (concurrent batch processing)
|   Set max_concurrent: 5, rate_limit_delay: 1.0
|   ALWAYS run with dry_run: true first
|
+-- 30+ submissions OR custom grading logic needed
    Use execute_typescript with bulkGrade function
    99.7% token savings -- grading logic runs locally
    ALWAYS run with dry_run: true first
```

### Strategy A: Single Grading (1-9 submissions)

Call `grade_with_rubric` once per student:

```
grade_with_rubric(
  course_identifier,
  assignment_id,
  user_id,
  rubric_assessment: {
    "criterion_id": {
      "points": <number>,
      "rating_id": "<string>",    // optional
      "comments": "<string>"      // optional per-criterion feedback
    }
  },
  comment: "Overall feedback"     // optional
)
```

### Strategy B: Bulk Grading (10-29 submissions)

**Always dry run first.** Build the grades dictionary mapping each user ID to their grade data, then validate before submitting:

```
bulk_grade_submissions(
  course_identifier,
  assignment_id,
  grades: {
    "user_id_1": {
      "rubric_assessment": {
        "criterion_id": {"points": 85, "comments": "Good analysis"}
      },
      "comment": "Overall feedback"
    },
    "user_id_2": {
      "grade": 92,
      "comment": "Excellent work"
    }
  },
  dry_run: true,          // VALIDATE FIRST
  max_concurrent: 5,
  rate_limit_delay: 1.0
)
```

Review the dry run output. If everything looks correct, re-run with `dry_run: false`.

### Strategy C: Code Execution (30+ submissions)

For large classes or custom grading logic, use `execute_typescript` to run grading locally. This avoids loading all submission data into the conversation context.

```
execute_typescript(code: `
  import { bulkGrade } from './canvas/grading/bulkGrade.js';

  await bulkGrade({
    courseIdentifier: "COURSE_ID",
    assignmentId: "ASSIGNMENT_ID",
    gradingFunction: (submission) => {
      // Custom grading logic runs locally -- no token cost
      const notebook = submission.attachments?.find(
        f => f.filename.endsWith('.ipynb')
      );

      if (!notebook) return null; // skip ungraded

      return {
        points: 100,
        rubricAssessment: { "_8027": { points: 100 } },
        comment: "Graded via automated review"
      };
    }
  });
`)
```

Use `search_canvas_tools("grading", "signatures")` to discover available TypeScript modules and their function signatures before writing code.

## Token Efficiency

The three strategies have very different token costs:

| Strategy | When | Token Cost | Why |
|----------|------|------------|-----|
| `grade_with_rubric` | 1-9 submissions | Low | Few round-trips, small payloads |
| `bulk_grade_submissions` | 10-29 submissions | Medium | One call with batch data |
| `execute_typescript` | 30+ submissions | Minimal | Grading logic runs locally; only the code string is sent. **99.7% savings** vs loading all submissions into context |

The key insight: as submission count grows, sending grading logic to the server (code execution) is far cheaper than bringing all submission data into the conversation.

## Safety Rules

1. **Always dry run first.** For `bulk_grade_submissions`, set `dry_run: true` before the real run. Review the output for correctness.
2. **Verify the rubric before grading.** Confirm criterion IDs, point ranges, and rating IDs match the assignment rubric. Mismatched IDs cause silent failures or incorrect grades.
3. **Spot-check before bulk.** For Strategy B and C, grade 1-2 submissions manually with `grade_with_rubric` first. Verify in Canvas that the grade and rubric feedback appear correctly.
4. **Respect rate limits.** Use `max_concurrent: 5` and `rate_limit_delay: 1.0` (1 second between batches). Canvas rate limits are approximately 700 requests per 10 minutes.
5. **Do not grade without explicit instructor confirmation.** Always present the grading plan (rubric mapping, point values, number of students affected) and wait for approval before submitting grades.

## Example Prompts

- "Grade Assignment 5 using the rubric"
- "Show me the rubric for the midterm project and grade all submissions"
- "Bulk grade all ungraded submissions for Assignment 3 -- give full marks on criterion 1 and 80% on criterion 2"
- "How many submissions still need grading for the final paper?"
- "Dry run bulk grading for Assignment 7 so I can review before submitting"
- "Use code execution to grade all 150 homework submissions with custom logic"

## Error Recovery

| Error | Cause | Action |
|-------|-------|--------|
| 401 Unauthorized | Token expired or invalid | Regenerate Canvas API token |
| 403 Forbidden | Not an instructor/TA for this course | Verify Canvas role |
| 404 Not Found | Wrong course, assignment, or rubric ID | Re-check IDs with `list_assignments` or `list_all_rubrics` |
| 422 Unprocessable | Invalid rubric assessment format | Verify criterion IDs and point ranges match the rubric |
| Partial failures in bulk | Some grades submitted, others failed | Check the response for per-student status; retry only failed ones |

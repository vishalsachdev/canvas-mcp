# Example: Bulk Grading Jupyter Notebooks

This example demonstrates how the code execution API can keep per-submission processing out of the model's context.

## Scenario

Grade 90 Jupyter notebook submissions for Assignment 123.
- Award 100 points if notebook runs without errors
- Award 0 points if notebook has errors
- Skip submissions without notebooks

## Traditional Approach (high context use)

### The Problem

```typescript
// Load ALL submissions into context
const submissions = await list_submissions({
  courseIdentifier: "60366",
  assignmentId: "123"
});
// Each returned submission consumes model context.

// Process each one (more tokens!)
for (const sub of submissions) {
  // Each submission's full data is in Claude's context
  const notebook = findNotebook(sub);
  const analysis = analyzeNotebook(notebook);

  await grade_with_rubric({
    courseIdentifier: "60366",
    assignmentId: "123",
    userId: sub.userId,
    rubricAssessment: { ... },
    comment: analysis.comment
  });
}
```

### Why This Is Inefficient

- ❌ All 90 submissions loaded into Claude's context
- ❌ Context use grows with the returned submission data
- ❌ This example processes submissions sequentially
- ❌ Risk of hitting token limits
- ❌ Model cost grows with payload size and the selected model

## Code Execution Approach (lower context use)

### The Solution

```typescript
import { bulkGrade } from './canvas/grading/bulkGrade';

await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    // ⭐ Process bulk operations locally without loading every item
    //    into the model's context; only selected output is returned.

    const notebook = submission.attachments?.find(
      f => f.filename.endsWith('.ipynb')
    );

    if (!notebook) {
      console.log(`No notebook for user ${submission.userId}`);
      return null; // Skip this submission
    }

    // Download and analyze notebook (locally!)
    const analysis = analyzeNotebook(notebook.url);

    if (analysis.hasErrors) {
      return {
        points: 0,
        rubricAssessment: {
          "_8027": {
            points: 0,
            comments: `Found ${analysis.errors.length} errors: ${analysis.errors.join(', ')}`
          }
        },
        comment: "Please fix errors and resubmit. See rubric for details."
      };
    }

    // No errors - full points!
    return {
      points: 100,
      rubricAssessment: {
        "_8027": {
          points: 100,
          comments: "Excellent work! All cells executed successfully."
        }
      },
      comment: "Great submission! Notebook runs perfectly without errors."
    };
  }
});
```

### What You See (Output)

```
Starting bulk grading for assignment 123...
Found 90 submissions to process

✓ Graded submission for user 12345
✓ Graded submission for user 12346
Skipped submission for user 12347 (no notebook)
✓ Graded submission for user 12348
✗ Failed to grade user 12349: Network timeout
...

Bulk grading complete:
  Total: 90
  Graded: 87
  Skipped: 2
  Failed: 1

First 5 results:
  - User 12345: ✓ Success
  - User 12346: ✓ Success
  - User 12347: Skipped
  - User 12348: ✓ Success
  - User 12349: ✗ Failed
```

### Why This Is Efficient

- ✅ Only selected output needs to return to the model
- ✅ Data processed locally in execution environment
- ✅ Supported operations can process concurrently
- ✅ Less per-item pressure on the model's context window
- ✅ Scale remains subject to Canvas rate limits and local resources

## Token Comparison

| Metric | Traditional | Code Execution |
|--------|-------------|----------------|
| Model Context | May receive each submission and result | Receives code and selected output |
| Item Processing | Orchestrated through tool calls | Local execution environment |
| Concurrency | Depends on client orchestration | Available in supported bulk operations |
| Scale | Bound by client context and tool-call overhead | Bound by Canvas rate limits and local resources |

## Advanced Example: Custom Analysis

You can implement any grading logic you want:

```typescript
await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    const notebook = submission.attachments?.find(
      f => f.filename.endsWith('.ipynb')
    );

    if (!notebook) return null;

    // Custom analysis logic
    const analysis = {
      cellCount: countCells(notebook),
      hasDocstrings: checkDocstrings(notebook),
      passesTests: runTests(notebook),
      codeQuality: analyzeCodeQuality(notebook)
    };

    // Complex grading rubric
    let points = 0;
    const rubricComments: Record<string, any> = {};

    // Criterion 1: Functionality (50 points)
    if (analysis.passesTests) {
      points += 50;
      rubricComments["_8027"] = {
        points: 50,
        comments: "All tests pass! ✓"
      };
    } else {
      rubricComments["_8027"] = {
        points: 0,
        comments: "Some tests failed. See notebook for details."
      };
    }

    // Criterion 2: Documentation (30 points)
    const docPoints = analysis.hasDocstrings ? 30 : 15;
    points += docPoints;
    rubricComments["_8028"] = {
      points: docPoints,
      comments: analysis.hasDocstrings
        ? "Excellent documentation!"
        : "Add more docstrings to improve documentation."
    };

    // Criterion 3: Code Quality (20 points)
    const qualityPoints = Math.min(20, analysis.codeQuality * 20);
    points += qualityPoints;
    rubricComments["_8029"] = {
      points: qualityPoints,
      comments: `Code quality score: ${analysis.codeQuality * 100}%`
    };

    return {
      points,
      rubricAssessment: rubricComments,
      comment: `Total: ${points}/100. Great work on ${
        analysis.passesTests ? 'passing all tests' : 'your effort'
      }!`
    };
  }
});
```

## Dry Run Mode (Testing)

Test your grading logic without actually grading:

```typescript
await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  dryRun: true,  // ⭐ Test mode - doesn't actually grade
  gradingFunction: (submission) => {
    // Your grading logic here
    console.log(`Would grade: ${submission.userId}`);
    return { points: 100, ... };
  }
});
```

## Best Practices

1. **Always test with dry run first** before grading for real
2. **Handle errors gracefully** - return `null` to skip problematic submissions
3. **Provide detailed rubric comments** to help students understand their grades
4. **Log progress** using `console.log()` to track grading status
5. **Validate rubric criterion IDs** before grading (use `list_assignment_rubrics`)

## Common Rubric Criterion ID Patterns

Canvas rubric criterion IDs typically start with underscore:
- `"_8027"` - Common format
- `"criterion_123"` - Alternative format
- `"8027"` - Without underscore (rare)

To find the correct IDs for your rubric:

```typescript
// First, discover the rubric structure
const rubric = await search_canvas_tools("list_assignment_rubrics", "full");

// Then use the correct criterion IDs in bulkGrade
```

## Troubleshooting

### "No exported function found"
- Check that your TypeScript files have `export async function` declarations
- Verify file paths are correct

### "Criterion ID not found"
- Use `list_assignment_rubrics` to get correct criterion IDs
- Remember: IDs often start with underscore (`"_8027"`)

### "Rate limit exceeded"
- Add delays between grading operations
- Reduce `maxConcurrent` parameter (default: 5)

### "Submission not found"
- Check that `courseIdentifier` and `assignmentId` are correct
- Verify students have actually submitted

## Summary

The code execution API can reduce model-context pressure by keeping per-item work local:

- **Traditional**: Tool-by-tool processing may return each item to the model
- **Code Execution**: Process items locally and return only selected output

This pattern can support many bulk operations:
- Grading submissions
- Sending messages to multiple students
- Analyzing discussion participation
- Generating reports

**Result**: Lower context use for suitable bulk workflows; actual savings and speed vary by workload and client.

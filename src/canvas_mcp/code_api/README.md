# Canvas Code Execution API

This directory contains the TypeScript code execution API for token-efficient bulk operations with Canvas LMS.

## Overview

The Code Execution API allows an AI client to process large datasets locally in the execution environment rather than loading every item into the model's context. Actual token savings depend on the workload and selected output.

### Context Efficiency

| Approach | Model Context | Item Processing |
|----------|---------------|-----------------|
| **Traditional** (call MCP tools) | May receive each submission and result | Orchestrated through tool calls |
| **Code Execution** (run locally) | Receives code and selected output | Runs in the local execution environment |

## Architecture

```
code_api/
├── client.ts              # Canvas API HTTP client with retry logic
├── index.ts               # Main entry point
└── canvas/
    ├── assignments/       # Assignment operations
    │   └── listSubmissions.ts
    ├── grading/          # Grading operations (HIGHEST VALUE)
    │   ├── gradeWithRubric.ts
    │   └── bulkGrade.ts  # Local per-submission processing
    ├── courses/          # Course operations
    ├── discussions/      # Discussion operations
    └── communications/   # Messaging operations
```

## Setup

### Environment Variables

The code execution API requires these environment variables:

```bash
# These should be available from the MCP server's .env file
CANVAS_API_URL=https://canvas.instructure.com/api/v1
CANVAS_API_TOKEN=your_canvas_api_token_here
```

### Initialization

The client auto-initializes from environment variables:

```typescript
import { initializeCanvasClient } from './client';

// Manual initialization (optional)
initializeCanvasClient(
  'https://canvas.instructure.com/api/v1',
  'your_api_token',
  30000 // timeout in ms
);
```

## Usage

### Discovery

Use the `search_canvas_tools` MCP tool to discover available operations:

```typescript
// Search for grading tools
search_canvas_tools("grading", "signatures")

// List all available tools
search_canvas_tools("", "names")
```

### Basic Operations

```typescript
import { listSubmissions, gradeWithRubric } from './canvas/grading';

// List submissions (stays in execution environment!)
const submissions = await listSubmissions({
  courseIdentifier: "60366",
  assignmentId: "123",
  includeUser: true  // Include user details (name, email, etc.)
});

// Access user information
submissions.forEach(sub => {
  console.log(`${sub.user?.name} (${sub.user?.email}): ${sub.score ?? 'ungraded'}`);
});

// Grade a single submission
await gradeWithRubric({
  courseIdentifier: "60366",
  assignmentId: "123",
  userId: 456,
  rubricAssessment: {
    "_8027": {
      points: 100,
      comments: "Excellent work!"
    }
  },
  comment: "Great submission!"
});
```

### Bulk Operations (⭐ Highest Value)

```typescript
import { bulkGrade } from './canvas/grading';

// Grade 90 submissions without returning every item to the model.
await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  maxConcurrent: 5,  // Process 5 at a time
  rateLimitDelay: 1000,  // 1s between batches
  gradingFunction: async (submission) => {
    // This runs LOCALLY - no token cost!

    const notebook = submission.attachments?.find(
      f => f.filename.endsWith('.ipynb')
    );

    if (!notebook) {
      return null; // Skip
    }

    // Analyze notebook locally
    const hasErrors = await analyzeNotebook(notebook.url);

    if (hasErrors) {
      return {
        points: 0,
        rubricAssessment: { "_8027": { points: 0 } },
        comment: "Notebook has errors"
      };
    }

    return {
      points: 100,
      rubricAssessment: { "_8027": { points: 100 } },
      comment: "Perfect!"
    };
  }
});
```

## Key Features

### ✅ Direct Canvas API Calls

- No dependency on MCP tools (which return formatted strings)
- Works with raw Canvas API responses (JSON)
- Full type safety with TypeScript interfaces

### ✅ Error Handling & Retries

- Automatic retry logic with exponential backoff (1s, 2s, 4s)
- Don't retry 4xx errors (client errors)
- Retry 5xx errors and network failures

### ✅ Input Validation

- Rubric assessments validated before submission
- Points must be non-negative numbers
- Clear error messages for invalid data

### ✅ Concurrent Processing

- Process multiple submissions in parallel
- Configurable batch size (`maxConcurrent`)
- Rate limiting between batches
- Promise.allSettled for fault tolerance

### ✅ Form-Encoded Data Support

- Proper Canvas API format for rubric assessments
- Uses `rubric_assessment[criterion_id][field]` notation
- Handles URL-encoded form data correctly

## API Reference

### Client Functions

```typescript
// HTTP methods
canvasGet<T>(endpoint, params): Promise<T>
canvasPost<T>(endpoint, body): Promise<T>
canvasPut<T>(endpoint, body): Promise<T>
canvasPutForm<T>(endpoint, body): Promise<T>  // Form-encoded
canvasDelete<T>(endpoint): Promise<T>

// Pagination
fetchAllPaginated<T>(endpoint, params): Promise<T[]>
```

### Response Types

All responses use Canvas API's snake_case field names:

```typescript
interface Submission {
  id: number;
  user_id: number;        // NOT userId
  assignment_id: number;  // NOT assignmentId
  submitted_at: string | null;
  score: number | null;
  attachments?: Array<{
    id: number;
    filename: string;
    url: string;
    content_type: string;
  }>;
  user?: {                // Included when includeUser: true
    id: number;
    name: string;
    email: string;
    login_id: string;
    sortable_name: string;
  };
}
```

## Best Practices

### 1. Always Use Dry Run First

```typescript
await bulkGrade({
  ...params,
  dryRun: true  // Test without actually grading
});
```

### 2. Handle Errors Gracefully

```typescript
gradingFunction: (submission) => {
  try {
    // Your logic here
    return gradeResult;
  } catch (error) {
    console.error(`Error processing ${submission.user_id}:`, error);
    return null; // Skip on error
  }
}
```

### 3. Validate Rubric Criterion IDs

Canvas rubric criterion IDs often start with underscore:
- ✅ `"_8027"` - Correct format
- ❌ `"8027"` - May not work

Use `get_rubric` (with the assignment ID) to get correct IDs before grading.

### 4. Respect Rate Limits

```typescript
await bulkGrade({
  ...params,
  maxConcurrent: 3,      // Reduce if hitting rate limits
  rateLimitDelay: 2000   // Increase delay between batches
});
```

### 5. Log Progress

Use `console.log()` for visibility:

```typescript
gradingFunction: (submission) => {
  console.log(`Processing user ${submission.user_id}...`);
  // ... your logic
}
```

## Troubleshooting

### "Canvas client not initialized"

**Problem**: Environment variables not set

**Solution**:
```typescript
import { initializeCanvasClient } from './client';

initializeCanvasClient(
  process.env.CANVAS_API_URL!,
  process.env.CANVAS_API_TOKEN!
);
```

### "Canvas API error (401)"

**Problem**: Invalid or expired API token

**Solution**: Generate a new token in Canvas → Account → Settings → New Access Token.
If your institution disables self-service tokens (e.g. UIUC), request one through its IT
form instead — see [Common Issues](../../../examples/common_issues.md#cannot-create-access-token).

### "Canvas API error (404)"

**Problem**: Wrong course/assignment/user ID

**Solution**: Verify IDs are correct and resources exist

### "Criterion ID not found"

**Problem**: Rubric criterion ID is incorrect

**Solution**: Use `search_canvas_tools("rubric", "full")` to find correct IDs

### Rate Limit Errors

**Problem**: Too many concurrent requests

**Solution**: Reduce `maxConcurrent` and increase `rateLimitDelay`:

```typescript
await bulkGrade({
  ...params,
  maxConcurrent: 2,      // Slower but safer
  rateLimitDelay: 3000   // 3s between batches
});
```

## Examples

See `/examples/bulk_grading_example.md` for a comprehensive walkthrough.

## When to Use Code Execution vs MCP Tools

### Use Code Execution When:
- ✅ Processing 10+ submissions/items
- ✅ Performing bulk operations
- ✅ Need to analyze data locally
- ✅ Want custom bulk logic that returns selected output

### Use MCP Tools When:
- ✅ Single queries ("Show me course details")
- ✅ Simple lookups ("Get assignment 123")
- ✅ Interactive exploration
- ✅ Small datasets

## Performance

### Context Use

| Approach | Model Context | Operational Limits |
|----------|---------------|--------------------|
| Traditional tool calls | May receive each item and result | Client context and tool-call overhead |
| Code execution | Receives code and selected output | Canvas rate limits and local resources |

### Processing Time

Supported operations can use concurrent processing (`maxConcurrent: 5`). Runtime varies with Canvas response time, rate limits, local resources, and the grading logic.

Additional control:

- **Rate limiting**: Prevents Canvas API throttling

## Contributing

When adding new wrapper functions:

1. ✅ Use direct Canvas API calls (`canvasGet`, `canvasPost`, etc.)
2. ✅ Use snake_case for Canvas API field names
3. ✅ Add TypeScript type definitions
4. ✅ Include JSDoc comments with examples
5. ✅ Add error handling with clear messages
6. ✅ Update this README

## References

- [Anthropic Blog: Code Execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)
- [Canvas LMS API Documentation](https://developerdocs.instructure.com/services/canvas)
- [Canvas MCP Server](../../README.md)

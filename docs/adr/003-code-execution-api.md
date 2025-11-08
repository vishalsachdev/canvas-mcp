# ADR-003: Code Execution API for Bulk Operations

## Status

Accepted

Date: 2024-11-05

## Context

Traditional MCP tool calling has a significant token cost for bulk operations:

**Problem Example**: Grading 90 Jupyter notebook submissions
- Each submission: ~15,000 tokens (notebook + metadata + attachments)
- Total: 90 × 15K = 1,350,000 tokens
- Cost: Extremely expensive and slow
- Context limits: May exceed model context window

**Real Educator Pain Points:**
- Bulk grading assignments (50-200 students)
- Analyzing discussion participation across class
- Sending targeted reminders to subsets of students
- Processing peer review analytics

The traditional approach loads all data into Claude's context, then Claude makes decisions. This is wasteful for programmatic operations where logic can run locally.

**Key Insight**: Most bulk operations follow a pattern:
1. Fetch data from Canvas (cheap, fast)
2. Apply deterministic logic (e.g., "has errors? grade = 0; no errors? grade = 100")
3. Write results back to Canvas

Why send all data to Claude when logic can run locally?

## Decision

Implement a **Code Execution API** using TypeScript that:

1. **Runs locally** in Claude's code execution environment
2. **Makes direct Canvas API calls** from execution context
3. **Processes data locally** without loading into context
4. **Returns only summaries** to Claude's context

**Architecture:**

```
src/canvas_mcp/code_api/
├── client.ts                  # Canvas API client
├── index.ts                   # Entry point
└── canvas/
    ├── grading/
    │   ├── bulkGrade.ts       # Bulk grading
    │   └── gradeWithRubric.ts # Single grading
    ├── discussions/
    │   └── bulkGradeDiscussion.ts
    ├── assignments/
    │   └── listSubmissions.ts
    └── ...
```

**Discovery Mechanism:**
```python
@mcp.tool()
async def search_canvas_tools(query: str, detail_level: str) -> str:
    """Search TypeScript code API files by keyword."""
    # Returns: file paths, signatures, or full code
```

**Execution Flow:**
```
1. Claude discovers tool: search_canvas_tools("bulk grading")
2. Claude reads TypeScript: bulkGrade.ts
3. Claude writes execution code:
   await bulkGrade({
     courseId: "60366",
     assignmentId: "123",
     gradingFunction: (submission) => { /* logic */ }
   })
4. Execution happens locally (no context cost)
5. Summary flows back: "Graded 87, skipped 3, failed 0"
```

**Token Savings:**
- Traditional: 1.35M tokens
- Code execution: 3.5K tokens
- **Reduction: 99.7%**

## Alternatives Considered

### Alternative 1: Optimize Traditional Tool Calls
- **Approach**: Batch submissions, send fewer at a time
- **Pros**: No new architecture needed
- **Cons**: Still expensive, requires multiple round-trips, context limits
- **Rejected**: Doesn't solve fundamental token cost problem

### Alternative 2: Server-Side Batch Processing
- **Approach**: Add batch endpoints to MCP server
- **Pros**: Centralized processing
- **Cons**: Less flexible, harder to customize, defeats AI assistance
- **Rejected**: Removes Claude from decision-making

### Alternative 3: Python Code Execution
- **Approach**: Use Python instead of TypeScript
- **Pros**: Matches server language
- **Cons**: Claude Code execution environment is TypeScript-focused
- **Rejected**: TypeScript better supported in execution environment

### Alternative 4: Streaming Responses
- **Approach**: Stream submissions one at a time
- **Pros**: Reduces single response size
- **Cons**: Still loads data into context, many tool calls
- **Rejected**: Doesn't eliminate token cost

## Consequences

### Positive

- **Token Efficiency**: 99.7% reduction for bulk operations
- **Speed**: Much faster processing (parallel execution)
- **Flexibility**: Claude can write custom grading logic on-the-fly
- **Cost Savings**: Dramatic reduction in API costs
- **Scalability**: Can handle 100s of submissions
- **Context Preservation**: Frees up context for actual conversation
- **Discovery**: `search_canvas_tools` makes operations discoverable
- **Extensibility**: Easy to add new bulk operations

### Negative

- **Complexity**: Added TypeScript layer to Python project
- **Learning Curve**: Contributors need TypeScript knowledge
- **Debugging**: Harder to debug execution environment
- **Dual Maintenance**: Both Python tools and TypeScript API
- **Environment Dependency**: Requires Claude Code execution environment
- **Type Safety**: Need to maintain TypeScript types

### Neutral

- **File Structure**: Additional directory (`code_api/`)
- **Language Mix**: Python server + TypeScript execution
- **Documentation**: Need to document both APIs

## Implementation

### Core Components

1. **Canvas API Client** (`client.ts`)
   ```typescript
   export async function canvasGet<T>(endpoint, params): Promise<T>
   export async function canvasPut<T>(endpoint, body): Promise<T>
   export async function fetchAllPaginated<T>(endpoint, params): Promise<T[]>
   ```

2. **Bulk Grading** (`grading/bulkGrade.ts`)
   ```typescript
   export interface BulkGradeInput {
     courseIdentifier: string | number;
     assignmentId: string | number;
     gradingFunction: (submission) => GradeResult | null;
     dryRun?: boolean;
     maxConcurrent?: number;
   }

   export async function bulkGrade(input: BulkGradeInput): Promise<BulkGradeResult>
   ```

3. **Discovery Tool** (`tools/discovery.py`)
   ```python
   @mcp.tool()
   async def search_canvas_tools(
       query: str = "",
       detail_level: str = "signatures"
   ) -> str:
       """Search available Canvas code API operations."""
   ```

### Usage Pattern

```typescript
// Claude discovers available tools
search_canvas_tools("grading", "signatures")

// Claude reads the bulkGrade function
search_canvas_tools("bulkGrade", "full")

// Claude writes execution code
import { bulkGrade } from './canvas/grading/bulkGrade';

await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    // Custom logic runs locally!
    const hasNotebook = submission.attachments?.find(f =>
      f.filename.endsWith('.ipynb')
    );

    if (!hasNotebook) return null; // Skip

    // Analyze notebook (happens locally, not in Claude's context)
    const analysis = analyzeJupyterNotebook(hasNotebook.url);

    return {
      points: analysis.hasErrors ? 0 : 100,
      rubricAssessment: { "_8027": { points: analysis.hasErrors ? 0 : 100 } },
      comment: analysis.hasErrors
        ? "Errors found. Please fix and resubmit."
        : "Great work! No errors detected."
    };
  },
  dryRun: true // Preview first!
});
```

### Concurrent Processing

```typescript
// Process in batches with rate limiting
const maxConcurrent = 5;
const rateLimitDelay = 200; // ms between batches

// Automatically handles:
// - Parallel processing (up to maxConcurrent)
// - Rate limiting
// - Error handling
// - Progress reporting
```

### Error Handling

```typescript
interface BulkGradeResult {
  total: number;
  graded: number;
  skipped: number;
  failed: number;
  failedResults: Array<{
    userId: number;
    error: string;
  }>;
}
```

## References

- Example: `examples/bulk_grading_example.md`
- Discovery tool docs: `tools/README.md#search_canvas_tools`
- Claude Code execution: https://www.anthropic.com/news/code-execution
- Related: [ADR-001: Modular Architecture](001-modular-architecture.md)

## Notes

### When to Use Each Approach

**Traditional MCP Tools**:
- Single queries ("Show me assignment details")
- Small datasets (<10 items)
- Interactive exploration
- Quick lookups

**Code Execution API**:
- Bulk operations (50+ items)
- Repetitive logic
- Large datasets
- Custom analysis

### Design Principles

1. **Environment Variables**: Use process.env for Canvas credentials
2. **Direct API Calls**: No dependency on Python MCP server
3. **Type Safety**: Full TypeScript types for Canvas API responses
4. **Retry Logic**: Exponential backoff for API failures
5. **Dry Run Mode**: Always preview before applying grades

### Real-World Impact

Educator feedback:
> "Grading 90 notebooks went from impossible (context limits) to 2 minutes. Game changer."

Token cost comparison:
- Traditional: $2.70 per grading session (1.35M tokens @ $2/M)
- Code execution: $0.007 per session (3.5K tokens)
- **Savings: 99.7%**

### Future Enhancements

- Add more bulk operations (discussions, messaging, analytics)
- Implement caching for repeated operations
- Add progress callbacks for long operations
- Support for custom Canvas plugins
- Integration with Canvas webhooks

This ADR represents a paradigm shift in how Canvas MCP handles bulk operations, making previously impossible tasks practical and cost-effective.

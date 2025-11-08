# Canvas MCP API Reference

Complete API reference for Canvas MCP server tools and resources.

## Table of Contents

- [MCP Tools](#mcp-tools)
- [Code Execution API](#code-execution-api)
- [Core Utilities](#core-utilities)
- [Type Definitions](#type-definitions)

---

## MCP Tools

For complete tool documentation including parameters, examples, and usage, see:
- **[Tools README](../tools/README.md)** - Comprehensive tool documentation

### Quick Reference

| Category | Tools | Description |
|----------|-------|-------------|
| **Student Tools** | `get_my_upcoming_assignments`, `get_my_todo_items`, `get_my_submission_status`, `get_my_course_grades`, `get_my_peer_reviews_todo` | Personal academic tracking |
| **Course Tools** | `list_courses`, `get_course_details`, `list_pages`, `get_page_content` | Course information and content |
| **Assignment Tools** | `list_assignments`, `get_assignment_details`, `list_submissions`, `get_assignment_analytics` | Assignment management |
| **Discussion Tools** | `list_discussion_topics`, `list_discussion_entries`, `post_discussion_entry`, `reply_to_discussion_entry` | Discussion forums |
| **Rubric Tools** | `create_rubric`, `get_rubric_details`, `associate_rubric`, `grade_submission_with_rubric` | Rubric management and grading |
| **Peer Review Tools** | `list_peer_reviews`, `get_peer_review_completion_analytics`, `get_peer_review_comments`, `analyze_peer_review_quality` | Peer review workflows |
| **Messaging Tools** | `send_conversation`, `send_peer_review_reminders`, `create_announcement` | Communication |
| **Discovery Tools** | `search_canvas_tools` | Find code execution API operations |

---

## Code Execution API

TypeScript API for bulk operations with token-efficient execution.

### Installation in Code Execution Environment

```typescript
// Environment variables automatically available
const CANVAS_API_URL = process.env.CANVAS_API_URL;
const CANVAS_API_TOKEN = process.env.CANVAS_API_TOKEN;
```

### Client Functions

#### `canvasGet<T>(endpoint, params?)`
Make GET request to Canvas API.

```typescript
import { canvasGet } from './client';

const course = await canvasGet<Course>('/courses/12345');
```

#### `canvasPost<T>(endpoint, body)`
Make POST request to Canvas API.

```typescript
import { canvasPost } from './client';

const result = await canvasPost('/courses/12345/assignments', {
  assignment: { name: "New Assignment", points_possible: 100 }
});
```

#### `canvasPut<T>(endpoint, body)`
Make PUT request to Canvas API.

```typescript
import { canvasPut } from './client';

const updated = await canvasPut('/courses/12345/assignments/67890', {
  assignment: { name: "Updated Name" }
});
```

#### `fetchAllPaginated<T>(endpoint, params?)`
Fetch all paginated results automatically.

```typescript
import { fetchAllPaginated } from './client';

const allStudents = await fetchAllPaginated<User>(
  '/courses/12345/users',
  { enrollment_type: 'student' }
);
```

### Grading Operations

#### `bulkGrade(input: BulkGradeInput)`
Grade multiple submissions efficiently.

**Type Definition:**
```typescript
interface BulkGradeInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
  gradingFunction: (submission: Submission) => GradeResult | null | Promise<GradeResult | null>;
  dryRun?: boolean;
  maxConcurrent?: number;
  rateLimitDelay?: number;
}

interface GradeResult {
  points: number;
  rubricAssessment: Record<string, { points: number; ratingId?: string; comments?: string }>;
  comment: string;
}

interface BulkGradeResult {
  total: number;
  graded: number;
  skipped: number;
  failed: number;
  failedResults: Array<{ userId: number; error: string }>;
}
```

**Example:**
```typescript
import { bulkGrade } from './canvas/grading/bulkGrade';

const result = await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    if (!submission.submitted_at) return null;

    return {
      points: 100,
      rubricAssessment: { "_8027": { points: 100 } },
      comment: "Great work!"
    };
  },
  dryRun: true
});
```

#### `gradeWithRubric(input: GradeWithRubricInput)`
Grade a single submission with rubric.

**Type Definition:**
```typescript
interface GradeWithRubricInput {
  courseIdentifier: string | number;
  assignmentId: string | number;
  userId: number;
  rubricAssessment: Record<string, { points: number; ratingId?: string; comments?: string }>;
  comment?: string;
}
```

### Discussion Operations

#### `bulkGradeDiscussion(input: BulkGradeDiscussionInput)`
Grade discussion participation with peer review requirements.

**Type Definition:**
```typescript
interface BulkGradeDiscussionInput {
  courseIdentifier: string | number;
  topicId: string | number;
  assignmentId?: string | number;
  criteria: {
    initialPostPoints: number;
    peerReviewPointsEach: number;
    requiredPeerReviews: number;
    maxPeerReviewPoints: number;
  };
  latePenalty?: {
    deadline: string; // ISO date
    penaltyPercentage: number;
  };
  dryRun?: boolean;
}
```

**Example:**
```typescript
import { bulkGradeDiscussion } from './canvas/discussions/bulkGradeDiscussion';

const result = await bulkGradeDiscussion({
  courseIdentifier: "60365",
  topicId: "990001",
  assignmentId: "1234567",
  criteria: {
    initialPostPoints: 10,
    peerReviewPointsEach: 5,
    requiredPeerReviews: 2,
    maxPeerReviewPoints: 10
  },
  dryRun: false
});
```

---

## Core Utilities

### Configuration

#### `get_config()`
Get current configuration with validation.

```python
from canvas_mcp.core.config import get_config

config = get_config()
print(config.api_url)  # Canvas API URL
print(config.api_token)  # Canvas API token (masked)
print(config.enable_anonymization)  # Privacy setting
```

### Caching

#### `get_course_id(course_identifier: str | int) -> str | None`
Convert course code or identifier to Canvas course ID.

```python
from canvas_mcp.core.cache import get_course_id

# From course code
course_id = await get_course_id("badm_350_120251_246794")  # "60366"

# From numeric ID
course_id = await get_course_id(60366)  # "60366"

# From SIS ID
course_id = await get_course_id("sis_course_id:BADM_350")  # "sis_course_id:BADM_350"
```

#### `get_course_code(course_id: str) -> str | None`
Convert course ID to human-readable course code.

```python
from canvas_mcp.core.cache import get_course_code

course_code = await get_course_code("60366")  # "badm_350_120251_246794"
```

#### `refresh_course_cache() -> bool`
Manually refresh course cache.

```python
from canvas_mcp.core.cache import refresh_course_cache

success = await refresh_course_cache()
```

### Validation

#### `@validate_params`
Decorator for automatic parameter validation.

```python
from canvas_mcp.core.validation import validate_params

@validate_params
async def my_tool(course_id: str | int, active: bool = True) -> str:
    # Parameters automatically validated and converted
    pass
```

#### `validate_parameter(name: str, value: Any, expected_type: Any) -> Any`
Validate single parameter.

```python
from canvas_mcp.core.validation import validate_parameter

validated = validate_parameter("course_id", "123", int)  # Returns 123 as int
```

### HTTP Client

#### `make_canvas_request(method, endpoint, params?, data?)`
Make authenticated request to Canvas API.

```python
from canvas_mcp.core.client import make_canvas_request

response = await make_canvas_request("get", "/courses/12345")
if "error" not in response:
    print(response["name"])
```

#### `fetch_all_paginated_results(endpoint, params?)`
Fetch all pages automatically.

```python
from canvas_mcp.core.client import fetch_all_paginated_results

all_students = await fetch_all_paginated_results(
    "/courses/12345/users",
    {"enrollment_type": "student", "per_page": 100}
)
```

### Date Handling

#### `format_date(date_str: str | None) -> str | None`
Convert Canvas date to ISO 8601 format.

```python
from canvas_mcp.core.dates import format_date

iso_date = format_date("2024-11-08T15:30:00Z")  # "2024-11-08T15:30:00Z"
```

#### `parse_date(date_str: str) -> datetime`
Parse ISO 8601 date string.

```python
from canvas_mcp.core.dates import parse_date

dt = parse_date("2024-11-08T15:30:00Z")  # datetime object
```

### Anonymization

#### `anonymize_response_data(data, data_type: str)`
Anonymize student data for FERPA compliance.

```python
from canvas_mcp.core.anonymization import anonymize_response_data

# Anonymize user data
anonymized = anonymize_response_data(user_data, "users")
# Names: "John Smith" → "Student_abc123"
# Emails: "john@uni.edu" → "student_abc123@masked"
```

---

## Type Definitions

### Common Canvas Types

#### Course
```typescript
interface Course {
  id: number;
  name: string;
  course_code: string;
  workflow_state: "available" | "completed" | "deleted";
  start_at?: string;
  end_at?: string;
  enrollment_term_id: number;
}
```

#### Assignment
```typescript
interface Assignment {
  id: number;
  name: string;
  description?: string;
  due_at?: string;
  points_possible: number;
  grading_type: "pass_fail" | "percent" | "letter_grade" | "points";
  submission_types: string[];
  has_submitted_submissions: boolean;
}
```

#### Submission
```typescript
interface Submission {
  id: number;
  assignment_id: number;
  user_id: number;
  submitted_at?: string;
  score?: number;
  grade?: string;
  workflow_state: "submitted" | "unsubmitted" | "graded" | "pending_review";
  late: boolean;
  missing: boolean;
  attachments?: Attachment[];
}
```

#### User
```typescript
interface User {
  id: number;
  name: string;
  email?: string;
  login_id?: string;
  sis_user_id?: string;
}
```

#### Discussion Topic
```typescript
interface DiscussionTopic {
  id: number;
  title: string;
  message?: string;
  posted_at?: string;
  discussion_type: "side_comment" | "threaded";
  assignment_id?: number;
  user_name?: string;
}
```

#### Discussion Entry
```typescript
interface DiscussionEntry {
  id: number;
  user_id: number;
  parent_id?: number;
  created_at: string;
  updated_at: string;
  message: string;
  user_name?: string;
  rating_sum?: number;
}
```

---

## Error Handling

### MCP Tools
All MCP tools return JSON strings. Errors are returned as:

```json
{
  "error": "Error message describing what went wrong"
}
```

### Code Execution API
TypeScript functions throw errors:

```typescript
try {
  const result = await bulkGrade({ ... });
} catch (error) {
  console.error("Grading failed:", error.message);
}
```

---

## Rate Limiting

Canvas API has rate limits:
- **Requests**: ~3000 per hour per token
- **Burst**: Short burst of 100 requests allowed
- **Backoff**: Automatic exponential backoff on 429 errors

Canvas MCP handles rate limiting automatically:
- Request throttling
- Retry logic with backoff
- Concurrent request limits (configurable)

---

## Authentication

All API calls require Canvas API token:

```bash
# In .env file
CANVAS_API_TOKEN=your_token_here
CANVAS_API_URL=https://canvas.youruniversity.edu/api/v1
```

Token permissions required:
- **Students**: Read access to own data
- **Educators**: Instructor or TA role for course management

---

## Additional Resources

- **[Tools Documentation](../tools/README.md)** - Complete tool reference
- **[Student Guide](STUDENT_GUIDE.md)** - For students
- **[Educator Guide](EDUCATOR_GUIDE.md)** - For educators
- **[Development Guide](CLAUDE.md)** - For contributors
- **[Examples](../examples/)** - Workflow examples

---

## Getting Help

- **GitHub Issues**: [Report issues](https://github.com/vishalsachdev/canvas-mcp/issues)
- **Documentation**: Check guides and examples
- **Code Examples**: See `examples/` directory

Last updated: November 8, 2024

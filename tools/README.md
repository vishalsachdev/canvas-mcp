# Canvas MCP Tools Documentation

This document provides a comprehensive overview of all tools available in the Canvas MCP Server, organized by audience and functionality.

## Table of Contents

- [Student Tools](#student-tools)
- [Educator Tools](#educator-tools)
- [Shared Tools](#shared-tools-both-students--educators)
- [Developer Tools](#developer-tools)
- [Tool Usage Guidelines](#tool-usage-guidelines)

---

## Student Tools

These tools provide students with personal academic tracking and organization capabilities using Canvas API's "self" endpoints.

### Personal Organization

#### `get_my_upcoming_assignments`
Get your upcoming assignments across all enrolled courses.

**Parameters:**
- `days` (optional): Number of days to look ahead (default: 7)

**Example:**
```
"What assignments do I have due this week?"
"Show me what's due in the next 3 days"
```

**Returns:** List of assignments due within timeframe, sorted by due date, with submission status.

---

#### `get_my_todo_items`
Get your Canvas TODO list including assignments, quizzes, and discussions.

**Example:**
```
"Show me my Canvas TODO list"
"What do I need to do?"
```

**Returns:** All items requiring your attention with due dates and course information.

---

#### `get_my_submission_status`
Check your submission status across assignments.

**Parameters:**
- `course_identifier` (optional): Specific course code or ID to filter

**Example:**
```
"Have I submitted everything?"
"Show me my submission status for BADM 350"
"What haven't I turned in yet?"
```

**Returns:** Submitted and missing assignments, with overdue items flagged.

---

### Academic Performance

#### `get_my_course_grades`
View your current grades across all enrolled courses.

**Example:**
```
"What are my current grades?"
"Show me how I'm doing in all my courses"
```

**Returns:** Current grade, percentage, and enrollment status for each course.

---

### Peer Review Management

#### `get_my_peer_reviews_todo`
List peer reviews you need to complete.

**Parameters:**
- `course_identifier` (optional): Filter by specific course

**Example:**
```
"What peer reviews do I need to complete?"
"Show me my pending peer reviews for ENGL 101"
```

**Returns:** Incomplete peer reviews with assignment and course information.

---

## Educator Tools

These tools provide instructors and TAs with course management, grading, analytics, and communication capabilities.

### Assignment Management

#### `list_assignments`
List all assignments for a course.

**Parameters:**
- `course_identifier`: Course code (e.g., "badm_350_120251_246794") or ID

**Example:**
```
"Show me all assignments in BADM 350"
"List assignments for my Spring 2025 course"
```

---

#### `get_assignment_details`
Get detailed information about a specific assignment.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"Show me details for Assignment 3"
```

---

#### `list_submissions`
View student submissions for an assignment.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"Who has submitted Assignment 2 in BADM 350?"
"Show me submissions for the latest assignment"
```

**Note:** Student data is anonymized if `ENABLE_DATA_ANONYMIZATION=true` in educator's `.env` file.

---

#### `get_assignment_analytics`
Get comprehensive performance analytics for an assignment.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"Show me analytics for Assignment 3"
"What's the submission rate for the final project?"
```

**Returns:** Submission statistics, grade distribution, completion rates, and performance metrics.

---

### Grading & Rubrics

#### `create_rubric`
Create a new grading rubric.

**Parameters:**
- `course_identifier`: Course code or ID
- `title`: Rubric title
- `criteria`: JSON array of rubric criteria

**Example:**
```
"Create a rubric for the final project with criteria for content, organization, and citations"
```

---

#### `get_rubric_details`
View rubric criteria and point values.

**Parameters:**
- `course_identifier`: Course code or ID
- `rubric_id`: Rubric ID

**Example:**
```
"Show me the rubric for Assignment 4"
```

---

#### `associate_rubric`
Link a rubric to an assignment.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `rubric_id`: Rubric ID
- `use_for_grading`: Boolean (true/false)

---

#### `grade_submission_with_rubric`
Grade a student submission using a rubric.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `user_id`: Student ID
- `rubric_assessment`: JSON with criterion ratings

---

#### `bulk_grade_submissions`
Grade multiple submissions efficiently with concurrent processing. **Most efficient way for bulk grading!**

**IMPORTANT:** This tool provides significant token savings by processing submissions in batches without loading all data into context.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `grades`: Dictionary mapping user IDs to grade information
  ```json
  {
    "user_id": {
      "rubric_assessment": {...},  // Optional: rubric-based grading
      "grade": <number>,            // Optional: simple grade
      "comment": "<string>"         // Optional: feedback comment
    }
  }
  ```
- `dry_run` (optional): If true, analyze but don't submit grades (default: false)
- `max_concurrent` (optional): Maximum concurrent grading operations (default: 5)
- `rate_limit_delay` (optional): Delay between batches in seconds (default: 1.0)

**Example Usage - Rubric Grading:**
```
"Grade these 3 students using the rubric:
- User 9824: 100 points for criterion _8027 with comment 'Excellent work!'
- User 9825: 75 points for criterion _8027 with comment 'Good work'
- User 9826: 50 points for criterion _8027 with comment 'Needs improvement'"
```

**Example Usage - Simple Grading:**
```
"Grade these submissions with simple points:
- User 9824: 100 points, comment 'Perfect!'
- User 9825: 85 points, comment 'Very good'"
```

**Returns:** Summary of grading operation including total submissions, successfully graded, failed attempts, and any error details.

**Notes:**
- Supports both rubric-based grading and simple point-based grading
- Can mix and match grading styles for different students
- Automatically validates rubric configuration before grading
- Use `dry_run=true` to preview grades before applying
- For maximum token efficiency with custom grading logic, consider using the `execute_typescript` tool with `bulkGrade` from the code execution API

---

### Student Analytics

#### `get_student_analytics`
Multi-dimensional student performance analysis.

**Parameters:**
- `course_identifier`: Course code or ID
- `student_id` (optional): Specific student or all students

**Example:**
```
"Show me student performance in BADM 350"
"Analyze Student_abc123's progress"
```

**Returns:** Assignment completion, grade trends, participation, and risk indicators.

---

### Peer Review Management

#### `list_peer_reviews`
List all peer review assignments.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"Show me peer review assignments for Assignment 2"
```

---

#### `get_peer_review_completion_analytics`
Analyze peer review completion rates.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"How many students completed peer reviews for Assignment 2?"
"Show me peer review completion statistics"
```

**Returns:** Completion rates, incomplete reviews, and student-level breakdown.

---

#### `get_peer_review_comments`
Extract actual peer review comment text and metadata.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"Show me peer review comments for Assignment 3"
```

---

#### `analyze_peer_review_quality`
Comprehensive quality analysis of peer review comments.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"Analyze the quality of peer reviews for Assignment 2"
```

**Returns:** Quality metrics including length, specificity, constructiveness, and patterns.

---

#### `identify_problematic_peer_reviews`
Flag low-quality peer reviews needing attention.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID

**Example:**
```
"Which peer reviews need improvement?"
```

---

#### `assign_peer_review`
Manually assign a peer review.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `reviewer_id`: Student who will review
- `reviewee_id`: Student being reviewed

---

### Communication & Messaging

#### `send_conversation`
Send messages to students.

**Parameters:**
- `course_identifier`: Course code or ID
- `recipients`: User IDs (array)
- `subject`: Message subject
- `body`: Message content

**Example:**
```
"Message students who haven't submitted Assignment 3"
```

---

#### `send_peer_review_reminders`
Automated peer review reminder workflow.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `user_ids`: Students to remind (array)
- `custom_message` (optional): Custom message template

**Example:**
```
"Send reminders to students who haven't completed peer reviews"
```

---

#### `create_announcement`
Post course announcements.

**Parameters:**
- `course_identifier`: Course code or ID
- `title`: Announcement title
- `message`: Announcement content

**Example:**
```
"Create an announcement about tomorrow's exam"
```

---

### Discussion Management

#### `create_discussion_topic`
Start a new discussion forum.

**Parameters:**
- `course_identifier`: Course code or ID
- `title`: Discussion title
- `message`: Initial post content

---

#### `reply_to_discussion_entry`
Respond to student discussion posts.

**Parameters:**
- `course_identifier`: Course code or ID
- `topic_id`: Discussion topic ID
- `entry_id`: Specific post ID
- `message`: Your response

**Example:**
```
"Reply to John's post in the Week 5 discussion"
```

---

## Shared Tools (Both Students & Educators)

These tools work for both audiences, providing access to course content and information.

### Course Management

#### `list_courses`
List all enrolled courses.

**Example:**
```
"Show me my courses"
"What courses am I enrolled in?"
```

---

#### `get_course_details`
Get detailed course information including syllabus.

**Parameters:**
- `course_identifier`: Course code or ID

**Example:**
```
"Show me the syllabus for BADM 350"
"What's the course description for my Marketing class?"
```

---

### Content Access

#### `list_pages`
List pages in a course.

**Parameters:**
- `course_identifier`: Course code or ID
- `sort` (optional): Sort by title, created_at, or updated_at
- `published` (optional): Filter by published status

**Example:**
```
"Show me all pages in BADM 350"
"List published pages for my course"
```

---

#### `get_page_content`
Read the full content of a course page.

**Parameters:**
- `course_identifier`: Course code or ID
- `page_url_or_id`: Page URL or ID

**Example:**
```
"Show me the Week 1 Overview page"
"Read the Course Policies page for HIST 202"
```

---

#### `get_page_details`
Get detailed page metadata.

**Parameters:**
- `course_identifier`: Course code or ID
- `page_url_or_id`: Page URL or ID

---

### Announcements

#### `list_announcements`
View course announcements.

**Parameters:**
- `course_identifier`: Course code or ID

**Example:**
```
"Show me recent announcements"
"What are the latest announcements in BADM 350?"
```

---

### Discussions

#### `list_discussion_topics`
View discussion forums in a course.

**Parameters:**
- `course_identifier`: Course code or ID
- `only_announcements` (optional): Filter for announcements only

**Example:**
```
"What discussions are active in my course?"
"Show me discussion topics for ENGL 101"
```

---

#### `get_discussion_topic_details`
Get details about a specific discussion.

**Parameters:**
- `course_identifier`: Course code or ID
- `topic_id`: Discussion topic ID

---

#### `list_discussion_entries`
View posts in a discussion.

**Parameters:**
- `course_identifier`: Course code or ID
- `topic_id`: Discussion topic ID

**Example:**
```
"Show me posts in the Week 5 discussion"
```

---

#### `get_discussion_entry_details`
Read a specific discussion post.

**Parameters:**
- `course_identifier`: Course code or ID
- `topic_id`: Discussion topic ID
- `entry_id`: Post ID

**Example:**
```
"Show me the first post in the introduction discussion"
```

---

#### `post_discussion_entry`
Create a new discussion post.

**Parameters:**
- `course_identifier`: Course code or ID
- `topic_id`: Discussion topic ID
- `message`: Post content

---

## Developer Tools

These tools help developers discover, explore, and execute Canvas code execution API operations.

### Tool Discovery

#### `search_canvas_tools`
Search and discover available Canvas code execution API operations by keyword.

**Parameters:**
- `query` (optional): Search term to filter tools. Empty string returns all tools. Examples: "grading", "assignment", "discussion", "bulk"
- `detail_level` (optional): How much information to return. Default: "signatures"
  - `"names"`: Just file paths (most efficient for quick lookups)
  - `"signatures"`: File paths + function signatures + descriptions (recommended)
  - `"full"`: Complete file contents (use sparingly for detailed inspection)

**Example:**
```
"Search for grading tools in the code API"
"What bulk operations are available?"
"Show me all code API tools"
"Find discussion-related operations"
```

**Returns:** JSON with query, detail_level, count, and array of matching tools.

**Usage Tips:**
- Use empty query (`""`) to list all available tools
- Use `"signatures"` detail level for most tasks (default)
- Use `"names"` when you just need a quick overview
- Use `"full"` only when you need to see complete implementation details

**Example Direct Usage:**
```typescript
// Search for grading-related tools with signatures
search_canvas_tools("grading", "signatures")

// List all available tools (names only)
search_canvas_tools("", "names")

// Get full implementation details for bulk operations
search_canvas_tools("bulk", "full")
```

---

#### `list_code_api_modules`
List all available TypeScript modules in the code execution API.

**Parameters:** None

**Example:**
```
"What TypeScript modules are available?"
"List all code API modules"
"Show me the available code execution operations"
```

**Returns:** Formatted list of all TypeScript files organized by category (grading, assignments, courses, discussions, etc.) with import paths.

**Usage Tips:**
- Use this for a quick overview of all available operations
- Results show the exact import paths to use in `execute_typescript`
- Organized by category for easy navigation

---

### Code Execution

#### `execute_typescript`
Execute TypeScript code in a Node.js environment with access to Canvas API credentials.

**IMPORTANT:** This tool enables **99.7% token savings** for bulk operations by executing code locally rather than loading all data into Claude's context!

**Parameters:**
- `code`: TypeScript code to execute. Can import from './canvas/*' modules.
- `timeout` (optional): Maximum execution time in seconds (default: 120)

**Example:**
```
"Grade all 90 Jupyter notebook submissions using bulk grading"
"Send reminders to all students who haven't submitted"
"Analyze discussion participation across all students"
```

**Example Code:**
```typescript
import { bulkGrade } from './canvas/grading/bulkGrade.js';

await bulkGrade({
  courseIdentifier: "60366",
  assignmentId: "123",
  gradingFunction: (submission) => {
    // This runs locally - no token cost!
    const notebook = submission.attachments?.find(
      f => f.filename.endsWith('.ipynb')
    );

    if (!notebook) return null;

    return {
      points: 100,
      rubricAssessment: { "_8027": { points: 100 } },
      comment: "Great work!"
    };
  }
});
```

**Returns:** Combined stdout and stderr from execution, or error message if failed.

**Security:**
- Code runs in a temporary file that is deleted after execution
- Inherits Canvas API credentials from server environment
- Timeout enforced to prevent runaway processes

**Token Efficiency:**
- **Traditional approach**: Loads all submissions into context (1.35M tokens for 90 submissions)
- **Code execution approach**: Only summary results return (3.5K tokens = 99.7% savings!)

**Usage Tips:**
- First use `search_canvas_tools` or `list_code_api_modules` to discover available operations
- Import operations from './canvas/*' paths (e.g., './canvas/grading/bulkGrade.js')
- Processing happens locally - only results flow back to Claude's context
- Best for bulk operations, large datasets, and complex analysis
- Traditional tools still best for simple queries and small datasets

---

## Tool Usage Guidelines

### For Students

1. **Be specific**: Use course codes when possible (e.g., "BADM 350" instead of "my business class")
2. **Combine queries**: "Show me my grades and what's due this week"
3. **Check regularly**: Use for daily planning and weekly organization
4. **No setup needed**: Student tools access only your data - no special configuration required

### For Educators

1. **Enable anonymization**: Set `ENABLE_DATA_ANONYMIZATION=true` in `.env` for FERPA compliance
2. **Use course codes**: Be specific about which course (e.g., "badm_350_120251_246794")
3. **Leverage automation**: Use messaging and reminder tools for routine communications
4. **Combine analytics**: Request multiple analytics in one query for comprehensive insights
5. **Protect mapping files**: Keep `local_maps/` folder secure - never commit to version control

### General Best Practices

- **Ask follow-up questions**: Claude remembers context within a conversation
- **Request summaries**: "Summarize..." for quick overviews
- **Be conversational**: Natural language works better than rigid commands
- **Check tool output**: Review the data Claude retrieves before taking action

## Need Help?

- **Student Guide**: [STUDENT_GUIDE.md](../docs/STUDENT_GUIDE.md)
- **Educator Guide**: [EDUCATOR_GUIDE.md](../docs/EDUCATOR_GUIDE.md)
- **Main README**: [README.md](../README.md)
- **Development Guide**: [CLAUDE.md](../docs/CLAUDE.md)
- **GitHub Issues**: [Report issues](https://github.com/vishalsachdev/canvas-mcp/issues)

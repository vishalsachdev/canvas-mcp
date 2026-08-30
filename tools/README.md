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

### Self-Identity

Available under **every** role profile (student, educator, all) — these describe only the authenticated caller, so they need no roster permission.

#### `get_my_profile`
Get your own Canvas identity.

**Parameters:** none

**Example:**
```
"Who am I in Canvas?"
"What's my Canvas user ID?"
```

**Returns:** Your Canvas user ID, name, and login ID. `primary_email` and `sis_user_id` are deliberately omitted — neither is needed to identify you to other tools, and both are needlessly sensitive in a transcript.

---

#### `get_my_enrollments`
List the courses **you** are enrolled in, with your role in each.

**Parameters:**
- `include_concluded` (optional): Also include concluded/completed courses (default `false` = active only)

**Example:**
```
"What courses am I in?"
"Am I a student or a TA in BADM 350?"
```

**Returns:** Course code, name, ID, and your role(s) per course. Reports **all** roles when you hold more than one enrollment in a course (e.g. TA and student).

Use this — not [`check_enrollment`](#check_enrollment) — for any question about your own enrollment. `check_enrollment` reads the course roster, which requires roster-admin rights your token probably does not have.

---

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

#### `get_my_submission`
View your own submission for a single assignment, including how many attempts
you have used and any instructor comments.

**Parameters:**
- `course_identifier` (required): Course code or Canvas ID
- `assignment_id` (required): Canvas assignment ID

**Example:**
```
"Did my essay for BADM 350 go through?"
"How many attempts do I have left on assignment 4821?"
```

**Returns:** Status, submitted time, due and lock dates, attempts used vs allowed,
grade if any, and submission comments.

---

### Student Write Tools

> **Off by default.** These tools only exist if the server operator enabled them
> via `STUDENT_WRITE_TOOLS`, and an instructor can additionally block them in
> their own course. See [Student write configuration](#student-write-configuration).

#### `submit_assignment`
Submit one of your own assignments. **Consumes an attempt.**

This is a deliberate two-call flow. The first call previews and submits nothing;
the second call, carrying the token from the preview, actually submits.

**Parameters:**
- `course_identifier` (required): Course code or Canvas ID
- `assignment_id` (required): Canvas assignment ID
- `submission_type` (required): `online_text_entry`, `online_url`, or `online_upload`
- `body` (for text entry): The content to submit
- `url` (for URL submissions): The URL
- `file_paths` (for uploads, local servers only): Local file paths, any file type
- `file_contents` (for uploads, hosted servers): `[{"name": ..., "content_base64": ...}]`
- `comment` (optional): A comment to include with the submission
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Submit my essay draft to assignment 4821"        → returns a preview
"Yes, submit it"                                   → confirms with the token
```

**Returns:** On the first call, a preview showing the assignment, due and lock
dates, attempts remaining, and exactly what would be sent. On the second, the
submission result including whether Canvas marked it late.

**Files are sent as raw bytes.** Images and PDFs are uploaded as-is, never
converted to text or run through OCR. There is no global list of permitted
extensions: whatever the assignment's own `allowed_extensions` permits is
accepted, so `.heic` photos and `.tex` sources work wherever the instructor
allows them. Limits are 100 MB per file, 100 MB and 20 files per submission.

**Not supported:** group assignments (submitting would bind your whole group) and
quizzes (a separate institutional decision).

---

#### `comment_on_my_submission`
Add a comment to your own submission.

**Parameters:**
- `course_identifier` (required): Course code or Canvas ID
- `assignment_id` (required): Canvas assignment ID
- `comment` (required): The comment text

**Example:**
```
"Add a note to my submission explaining the late turn-in"
```

---

#### `mark_module_item_done`
Mark a module item complete for yourself, for modules using "mark as done"
requirements.

**Parameters:**
- `course_identifier` (required): Course code or Canvas ID
- `module_id` (required): Canvas module ID
- `item_id` (required): Canvas module item ID

---

#### Student write configuration

Two independent gates, and the second can only ever narrow the first.

**1. Operator ceiling — `STUDENT_WRITE_TOOLS`**

Comma- or space-separated tool names. Empty (the default) means no student write
tool is registered at all.

```bash
STUDENT_WRITE_TOOLS=submit_assignment,comment_on_my_submission
```

**2. Per-course instructor policy**

An instructor states their course's stance in the course syllabus (the default
carrier, because students cannot edit it):

```
agent_writes: deny
```

or, to allow with limits:

```
agent_writes: allow
allow_tools: submit_assignment
note: Allowed for the weekly labs. Ask me before using it on the final project.
```

`COURSE_AGENT_POLICY_DEFAULT` decides what happens in a course that says nothing:
`deny` (the default, instructors opt in) or `allow` (instructors opt out).

The syllabus is the only supported carrier, and that is deliberate. Students can
read it but cannot edit it, so instructor authorship is structural rather than
assumed. A course-page carrier was built and then removed: a page's
`editing_roles` tells you who may edit it *now*, not who wrote it, so a student
who can create pages could author the policy and set it teacher-only in the same
breath. Authorship cannot be established from a student's own token.

Anything ambiguous denies: a malformed policy, contradictory directives (an
`agent_writes: deny` appended under an earlier `allow`), a failed read, or a
course this caller cannot see.

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
- `course_identifier` (optional): Filter by specific course. Required if `assignment_identifier` is given.
- `assignment_identifier` (optional): Check a specific assignment directly, bypassing the per-course discovery scan. Use this if you know which assignment has your peer review but the general scan doesn't find it.

**Example:**
```
"What peer reviews do I need to complete?"
"Show me my pending peer reviews for ENGL 101"
"Do I have a peer review to do for assignment 4821 in ENGL 101?"
```

**Returns:** Incomplete peer reviews with assignment and course information, each
labeled with its discovery source (`Assignment scan` or `Planner feed`). The
per-course discovery scan (`Assignment scan`) only checks assignments whose
listing carries `peer_reviews: true`; as of #275 it is supplemented with a
Planner API query (`Planner feed`) that mirrors how Canvas's own student
"To Do" list finds pending peer reviews, since the two sources can disagree
on some instances. Results from both are merged and deduplicated.

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

#### `create_assignment`
Create a new assignment in a course.

**Parameters:**
- `course_identifier`: Course code or ID
- `name`: Assignment name/title (required)
- `description`: HTML content for the assignment body
- `submission_types`: Comma-separated list of allowed types:
  - `online_text_entry`, `online_url`, `online_upload`
  - `discussion_topic`, `none`, `on_paper`, `external_tool`
- `due_at`: Due date in ISO 8601 format (e.g., "2026-01-26T23:59:00Z")
- `unlock_at`: When assignment becomes available (ISO 8601)
- `lock_at`: When assignment locks (ISO 8601)
- `points_possible`: Maximum points
- `grading_type`: One of `points`, `letter_grade`, `pass_fail`, `percent`, `not_graded`
- `published`: Whether to publish immediately (default: `false` for safety)
- `assignment_group_id`: ID of assignment group to place in
- `peer_reviews`: Enable peer reviews (boolean)
- `automatic_peer_reviews`: Auto-assign peer reviews (boolean)
- `allowed_extensions`: Comma-separated file extensions for uploads (e.g., "pdf,docx,txt")

**Example:**
```
"Create an assignment called 'Week 1 Discussion' worth 10 points, due Jan 26, with online_text_entry submission"
"Add a new essay assignment with PDF and DOCX uploads allowed"
```

**Note:** Assignments are created unpublished by default for safety. Set `published=true` to publish immediately.

---

#### `update_assignment`
Update an existing assignment in a course.

**Parameters:**
- `course_identifier`: Course code or ID (required)
- `assignment_id`: ID of the assignment to update (required)
- `name`: New assignment name/title
- `description`: New HTML content for the assignment body
- `submission_types`: Comma-separated list of allowed types
- `due_at`: New due date in ISO 8601 format
- `unlock_at`: New availability date (ISO 8601)
- `lock_at`: New lock date (ISO 8601)
- `points_possible`: New maximum points
- `grading_type`: One of `points`, `letter_grade`, `pass_fail`, `percent`, `not_graded`
- `published`: Whether the assignment should be published
- `assignment_group_id`: ID of assignment group to move to
- `peer_reviews`: Enable/disable peer reviews
- `automatic_peer_reviews`: Enable/disable auto-assign peer reviews
- `allowed_extensions`: Comma-separated file extensions for uploads

**Example:**
```
"Change the due date for Assignment 3 to Feb 15 at midnight"
"Update Quiz 1 to be worth 50 points instead of 25"
"Publish Assignment 4"
```

**Note:** Only fields you specify will be updated. Omitted fields remain unchanged.

---

#### `delete_assignment_with_confirmation`
Delete an assignment. **Permanent, and it takes every submission and grade with it.** Two-step: preview first, then confirm with the token.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID to delete
- `require_name_match` (optional): Only delete if the assignment name matches this string exactly
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Delete the duplicate 'Homework 1' assignment, but show me first"
```

**Returns:** Preview with name, due date, points and whether submissions exist (no token), then the deletion result.

---

### Content Migration

#### `create_content_migration`
Preview and confirm a request to copy the full contents of one course into another.

**Signature:**
```python
create_content_migration(
    target_course_identifier: str | int,
    source_course_identifier: str | int,
    old_start_date: str | None = None,
    old_end_date: str | None = None,
    new_start_date: str | None = None,
    new_end_date: str | None = None,
    confirmation_token: str | None = None,
) -> dict[str, Any]
```

The first call never starts a migration. It resolves both courses, rejects a
source and target that resolve to the same Canvas course, validates the optional
date shift, and returns a preview with counts of the target's current
assignments, pages, modules, discussions, and files where those lists are
readable. These counts describe occupancy only; they are not a content-level
diff of likely collisions. A non-empty target receives an explicit duplicate-risk
warning.

Date shifting accepts either none or all four date fields. Both the old and new
start dates must be earlier than their matching end dates. This tool does not
expose `dry_run` or selective imports.

**Preview and confirmation example:**
```python
preview = create_content_migration(
    target_course_identifier="BADM_350_FALL_2026",
    source_course_identifier="BADM_350_FALL_2025",
    old_start_date="2025-08-25",
    old_end_date="2025-12-19",
    new_start_date="2026-08-24",
    new_end_date="2026-12-18",
)

# Show the complete preview to the educator and obtain explicit confirmation.
started = create_content_migration(
    target_course_identifier="BADM_350_FALL_2026",
    source_course_identifier="BADM_350_FALL_2025",
    old_start_date="2025-08-25",
    old_end_date="2025-12-19",
    new_start_date="2026-08-24",
    new_end_date="2026-12-18",
    confirmation_token=preview["confirmation_token"],
)
```

The token is short-lived, single-use, and bound to the canonical source and
target plus the exact normalized date options. Changed arguments invalidate and
burn it. A returned migration ID confirms only that Canvas created the migration
record; it does not mean the migration completed or that content was copied.
If the POST fails ambiguously or the response has no migration ID, the result
sets `migration_start_unconfirmed=true`. Check the target course's migration
history before retrying, because a timeout can occur after the request reached
Canvas.

---

#### `get_content_migration_status`
Read one migration and one progress snapshot.

**Signature:**
```python
get_content_migration_status(
    course_identifier: str | int,
    migration_id: str | int,
) -> dict[str, Any]
```

Each invocation performs exactly one progress read. It does not sleep, loop, or
run a background job. For `queued` or `running`, the result sets
`terminal=false`, `poll_again=true`, and provides concrete arguments for the
next call. Repeat only when the caller is ready to poll again:

```python
status = get_content_migration_status(
    course_identifier=started["next_action"]["arguments"]["course_identifier"],
    migration_id=started["migration_id"],
)

if status.get("poll_again"):
    status = get_content_migration_status(**status["next_action"]["arguments"])
```

When progress is terminal, the tool reads all paginated migration issues:

- `completed` with no issues is a clean completion.
- `completed_with_issues` includes every returned issue, sets
  `requires_review=true`, and uses a warning rather than an error.
- `failed` is terminal and returns a top-level error plus any readable issues.
- If issues cannot be read, `issues_checked=false` is returned with the progress
  snapshot; the tool never substitutes an empty issue list.
- A missing or unknown progress state is an error and is never treated as
  completion.

Canvas-authored progress messages and issue descriptions or administrator error
details are provenance-fenced as untrusted data in the tool output.

---

### Grading & Rubrics

#### `create_rubric`
Create a new rubric in a course, optionally associating it with an assignment.

Uses bracket-notation form-data encoding required by the Canvas rubric API.

**Parameters:**
- `course_identifier`: Course code or ID
- `title`: Rubric title
- `criteria`: JSON string defining criteria (see example below)
- `assignment_id` (optional): Assignment ID to immediately associate the rubric with
- `use_for_grading` (optional): Use rubric for grade calculation when associating (default: false)
- `reusable` (optional): Make rubric reusable across courses (default: false)
- `free_form_criterion_comments` (optional): Allow free-form comments per criterion (default: false)

**Criteria JSON format:**
```json
{
  "c1": {
    "description": "Content Quality",
    "points": 10,
    "ratings": [
      {"description": "Excellent", "points": 10},
      {"description": "Satisfactory", "points": 7},
      {"description": "Needs Work", "points": 3}
    ]
  },
  "c2": {
    "description": "Grammar",
    "points": 5,
    "ratings": [
      {"description": "No errors", "points": 5},
      {"description": "Minor errors", "points": 3}
    ]
  }
}
```

**Example:**
```
"Create a rubric called 'Essay Rubric' in CS101 with two criteria: Content (10 pts) and Grammar (5 pts)"
"Create a rubric and associate it with Assignment 456 for grading"
```

---

#### `create_rubric_from_csv`
Create one or more rubrics in a course from a CSV string using Canvas's native rubric CSV import endpoint. Uploads the CSV, then polls the import job until it reaches a terminal state.

**Parameters:**
- `course_identifier`: Course code or ID
- `csv_content`: The CSV content as a string. **A `Rubric Name` column is required** — Canvas rejects the import without it.

**Required CSV format:**

```csv
Rubric Name,Criteria Name,Criteria Description,Criteria Enable Range,Rating Name,Rating Description,Rating Points,Rating Name,Rating Description,Rating Points
Essay Rubric,Clarity,Is the argument clear,false,Excellent,Very clear,10,Poor,Unclear,2
```

Repeat the `Rating Name,Rating Description,Rating Points` triple for each rating level. Use a distinct `Rubric Name` per row to create multiple rubrics in one import.

**Two behaviours worth knowing:**

- **Imported rubrics land in Canvas's `Draft` state and are NOT returned by `list_rubrics`.** They *are* visible in the course's Rubrics page. Do not treat an empty `list_rubrics` result as evidence the import failed.
- Canvas returns `succeeded_with_errors` when the file parses but some rows are rejected. That is a terminal state, not a transient one, and it can mean **zero** rubrics were created — check the reported error messages rather than assuming partial success.

**Example:**
```
"Create a rubric in CS101 from this CSV: Rubric Name,Criteria Name,Criteria Description,Criteria Enable Range,Rating Name,Rating Description,Rating Points / Essay Rubric,Clarity,Is it clear,false,Excellent,Very clear,10"
```

**Note:** CSV-imported rubrics appear in Canvas as **Draft** items. They may not appear immediately in `list_rubrics`; verify imports in the course Rubrics UI.

---

#### `list_rubrics`
List all rubrics in a course.

**Parameters:**
- `course_identifier`: Course code or ID

**Example:**
```
"Show me all rubrics in CS101"
```

---

#### `get_rubric`
View rubric criteria and point values. Accepts either a rubric ID or an assignment ID.

**Parameters:**
- `course_identifier`: Course code or ID
- `rubric_id` (optional): Rubric ID
- `assignment_id` (optional): Assignment ID (fetches the rubric attached to this assignment)

**Example:**
```
"Show me the rubric for Assignment 4"
"What rubric criteria are in rubric 789?"
```

---

#### `get_rubric_assessment`
View the rubric assessment submitted for a student's submission.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `student_id`: Student user ID

---

#### `associate_rubric`
Link a rubric to an assignment.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `rubric_id`: Rubric ID
- `use_for_grading`: Boolean (true/false)

---

#### `grade_with_rubric`
Grade a student submission using a rubric.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `user_id`: Student ID
- `rubric_assessment`: JSON with criterion ratings

---

#### `bulk_grade_submissions`
Grade multiple submissions concurrently.

**Context use:** Process bulk operations locally without loading every item into the model's context. Actual savings depend on the workload and selected output.

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

**Example Usage - Simple Grading (no comments):**
```
"Grade these submissions with simple points:
- User 9824: 100 points
- User 9825: 85 points"
```

> **Comments are opt-in.** `comment` is student-visible in SpeedGrader, it
> **appends** on every call rather than replacing, and it cannot be un-sent.
> Ask for one only when you want written feedback — "assign grade 8" means the
> grade alone. A comment that only restates the grade or notes that grading
> happened is worse than none.

**Returns:** Summary of grading operation including total submissions, successfully graded, failed attempts, and any error details.

**Notes:**
- Supports both rubric-based grading and simple point-based grading
- `dry_run: true` previews the grade **and** any comment that would be posted
- Can mix and match grading styles for different students
- Automatically validates rubric configuration before grading
- Use `dry_run=true` to preview grades before applying
- For custom bulk grading logic that can return selected output, consider `execute_typescript` with `bulkGrade` from the code execution API

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

#### `check_enrollment`
Check whether a specific campus login ID is enrolled in a course. Answers a roster-membership question about an externally-supplied person (not the caller) and returns **only** a yes/no plus minimal enrollment metadata — never the roster, names, or grades. Requires a Canvas token with roster-admin rights.

> **A token without roster rights does not fail loudly.** Canvas returns HTTP 200 with the full roster and silently omits `login_id`/`sis_user_id` from every user, so the identifier can never match. This tool detects that and answers **INDETERMINATE**, never "no" — permission-blindness is not absence. To ask about *yourself*, use [`get_my_enrollments`](#get_my_enrollments) instead, which needs no roster permission.

**Parameters:**
- `course_identifier`: Course code, numeric ID, or SIS ID
- `net_id`: The person's campus login ID — a NetID (UIUC), uniqname (UMich), campus ID, or the full email-style Canvas login. Matched case-insensitively against `login_id`, then `sis_user_id`. **Not** a display name.
- `role` (optional): Enrollment type that satisfies the check — `student` (default), `teacher`, `ta`, `observer`, `designer`, or `any`
- `active_only` (optional): Only count active enrollments (default `true`)

**Example:**
```
"Is netid jdoe2 enrolled in BADM 350?"
```

**Returns:** A yes/no answer with the enrollment state, role, and which field matched. Data-minimizing by design — built for external access gating (e.g. UniQuick) without exposing the class roster.

> **Identifier form is flexible, but never guessed at.** Canvas does not define what `login_id` holds — UIUC stores the bare NetID (`jdoe2`), other instances store the full email (`jdoe2@umich.edu`). An exact match always wins. Failing that, a **bare** identifier may match a domain-qualified roster value (`zqian` finds `zqian@umich.edu`), because there the roster's own domain is authoritative. The reverse is not inferred: since this tool is used as an access gate, anything unverifiable returns **AMBIGUOUS** rather than a yes or a no —
>
> - two differing full addresses (`jdoe@school.edu` vs `jdoe@other.edu`) are different people, and a bare `sis_user_id` on that same user will not override their own domain;
> - an identifier matching several people by local part alone is not resolved by roster order;
> - a qualified identifier offered to a roster of bare IDs is unverifiable — `jdoe@attacker.example` has as much claim on a stored `jdoe` as the real domain does. Re-run with the bare ID.

> **`role` defaults to `student`, and a NO is scoped to that role.** Asking about a teacher with the default answers `NO — … has no active 'student' enrollment`, which is true but reads as "not in this course". The answer now names any other role the person holds (`They ARE enrolled in this course, as: TeacherEnrollment`). Pass `role="any"` when you only want to know whether they are in the course at all.

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

#### `get_peer_review_assignments`
Get the peer review mapping showing who reviews whom, with completion status.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `include_names` (optional): Include student names (default: true)
- `include_submission_details` (optional): Include submission metadata (default: false)

**Example:**
```
"Who is reviewing whom on the essay assignment?"
```

**Returns:** Reviewer-to-reviewee mapping with per-review completion status.

---

#### `generate_peer_review_report`
Generate a peer review completion report with summary statistics, analytics, and follow-up recommendations.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `report_format` (optional): `markdown` (default), `csv`, or `json`
- `include_executive_summary` (optional): Include executive summary (default: true)
- `include_student_details` (optional): Include student details (default: true)
- `include_action_items` (optional): Include action items (default: true)
- `include_timeline_analysis` (optional): Include timeline analysis (default: true)
- `save_to_file` (optional): Save report to a local file (default: false)
- `filename` (optional): Custom filename for the saved report

**Example:**
```
"Generate a peer review completion report for assignment 4821"
```

---

#### `get_peer_review_followup_list`
Get a prioritized list of students needing follow-up on peer review completion.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `priority_filter` (optional): `urgent`, `medium`, `low`, or `all` (default: all)
- `include_contact_info` (optional): Include email addresses (default: false)
- `days_threshold` (optional): Days since assignment for urgency calculation (default: 3)

**Example:**
```
"Which students still owe peer reviews?"
```

**Returns:** Prioritized list of students to follow up with, by incomplete review count.

---

#### `send_peer_review_followup_campaign`
Complete workflow: analyze peer review completion and send targeted reminders.

**Two-step by design.** Call it without a `confirmation_token` to get the
analytics plus the fully rendered subject/body of each reminder batch (urgent
vs gentle) and a single-use token; call again with the token to send. The
token commits to the recipients AND the rendered text, so it is void if the
completion analytics shifted or the assignment was renamed in between.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Analyze peer review completion and remind everyone who's behind"
```

**Returns:** Without a token: analytics, planned reminder groups, and a
`confirmation_token` (nothing sent). With a valid token: campaign summary with
send results.

---

#### `generate_peer_review_feedback_report`
Create instructor-ready reports on peer review quality.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `report_type` (optional): `comprehensive` (default), `summary`, or `individual`
- `include_student_names` (optional): Include student names (default: false)
- `format_type` (optional): `markdown` (default), `html`, or `text`

**Example:**
```
"Generate a peer review quality report for the essay assignment"
```

---

#### `extract_peer_review_dataset`
Export all peer review data for external analysis.

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `output_format` (optional): `csv` (default), `json`, or `xlsx`
- `include_analytics` (optional): Include quality analytics (default: true)
- `anonymize_data` (optional): Anonymize student data (default: true)
- `save_locally` (optional): Save file locally (default: true)
- `filename` (optional): Custom filename

**Example:**
```
"Export all peer review data for the essay assignment as CSV"
```

---

### Communication & Messaging

#### `send_conversation`
Send messages to students.

**Sending to exactly one plain numeric user ID is a single call. Anything else
is two-step** — multiple recipients, or any expandable alias like `course_123`
or `group_45` (which fans out server-side): call without a `confirmation_token`
to get a preview (recipients, subject, body, attachments, delivery flags) plus
a single-use token, then call again with the token and identical arguments to
send.

**Parameters:**
- `course_identifier`: Course code or ID
- `recipients`: User IDs (array)
- `subject`: Message subject
- `body`: Message content
- `confirmation_token` (optional): Token from the preview call (multi-recipient only)

**Example:**
```
"Message students who haven't submitted Assignment 3"
```

---

#### `send_peer_review_inbox_messages`
Send direct Canvas Inbox messages about incomplete peer reviews. This tool sends
ordinary conversation messages; it does **not** invoke Canvas's native
peer-review reminder action. It verifies the course-level `manage_grades`
permission before preparing or sending a message.

**Two-step by design.** Call it without a `confirmation_token` to get a preview
(recipients, composed subject and body) plus a single-use token; call again
with the token and identical arguments to send. The token is void if the
composed message changed (e.g. the assignment was renamed).

**Parameters:**
- `course_identifier`: Course code or ID
- `assignment_id`: Assignment ID
- `recipient_ids`: Students to message (array)
- `custom_message` (optional): Custom message template
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Send reminders to students who haven't completed peer reviews"
```

---

#### `send_bulk_messages_from_list`
Send customized messages to multiple recipients using templates with per-recipient variables.

**Two-step by design.** Call it without a `confirmation_token` to get a preview
that renders **every** outbound message plus a single-use token; show the
preview to the educator, then call again with the token and identical arguments
to actually send. Rows with invalid or alias user IDs, or that fail to render,
fail the preview before a token is issued. The token expires after a few
minutes and is void if any argument changed since the preview. This prevents
content read from Canvas (e.g. a student-authored message) from silently
triggering a bulk send.

**Parameters:**
- `course_identifier`: Course code or ID
- `recipient_data`: List of dicts with recipient info and template variables
- `subject_template`: Subject with placeholders (e.g., `"Reminder - {missing_count} reviews"`)
- `body_template`: Body with placeholders (e.g., `"Hi {name}, you have {missing_count}..."`)
- `context_code` (optional): Course context
- `mode` (optional): `sync` (default) or `async`
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Send this templated reminder to these 12 students"
```

**Returns:** Without a token: a preview with `confirmation_token` (nothing sent).
With a valid token: per-recipient success/failure summary of sent messages.

---

#### `create_announcement`
Post course announcements. Before posting, the tool checks the course's
announcement permission and refuses on an explicit denial. Canvas can
occasionally accept the request but create a regular discussion instead; the
tool verifies the returned type, deletes that unintended topic automatically,
and reports failure. If cleanup cannot be confirmed, the response includes the
topic ID when Canvas returned one and tells the user to check the course and
remove the unintended topic. It never falls back to a discussion post.

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

#### `update_discussion_topic`
Edit an existing discussion topic or announcement (title, body, publish state, etc.).

**Parameters:**
- `course_identifier`: Course code or ID
- `topic_id`: Discussion topic ID
- `title`: New title (optional)
- `message`: New body content, HTML supported (optional)
- `published`: Publish or unpublish (optional)
- `pinned`: Pin or unpin (optional)
- `locked`: Lock or unlock (optional)
- `delayed_post_at`: Schedule posting, ISO 8601 (optional)
- `lock_at`: Auto-lock datetime, ISO 8601 (optional)
- `require_initial_post`: Require initial post before viewing replies (optional)

**Example:**
```
"Update the Week 1 discussion prompt to mention Claude and Gemini"
```

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

### Announcement Management

Deletion is **permanent** — Canvas may retain a recycle-bin copy depending on admin settings, but do not count on it.

**Every delete tool is two-step.** Call it without `confirmation_token` and it returns a preview of exactly what would be deleted plus a single-use token; nothing is deleted. Call it again with the token and identical arguments to delete. The token expires in 5 minutes and stops matching if the target changed in between (retitled, different match set), so the preview the user saw is the deletion they get.

#### `delete_announcement_with_confirmation`
Delete a single announcement.

**Parameters:**
- `course_identifier`: Course code or ID
- `announcement_id`: Announcement ID to delete
- `require_title_match` (optional): Only delete if the title matches this string exactly
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Delete the 'Old Exam Info' announcement, but show me it first"
```

---

#### `bulk_delete_announcements`
Delete multiple announcements by ID.

**Parameters:**
- `course_identifier`: Course code or ID
- `announcement_ids`: List of announcement IDs to delete
- `stop_on_error` (optional): Stop at the first failed deletion; if false, continue with the rest (default: false)
- `limit` (optional): Max announcements per call (default: 25); pass a higher value to override
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Delete announcements 101, 102, and 103 from BADM 350"
```

**Returns:** Preview with titles and any unreachable IDs (no token), then a per-announcement success/failure summary.

---

#### `delete_announcements_by_criteria`
Delete announcements matching criteria such as age or title patterns.

**Parameters:**
- `course_identifier`: Course code or ID
- `criteria`: Dict with keys: `title_contains`, `older_than` (ISO), `newer_than` (ISO), `title_regex`
- `limit` (optional): Max announcements to delete (safety limit)
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Delete all announcements older than 90 days (preview first)"
```

**Returns:** The matched list with a token; the token is bound to that exact match set, so if the listing drifts before you confirm, the call refuses instead of deleting something you never saw.

---

### Page Management

For reading pages, see [Content Access](#content-access); for publish/unpublish and other settings, see [Page Settings](#page-settings).

#### `create_page`
Create a new page in a course.

**Parameters:**
- `course_identifier`: Course code or ID
- `title`: Page title
- `body`: HTML content for the page
- `published` (optional): Whether to publish (default: true)
- `front_page` (optional): Whether to set as front page (default: false)
- `editing_roles` (optional): Who can edit (default: "teachers")

**Example:**
```
"Create a course page called 'Office Hours' with this content"
```

**Returns:** Created page details including URL slug and publication state.

---

#### `edit_page_content`
Replace the content of an existing page.

**Parameters:**
- `course_identifier`: Course code or ID
- `page_url_or_id`: Page URL slug or page ID
- `new_content`: New HTML content for the page
- `title` (optional): New title for the page

**Example:**
```
"Update the 'Course Policies' page with this new HTML"
```

---

#### `delete_page`
Delete a page from a course. **Permanent.** Two-step: preview first, then confirm with the token.

**Parameters:**
- `course_identifier`: Course code or ID
- `page_url_or_id`: Page URL slug or page ID to delete
- `require_title_match` (optional): Safety check — only delete if the page title matches exactly
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Example:**
```
"Delete the outdated 'Fall 2024 Schedule' page"
```

---

### File Management

For listing, downloading, and reading course files (available to both roles), see [Files](#files) under Shared Tools.

#### `upload_course_file`
Upload a local file to Canvas course storage.

> **Local (stdio) servers only.** `file_path` is read from the *server's*
> filesystem. On a shared HTTP server that is somebody else's host, so the tool
> refuses the request rather than let a remote caller name any file the service
> account can read.

**Parameters:**
- `course_identifier`: Course code or ID
- `file_path`: Absolute path to the local file to upload (stdio only)
- `folder_path` (optional): Canvas folder path (default: "course files" root)
- `display_name` (optional): Override the filename shown in Canvas
- `on_duplicate` (optional): `rename` (default) or `overwrite`

**Example:**
```
"Upload lecture5.pdf to the course files"
```

**Returns:** Uploaded file details including the Canvas file ID, usable with `add_module_item` (`item_type='File'`) or `send_conversation` (attachment IDs).

---

### Accessibility

Two workflows: a built-in scanner (`scan_course_content_accessibility` → `fix_accessibility_issues`), and a UFIXIT-report pipeline (`fetch_ufixit_report` → `parse_ufixit_violations` → `format_accessibility_summary`).

The UFIXIT pipeline requires the UDOIT/UFIXIT add-on on your Canvas instance. Set `ACCESSIBILITY_CHECKERS=none` to leave those three tools unregistered (default: `ufixit`; `udoit` is an alias). The built-in scanner needs no add-on and is always available.

#### `scan_course_content_accessibility`
Scan course content for basic accessibility issues.

**Parameters:**
- `course_identifier`: Course code or ID
- `content_types` (optional): Comma-separated types to scan: `pages`, `assignments`, `discussions`, `syllabus` (default: "pages,assignments")

**Example:**
```
"Scan my course for accessibility problems"
```

**Returns:** Accessibility issues grouped by page/item, with auto-fixable flags.

---

#### `fix_accessibility_issues`
Auto-fix accessibility issues flagged as `auto_fixable` by the scanner. Run `scan_course_content_accessibility` first to see what will be fixed.

**Parameters:**
- `course_identifier`: Course code or ID
- `fix_types` (optional): Comma-separated fix types to apply (default: all of the below)
  - `th_scope`: Add `scope="col"` to `<th>` without scope
  - `low_contrast`: Fix white text on `#ff5f05` orange backgrounds
  - `legacy_designplus`: Migrate `kl_` classes to `dp-` equivalents
  - `redundant_alt_prefix`: Remove "image of" prefix from alt text
- `content_types` (optional): Comma-separated types to fix: `pages`, `assignments` (default: "pages")
- `dry_run` (optional): Preview changes without applying (default: **true**). Set false to apply.

**Example:**
```
"Fix the auto-fixable accessibility issues found in the scan"
```

---

#### `fetch_ufixit_report`
Fetch a UFIXIT accessibility report stored on a Canvas course page.

**Parameters:**
- `course_identifier`: Course code or ID
- `page_title` (optional): Title of the UFIXIT report page (default: "UFIXIT")

**Example:**
```
"Fetch the UFIXIT accessibility report for BADM 350"
```

**Returns:** Report content ready for `parse_ufixit_violations`.

---

#### `parse_ufixit_violations`
Parse UFIXIT report content into individual accessibility violations.

**Parameters:**
- `report_json`: JSON string from `fetch_ufixit_report`

**Example:**
```
"Parse this UFIXIT report into individual violations"
```

---

#### `format_accessibility_summary`
Format parsed violations into a human-readable summary grouped by severity.

**Parameters:**
- `violations_json`: JSON string from `parse_ufixit_violations`

**Example:**
```
"Summarize these accessibility violations"
```

---

### Roster & Groups

#### `list_users`
List users enrolled in a course.

**Parameters:**
- `course_identifier`: Course code or ID

**Example:**
```
"List the students enrolled in BADM 350"
```

**Returns:** Enrolled users with IDs and roles. Names are subject to anonymization settings.

---

#### `list_groups`
List all groups and their members for a course.

**Parameters:**
- `course_identifier`: Course code or ID

**Example:**
```
"Show the project groups in BADM 350"
```

---

### Privacy & Anonymization

See also the `ENABLE_DATA_ANONYMIZATION` setting in the [usage guidelines](#for-educators).

#### `get_anonymization_status`
Get the server's current data anonymization configuration and statistics.

**Parameters:** none

**Example:**
```
"Is data anonymization enabled on this server?"
```

---

#### `create_student_anonymization_map`
Create a local CSV file mapping real student data to anonymous IDs for a course.

**Parameters:**
- `course_identifier`: Course code or ID

**Example:**
```
"Create an anonymization map for BADM 350"
```

**Returns:** Path to the CSV mapping file plus a summary of mapped students. Keep mapping files in `local_maps/` secure and never commit them to version control.

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

> Note: `get_course_details` and `get_course_content_overview` return only a short
> syllabus preview. For the **complete** syllabus body, use `get_syllabus` below.

---

#### `get_syllabus`
Get the complete Canvas Syllabus tab content for a course, **untruncated**. Unlike `get_course_content_overview` (which returns only a ~1000-character preview), this returns the full syllabus body, so later sections such as grading policies, weighting, and final-exam details remain accessible.

**Parameters:**
- `course_identifier`: Course code or ID
- `output_format` (optional): `text` (plain text, default), `html` (raw HTML body), or `both`
- `max_chars` (optional): Cap on returned characters per section. When exceeded, the content is truncated with an explicit `[truncated...]` marker. Defaults to no truncation.

**Example:**
```
"Get the full syllabus for BADM 350 including the grading policy"
"Show me the raw HTML of the CS101 syllabus"
```

---

#### `get_course_content_overview`
Get a comprehensive overview of course content including pages, modules, and syllabus in one call.

**Parameters:**
- `course_identifier`: Course code or ID
- `include_pages` (optional): Include pages information (default: true)
- `include_modules` (optional): Include modules and their items (default: true)
- `include_syllabus` (optional): Include syllabus content (default: true)

**Example:**
```
"Give me an overview of everything in BADM 350"
```

**Returns:** Structured overview of the course's pages, modules, and syllabus. The syllabus portion is a ~1000-character preview — use `get_syllabus` for the full body.

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

#### `get_front_page`
Get the front page content for a course.

**Parameters:**
- `course_identifier`: Course code or ID

**Example:**
```
"What's on the course front page?"
```

**Returns:** Front page title and full content body.

---

### Modules

Modules are Canvas's primary content organization system, allowing you to structure course content into ordered units with prerequisites and completion requirements.

#### `get_course_structure`
Get the complete course module structure as a JSON tree. Returns all modules with their items in a single call, plus summary statistics. Ideal for course auditing, QC checks, and structure cloning.

**Parameters:**
- `course_identifier`: Course code or ID
- `include_unpublished` (optional): Include unpublished modules/items (default: true)

**Example:**
```
"Show me the full structure of BADM 350"
"Get the module tree for my course"
```

**Returns:** JSON with `course_id`, `modules` array (each with nested `items`), and `summary` object with counts for total modules, items, unpublished items, empty modules, and item type breakdown.

---

#### `list_modules`
List all modules in a course.

**Parameters:**
- `course_identifier`: Course code or ID
- `include_items` (optional): Include item summary for each module (default: false)
- `search_term` (optional): Filter modules by name

**Example:**
```
"Show me all modules in BADM 350"
"List modules with their items"
```

---

#### `list_module_items`
List the items within a specific module, including pages.

**Parameters:**
- `course_identifier`: Course code or ID
- `module_id`: The module ID
- `include_content_details` (optional): Include additional content details (default: true)

**Example:**
```
"What's inside the 'Week 2' module?"
```

**Returns:** Items in the module with types, titles, and IDs.

---

#### `create_module`
Create a new module in a course.

**Parameters:**
- `course_identifier`: Course code or ID
- `name`: Module name (required)
- `position` (optional): Position in module list (1-indexed)
- `unlock_at` (optional): Date/time when module unlocks (ISO 8601)
- `require_sequential_progress` (optional): Students must complete items in order
- `prerequisite_module_ids` (optional): Comma-separated IDs of prerequisite modules
- `published` (optional): Whether module is published (default: true)

**Example:**
```
"Create a module called 'Week 1: Introduction' in BADM 350"
"Add a new module 'Final Project' at position 10"
```

---

#### `update_module`
Update an existing module's settings.

**Parameters:**
- `course_identifier`: Course code or ID
- `module_id`: Module ID to update
- `name` (optional): New name
- `position` (optional): New position
- `unlock_at` (optional): New unlock date, or empty string to remove
- `require_sequential_progress` (optional): Sequential progress requirement
- `prerequisite_module_ids` (optional): New prerequisites, or empty to clear
- `published` (optional): Published status

**Example:**
```
"Rename module 12345 to 'Unit 2: Advanced Topics'"
"Unpublish module 67890"
```

---

#### `delete_module`
Delete a module from a course. Two-step: preview first, then confirm with the token.

**Parameters:**
- `course_identifier`: Course code or ID
- `module_id`: Module ID to delete
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Note:** This removes the module organization only. The actual content (pages, assignments, etc.) is NOT deleted.

**Example:**
```
"Delete module 12345 from BADM 350"
```

---

#### `add_module_item`
Add an item to a module.

**Parameters:**
- `course_identifier`: Course code or ID
- `module_id`: Module ID to add item to
- `item_type`: One of: File, Page, Discussion, Assignment, Quiz, SubHeader, ExternalUrl, ExternalTool
- `content_id` (optional): Canvas ID of content (required for File, Discussion, Assignment, Quiz, ExternalTool)
- `title` (optional): Title for the item (required for SubHeader, ExternalUrl)
- `position` (optional): Position within the module
- `indent` (optional): Indentation level (0-4)
- `page_url` (optional): Page URL slug (required for Page type)
- `external_url` (optional): URL (required for ExternalUrl type)
- `new_tab` (optional): Open external links in new tab
- `completion_requirement_type` (optional): must_view, must_submit, must_contribute, min_score, must_mark_done
- `completion_requirement_min_score` (optional): Minimum score (for min_score type)

**Example:**
```
"Add assignment 123 to module 456"
"Add a subheader 'Required Readings' to module 789"
"Add the syllabus page to the first module"
```

---

#### `update_module_item`
Update an existing module item.

**Parameters:**
- `course_identifier`: Course code or ID
- `module_id`: Module ID containing the item
- `item_id`: Item ID to update
- `title` (optional): New title
- `position` (optional): New position
- `indent` (optional): New indent level (0-4)
- `external_url` (optional): New URL (ExternalUrl items)
- `new_tab` (optional): Open in new tab
- `completion_requirement_type` (optional): New completion type, or empty to remove
- `completion_requirement_min_score` (optional): New min score
- `published` (optional): Published status
- `move_to_module_id` (optional): Move item to different module

**Example:**
```
"Move item 111 to module 222"
"Set completion requirement to 'must_view' for item 333"
```

---

#### `delete_module_item`
Remove an item from a module. Two-step: preview first, then confirm with the token.

**Parameters:**
- `course_identifier`: Course code or ID
- `module_id`: Module ID containing the item
- `item_id`: Item ID to remove
- `confirmation_token` (optional): Token from the preview call; omit to preview

**Note:** This only removes the item from the module. The actual content is NOT deleted.

**Example:**
```
"Remove item 12345 from module 67890"
```

---

### Page Settings

#### `update_page_settings`
Update page settings without changing content (publish/unpublish, front page, editing roles).

**Parameters:**
- `course_identifier`: Course code or ID
- `page_url_or_id`: Page URL slug or ID
- `published` (optional): True to publish, False to unpublish
- `front_page` (optional): True to set as course front page
- `editing_roles` (optional): Who can edit - teachers, students, members, or public
- `notify_of_update` (optional): True to notify users of the update

**Example:**
```
"Unpublish the Week 10 page in BADM 350"
"Set the syllabus page as the front page"
"Allow students to edit the collaborative notes page"
```

**Note:** The front page cannot be unpublished. To unpublish it, first set another page as the front page.

---

#### `bulk_update_pages`
Update settings for multiple pages at once.

**Parameters:**
- `course_identifier`: Course code or ID
- `page_urls`: Comma-separated list of page URL slugs
- `published` (optional): True to publish all, False to unpublish all
- `editing_roles` (optional): Who can edit
- `notify_of_update` (optional): True to notify users

**Example:**
```
"Unpublish all the draft pages: draft-1, draft-2, draft-3"
"Publish pages week-1, week-2, week-3 in my course"
```

**Note:** front_page is not supported in bulk updates (only one page can be front page).

---

### Files

For uploading files (educator-only), see [File Management](#file-management) under Educator Tools.

#### `list_course_files`
List files in a course with optional search.

**Parameters:**
- `course_identifier`: Course code or ID
- `search_term` (optional): Filter files by name
- `sort` (optional): Sort field: `name`, `size`, `created_at`, `updated_at`, `content_type` (default: updated_at)
- `order` (optional): `asc` or `desc` (default: desc)

**Example:**
```
"List the PDF files in this course"
```

**Returns:** Course files with IDs, names, sizes, and folders.

---

#### `download_course_file`
Download a course file to the local filesystem of the machine running the MCP server.

> **Local (stdio) servers only.** The write lands on the *server's* filesystem,
> which a remote caller cannot read anyway, so the tool refuses over HTTP and
> points at `read_course_file` instead. It also never overwrites: the
> destination is created exclusively, so a Canvas file named e.g. `.zshrc`
> cannot clobber a real file in the chosen directory.

**Parameters:**
- `course_identifier`: Course code or ID
- `file_id`: Canvas file ID (find it with `list_course_files` or `list_module_items`)
- `save_directory` (optional): Local directory to save to (default: system temp dir, must exist)

**Example:**
```
"Download the syllabus PDF from the course files"
```

**Returns:** Local path of the downloaded file with size and content type. Errors
if the destination already exists rather than overwriting it.

---

#### `read_course_file`
Read a course file and return its content directly in the response as base64. Unlike `download_course_file`, nothing is written to the server's filesystem, so this works when the MCP server runs on a different machine than the client.

**Parameters:**
- `course_identifier`: Course code or ID
- `file_id`: Canvas file ID (find it with `list_course_files` or `list_module_items`)
- `max_size_mb` (optional): Maximum file size in MB to read (default: 25). Clamped server-side to `READ_FILE_MAX_SIZE_MB` (default 100); larger files are rejected to avoid excessive memory usage.

**Example:**
```
"Read the rubric spreadsheet from course files"
```

**Returns:** File content as base64 with name, size, and content type.

---

### Conversations (Inbox)

#### `list_conversations`
List Canvas inbox conversations for the current user.

**Parameters:**
- `scope` (optional): `unread` (default), `starred`, `sent`, `archived`, or `all`
- `filter_ids` (optional): Conversation IDs to filter by
- `filter_mode` (optional): `and` (default) or `or` for `filter_ids`
- `include_participants` (optional): Include participant info (default: true)
- `include_all_ids` (optional): Include all participant IDs (default: false)

**Example:**
```
"Show my Canvas inbox"
```

**Returns:** Conversations with participants, subjects, and read state.

---

#### `get_conversation_details`
Get a full conversation thread with its messages.

**Parameters:**
- `conversation_id`: Conversation ID
- `auto_mark_read` (optional): Mark as read when viewed (default: true)
- `include_messages` (optional): Include all messages (default: true)

**Example:**
```
"Show me the full thread of conversation 555"
```

---

#### `get_unread_count`
Get the number of unread conversations.

**Parameters:** none

**Example:**
```
"How many unread Canvas messages do I have?"
```

---

#### `mark_conversations_read`
Mark multiple conversations as read.

**Parameters:**
- `conversation_ids`: List of conversation IDs to mark as read

**Example:**
```
"Mark conversations 12, 13, and 14 as read"
```

**Returns:** Per-conversation success/failure summary.

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
View discussion forums in a course. Returns discussion topics only — announcements
are a separate Canvas collection and are excluded unless you opt in.

**Parameters:**
- `course_identifier`: Course code or ID
- `include_announcements` (optional, default `false`): Also list the course's
  announcements alongside its discussion topics. Each entry is labelled
  `Type: Announcement` or `Type: Discussion`. To list announcements on their
  own, use [`list_announcements`](#list_announcements) instead.

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

#### `get_discussion_with_replies`
Get all discussion entries with nested replies in one call.

**Parameters:**
- `course_identifier`: Course code or ID
- `topic_id`: Discussion topic ID
- `include_replies` (optional): Fetch detailed replies for all entries (default: false)

**Example:**
```
"Get the whole Week 3 discussion including replies"
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
Search and discover available Canvas tools by keyword — both the registered
MCP tools (the ~99 Python tools like `list_peer_reviews`,
`create_assignment`, called directly) and the TypeScript code execution API
operations (used from `execute_typescript`). Matches against tool name and
description.

**Parameters:**
- `query` (optional): Search term to filter tools. Empty string returns all tools. Examples: "peer review", "grading", "assignment", "discussion", "bulk"
- `detail_level` (optional): How much information to return. Default: "signatures"
  - `"names"`: Just tool names / file paths (most efficient for quick lookups)
  - `"signatures"`: Names/paths + short descriptions + function signatures (recommended)
  - `"full"`: Fuller descriptions for MCP tools (capped length) and code API file content capped at 2,000 characters per match

**Example:**
```
"Search for peer review tools"
"Search for grading tools in the code API"
"What bulk operations are available?"
"Show me all code API tools"
"Find discussion-related operations"
```

**Returns:** Response schema version `2`. A successful search returns JSON with
`schema_version`, `query`, `detail_level`, `count`, and two labeled sections —
`mcp_tools` (registered MCP tools) and `code_execution_api` (TypeScript code API
modules) — each with its own `count` and `tools` array. The pre-v1.10 flat
top-level `tools` key no longer exists; scripted clients should branch on
`schema_version`. A no-match response still includes `schema_version: 2` and
reports the message plus `mcp_tools_searched` instead of empty result sections.

**Usage Tips:**
- Use empty query (`""`) to list all available tools
- Use `"signatures"` detail level for most tasks (default)
- Use `"names"` when you just need a quick overview
- Use `"full"` only when you need to see complete implementation details

**Example Direct Usage:**
```typescript
// Search for peer-review tools across both MCP tools and the code API
search_canvas_tools("peer review", "signatures")

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

This tool can reduce model-context use by processing bulk items locally and returning only selected output. Actual savings depend on the workload and AI client.

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

**Platform Support:**
- **macOS/Linux**: Uses `npx tsx` directly
- **Windows**: Automatically locates the tsx CLI entry point via `shutil.which` or `%APPDATA%\npm\node_modules\tsx\dist\cli.mjs`, then invokes it via `node` to avoid `.cmd` batch wrapper limitations

**Security:**
- Code runs in a temporary file that is deleted after execution
- Inherits Canvas API credentials from server environment
- Timeout enforced to prevent runaway processes
- Local sandbox controls are best-effort, not a complete security boundary; code can access resources allowed to the server process, and strict egress control requires external isolation (see [issue #157](https://github.com/vishalsachdev/canvas-mcp/issues/157))

**Token Efficiency:**
- **Traditional approach**: Tool-by-tool processing may return each submission to the model
- **Code execution approach**: Per-item work runs locally and only selected output returns

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

1. **Enable anonymization**: Set `ENABLE_DATA_ANONYMIZATION=true` in `.env` for FERPA-conscious data handling; this control does not by itself establish compliance
2. **Use course codes**: Be specific about which course (e.g., "badm_350_120251_246794")
3. **Leverage automation**: Use messaging and reminder tools for routine communications
4. **Combine analytics**: Request multiple analytics in one query for comprehensive insights
5. **Protect mapping files**: Keep `local_maps/` folder secure - never commit to version control

### General Best Practices

- **Ask follow-up questions**: Claude remembers context within a conversation
- **Request summaries**: "Summarize..." for quick overviews
- **Be conversational**: Natural language works better than rigid commands
- **Check tool output**: Review the data Claude retrieves before taking action

---

## Known API Limitations

Some Canvas API endpoints have bugs or design issues that prevent certain operations from working correctly.

### Rubric API Issues

| Tool | Status | Issue | Reference |
|------|--------|-------|-----------|
| `update_rubric` | Removed | API does full replacement instead of PATCH (causes data loss) | Internal testing |

**Workaround for Rubric Editing:**
1. **Edit rubrics** in Canvas web UI: Assignments → Edit → Rubric
2. **Copy rubrics** between courses: Use "Find a Rubric" in the rubric editor

**Working Rubric Tools:**
- `create_rubric` - Create a new rubric with defined criteria and ratings
- `create_rubric_from_csv` - Create a rubric using a CSV file upload
- `list_rubrics` - List rubrics in a course
- `get_rubric` - View rubric criteria and points (by rubric_id or assignment_id)
- `get_rubric_assessment` - View a student's rubric assessment
- `associate_rubric` - Link rubric to assignment
- `grade_with_rubric` - Grade single submission
- `bulk_grade_submissions` - Efficient batch grading

---

## Need Help?

- **Student Guide**: https://canvas-mcp.illinihunt.org/student-guide.html
- **Educator Guide**: https://canvas-mcp.illinihunt.org/educator-guide.html
- **Main README**: [README.md](../README.md)
- **Development Guide**: [CLAUDE.md](../CLAUDE.md)
- **GitHub Issues**: [Report issues](https://github.com/vishalsachdev/canvas-mcp/issues)
